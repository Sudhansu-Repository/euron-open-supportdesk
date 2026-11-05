# Logs, alarms and one dashboard for a deployment:
#
#   - a CloudWatch log group per app (api, worker, web, migrate), encrypted, with retention
#   - metrics extracted from the structured worker logs: jobs that failed, and AI turns
#     that died and were handed to a human
#   - alarms to an SNS topic (optionally e-mailed): 5xx, api p95 latency, unhealthy
#     targets, a service with no running task, CPU and memory per service, database,
#     cache, failing jobs and dead AI turns
#   - one dashboard with the same signals side by side
data "aws_region" "current" {}

locals {
  region     = data.aws_region.current.region
  apps       = toset(["api", "worker", "web", "migrate"])
  namespace  = "SupportDesk/${var.name_prefix}"
  cache_node = [for i in range(var.cache_node_count) : format("%s-%03d", var.cache_replication_group_id, i + 1)]
}

# ─── Logs ────────────────────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "app" {
  #checkov:skip=CKV_AWS_338:Retention is an input (log_retention_days); aws-prod keeps 365 days.
  for_each          = local.apps
  name              = "/supportdesk/${var.name_prefix}/${each.key}"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.logs_kms_key_arn
}

# Log lines turned into metrics, so a broken pipeline pages someone before customers
# notice. The worker logs one JSON object per line (core/logs.py):
#
#   JobFailures     `job failed`: a job raised (it is retried with backoff, and dies after
#                   its last attempt); a burst means a dependency is down
#   AiTurnsFailed   `AI turn failed, handed over`: an AI turn died after every retry and the
#                   conversation went to a human instead (never lost, but the AI is down)
locals {
  log_metrics = {
    JobFailures   = { group = "worker", pattern = var.job_failed_log_pattern, value = "1" }
    AiTurnsFailed = { group = "worker", pattern = var.ai_turn_failed_log_pattern, value = "1" }
  }
}

resource "aws_cloudwatch_log_metric_filter" "this" {
  for_each       = local.log_metrics
  name           = "${var.name_prefix}-${each.key}"
  log_group_name = aws_cloudwatch_log_group.app[each.value.group].name
  pattern        = each.value.pattern
  metric_transformation {
    name      = each.key
    namespace = local.namespace
    value     = each.value.value
    unit      = "Count"
  }
}

# ─── Alarms ──────────────────────────────────────────────────────────────────

# Encrypted with the CMK: CloudWatch cannot publish to a topic under the AWS-managed SNS
# key, and the kms module's key policy lets it use this one.
resource "aws_sns_topic" "alarms" {
  name              = "${var.name_prefix}-alarms"
  kms_master_key_id = var.sns_kms_key_arn
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.alarm_email == null ? 0 : 1
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

locals {
  lb_alarms = merge([
    for name, s in var.lb_services : {
      "${name}-5xx" = {
        description = "${name}: 5xx responses from the tasks"
        namespace   = "AWS/ApplicationELB"
        metric      = "HTTPCode_Target_5XX_Count"
        stat        = "Sum"
        threshold   = var.target_5xx_threshold
        period      = 300
        dimensions  = { LoadBalancer = var.alb_arn_suffix, TargetGroup = s.target_group_arn_suffix }
        comparison  = "GreaterThanThreshold"
      }
      "${name}-unhealthy" = {
        description = "${name}: tasks failing load balancer health checks"
        namespace   = "AWS/ApplicationELB"
        metric      = "UnHealthyHostCount"
        stat        = "Maximum"
        threshold   = 0
        period      = 60
        dimensions  = { LoadBalancer = var.alb_arn_suffix, TargetGroup = s.target_group_arn_suffix }
        comparison  = "GreaterThanThreshold"
      }
    }
  ]...)

  ecs_alarms = merge([
    for name, service_name in var.ecs_services : {
      "${name}-cpu" = {
        description = "${name}: CPU sustained above 85%"
        namespace   = "AWS/ECS"
        metric      = "CPUUtilization"
        stat        = "Average"
        threshold   = 85
        period      = 300
        dimensions  = { ClusterName = var.ecs_cluster_name, ServiceName = service_name }
        comparison  = "GreaterThanThreshold"
      }
      "${name}-memory" = {
        description = "${name}: memory sustained above 85%"
        namespace   = "AWS/ECS"
        metric      = "MemoryUtilization"
        stat        = "Average"
        threshold   = 85
        period      = 300
        dimensions  = { ClusterName = var.ecs_cluster_name, ServiceName = service_name }
        comparison  = "GreaterThanThreshold"
      }
    }
  ]...)

  edge_alarms = {
    alb-5xx = {
      description = "Load balancer 5xx (no healthy target, timeouts)"
      namespace   = "AWS/ApplicationELB"
      metric      = "HTTPCode_ELB_5XX_Count"
      stat        = "Sum"
      threshold   = var.target_5xx_threshold
      period      = 300
      dimensions  = { LoadBalancer = var.alb_arn_suffix }
      comparison  = "GreaterThanThreshold"
    }
  }

  db_alarms = {
    db-cpu = {
      description = "Database CPU sustained above 80%"
      namespace   = "AWS/RDS"
      metric      = "CPUUtilization"
      stat        = "Average"
      threshold   = 80
      period      = 300
      dimensions  = { DBInstanceIdentifier = var.db_instance_identifier }
      comparison  = "GreaterThanThreshold"
    }
    db-storage = {
      description = "Database free storage below 5 GiB"
      namespace   = "AWS/RDS"
      metric      = "FreeStorageSpace"
      stat        = "Minimum"
      threshold   = 5 * 1024 * 1024 * 1024
      period      = 300
      dimensions  = { DBInstanceIdentifier = var.db_instance_identifier }
      comparison  = "LessThanThreshold"
    }
    db-connections = {
      description = "Database connections above 80% of the configured ceiling"
      namespace   = "AWS/RDS"
      metric      = "DatabaseConnections"
      stat        = "Maximum"
      threshold   = var.db_max_connections * 0.8
      period      = 300
      dimensions  = { DBInstanceIdentifier = var.db_instance_identifier }
      comparison  = "GreaterThanThreshold"
    }
  }

  # Per node: with volatile-lru a full node evicts cache entries first, and refuses writes
  # once only counters are left. Memory is the alarm that matters most here.
  # Keys use the node number (known at plan time); the node id, which embeds the
  # replication group id and is only known after apply, goes in the values.
  cache_alarms = merge([
    for i, node in local.cache_node : {
      "cache-node-${i + 1}-memory" = {
        description = "Cache node ${node}: memory above 80% (when full, answer caching and live fan-out degrade)"
        namespace   = "AWS/ElastiCache"
        metric      = "DatabaseMemoryUsagePercentage"
        stat        = "Maximum"
        threshold   = 80
        period      = 300
        dimensions  = { CacheClusterId = node }
        comparison  = "GreaterThanThreshold"
      }
      "cache-node-${i + 1}-cpu" = {
        description = "Cache node ${node}: engine CPU above 80%"
        namespace   = "AWS/ElastiCache"
        metric      = "EngineCPUUtilization"
        stat        = "Average"
        threshold   = 80
        period      = 300
        dimensions  = { CacheClusterId = node }
        comparison  = "GreaterThanThreshold"
      }
    }
  ]...)

  threshold_alarms = merge(local.lb_alarms, local.ecs_alarms, local.edge_alarms, local.db_alarms, local.cache_alarms)
}

resource "aws_cloudwatch_metric_alarm" "threshold" {
  for_each            = local.threshold_alarms
  alarm_name          = "${var.name_prefix}-${each.key}"
  alarm_description   = each.value.description
  namespace           = each.value.namespace
  metric_name         = each.value.metric
  statistic           = each.value.stat
  dimensions          = each.value.dimensions
  period              = each.value.period
  evaluation_periods  = 2
  threshold           = each.value.threshold
  comparison_operator = each.value.comparison
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  ok_actions          = [aws_sns_topic.alarms.arn]
}

# p95, not average: a slow database query hides inside an average of cached reads. AI
# turns run on the worker, never on a request path, so seconds here mean trouble.
resource "aws_cloudwatch_metric_alarm" "api_latency_p95" {
  alarm_name          = "${var.name_prefix}-api-latency-p95"
  alarm_description   = "api: p95 response time above ${var.api_p95_latency_seconds}s (AI turns are queued, never on a request path)"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "TargetResponseTime"
  extended_statistic  = "p95"
  dimensions          = { LoadBalancer = var.alb_arn_suffix, TargetGroup = var.lb_services["api"].target_group_arn_suffix }
  period              = 300
  evaluation_periods  = 3
  threshold           = var.api_p95_latency_seconds
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  ok_actions          = [aws_sns_topic.alarms.arn]
}

# A service with no running task is down, whatever its other metrics say. Missing data
# counts as breaching: a service that stopped reporting is not healthy. Container
# Insights (on by default in the service module) publishes RunningTaskCount.
resource "aws_cloudwatch_metric_alarm" "not_running" {
  for_each            = var.ecs_services
  alarm_name          = "${var.name_prefix}-${each.key}-not-running"
  alarm_description   = "${each.key}: no running task"
  namespace           = "ECS/ContainerInsights"
  metric_name         = "RunningTaskCount"
  statistic           = "Minimum"
  dimensions          = { ClusterName = var.ecs_cluster_name, ServiceName = each.value }
  period              = 60
  evaluation_periods  = 3
  threshold           = 1
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  ok_actions          = [aws_sns_topic.alarms.arn]
}

locals {
  log_alarms = {
    job-failures = {
      description = "Worker jobs failed more than ${var.job_failure_threshold} times in 5 minutes (a dependency is likely down)"
      metric      = "JobFailures"
      threshold   = var.job_failure_threshold
    }
    ai-turns-failed = {
      description = "AI turns died and were handed to humans more than ${var.ai_turn_failure_threshold} times in 5 minutes (the AI provider is failing)"
      metric      = "AiTurnsFailed"
      threshold   = var.ai_turn_failure_threshold
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "logs" {
  for_each            = local.log_alarms
  alarm_name          = "${var.name_prefix}-${each.key}"
  alarm_description   = each.value.description
  namespace           = local.namespace
  metric_name         = each.value.metric
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = each.value.threshold
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  ok_actions          = [aws_sns_topic.alarms.arn]
}

# ─── Dashboard ───────────────────────────────────────────────────────────────

resource "aws_cloudwatch_dashboard" "this" {
  dashboard_name = var.name_prefix
  dashboard_body = jsonencode({
    widgets = concat(
      [
        {
          type = "metric", x = 0, y = 0, width = 12, height = 6
          properties = {
            title = "Requests and errors", region = local.region, stat = "Sum", period = 60
            metrics = [
              ["AWS/ApplicationELB", "RequestCount", "LoadBalancer", var.alb_arn_suffix],
              [".", "HTTPCode_Target_4XX_Count", ".", "."],
              [".", "HTTPCode_Target_5XX_Count", ".", "."],
              [".", "HTTPCode_ELB_5XX_Count", ".", "."],
            ]
          }
        },
        {
          type = "metric", x = 12, y = 0, width = 12, height = 6
          properties = {
            title = "api latency p50 / p95 / p99", region = local.region, period = 60
            metrics = [
              ["AWS/ApplicationELB", "TargetResponseTime", "LoadBalancer", var.alb_arn_suffix, "TargetGroup", var.lb_services["api"].target_group_arn_suffix, { stat = "p50" }],
              ["...", { stat = "p95" }],
              ["...", { stat = "p99" }],
            ]
          }
        },
        {
          type = "metric", x = 0, y = 12, width = 8, height = 6
          properties = {
            title = "Worker: failed jobs / dead AI turns", region = local.region, period = 60, stat = "Sum"
            metrics = [
              [local.namespace, "JobFailures"],
              [local.namespace, "AiTurnsFailed"],
            ]
          }
        },
        {
          type = "metric", x = 8, y = 12, width = 8, height = 6
          properties = {
            title = "Database", region = local.region, stat = "Average", period = 60
            metrics = [
              ["AWS/RDS", "CPUUtilization", "DBInstanceIdentifier", var.db_instance_identifier],
              [".", "DatabaseConnections", ".", "."],
              [".", "ReadLatency", ".", "."],
              [".", "WriteLatency", ".", "."],
            ]
          }
        },
        {
          type = "metric", x = 16, y = 12, width = 8, height = 6
          properties = {
            title = "Cache memory % / engine CPU %", region = local.region, stat = "Maximum", period = 60
            metrics = concat(
              [for node in local.cache_node : ["AWS/ElastiCache", "DatabaseMemoryUsagePercentage", "CacheClusterId", node]],
              [for node in local.cache_node : ["AWS/ElastiCache", "EngineCPUUtilization", "CacheClusterId", node]],
            )
          }
        },
      ],
      [
        for i, name in sort(keys(var.ecs_services)) : {
          type = "metric", x = (i % 3) * 8, y = 6, width = 8, height = 6
          properties = {
            title = "${name}: CPU / memory", region = local.region, stat = "Average", period = 60
            metrics = [
              ["AWS/ECS", "CPUUtilization", "ClusterName", var.ecs_cluster_name, "ServiceName", var.ecs_services[name]],
              [".", "MemoryUtilization", ".", ".", ".", "."],
            ]
          }
        }
      ],
    )
  })
}
