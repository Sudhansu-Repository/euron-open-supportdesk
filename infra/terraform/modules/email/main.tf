# Amazon SES for SupportDesk's mail, both directions.
#
# Outgoing: ticket replies (with threading headers), portal sign-in links, invitations
# and CSAT requests. The api and worker send through SES (MAIL_BACKEND=ses) from
# `from_address`; their task roles may send only as that address, only through this
# identity.
#
#   - a domain identity with Easy DKIM (three CNAMEs), published in Route53 when a zone is
#     given, otherwise listed in the dkim_records output for the operator to create
#   - a configuration set (the identity's default) that records bounces and complaints as
#     CloudWatch metrics and suppresses addresses that bounced or complained
#   - new AWS accounts start in the SES sandbox: request production access before
#     replying to customers outside verified addresses (docs/guides/deploy-aws.md)
#
# Incoming (enable_inbound): customers write to an inbox address or reply to a ticket
# email (<local>+<ticket token>@<domain>); SES receives it, stores the raw message under
# inbound/ in the objects bucket, and publishes it (Base64, up to 150 KB) to an SNS topic
# whose HTTPS subscription is the inbox's inbound URL
# (https://<host>/api/v1/channels/email/inbound/<token>). The api accepts the SNS
# envelope (verifying its signature) and opens or threads the ticket. MX for the domain
# must point at SES inbound (created in Route53 when a zone is given). SES receiving
# exists in a subset of regions and only one receipt rule set is active per account and
# region.
resource "aws_sesv2_email_identity" "this" {
  email_identity         = var.domain
  configuration_set_name = aws_sesv2_configuration_set.this.configuration_set_name
}

resource "aws_sesv2_configuration_set" "this" {
  configuration_set_name = "${var.name_prefix}-mail"

  delivery_options {
    tls_policy = "REQUIRE"
  }
  reputation_options {
    reputation_metrics_enabled = true
  }
  sending_options {
    sending_enabled = true
  }
  suppression_options {
    suppressed_reasons = ["BOUNCE", "COMPLAINT"]
  }
}

resource "aws_sesv2_configuration_set_event_destination" "metrics" {
  configuration_set_name = aws_sesv2_configuration_set.this.configuration_set_name
  event_destination_name = "cloudwatch"
  event_destination {
    enabled              = true
    matching_event_types = ["SEND", "BOUNCE", "COMPLAINT", "REJECT", "DELIVERY"]
    cloud_watch_destination {
      dimension_configuration {
        default_dimension_value = "supportdesk"
        dimension_name          = "app"
        dimension_value_source  = "MESSAGE_TAG"
      }
    }
  }
}

resource "aws_route53_record" "dkim" {
  count   = var.route53_zone_id == null ? 0 : 3
  zone_id = var.route53_zone_id
  name    = "${aws_sesv2_email_identity.this.dkim_signing_attributes[0].tokens[count.index]}._domainkey.${var.domain}"
  type    = "CNAME"
  ttl     = 600
  records = ["${aws_sesv2_email_identity.this.dkim_signing_attributes[0].tokens[count.index]}.dkim.amazonses.com"]
}

data "aws_iam_policy_document" "send" {
  statement {
    sid     = "SendMail"
    actions = ["ses:SendEmail", "ses:SendRawEmail"]
    resources = [
      aws_sesv2_email_identity.this.arn,
      aws_sesv2_configuration_set.this.arn,
    ]
    condition {
      test     = "StringEquals"
      variable = "ses:FromAddress"
      values   = [var.from_address]
    }
  }
}

# ─── Inbound ─────────────────────────────────────────────────────────────────

data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

locals {
  inbound            = var.enable_inbound ? 1 : 0
  inbound_recipients = length(var.inbound_recipients) > 0 ? var.inbound_recipients : [var.domain]
}

resource "aws_sns_topic" "inbound" {
  count             = local.inbound
  name              = "${var.name_prefix}-inbound-mail"
  kms_master_key_id = var.kms_key_arn
}

data "aws_iam_policy_document" "inbound_topic" {
  count = local.inbound
  statement {
    sid       = "SesPublish"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.inbound[0].arn]
    principals {
      type        = "Service"
      identifiers = ["ses.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_sns_topic_policy" "inbound" {
  count  = local.inbound
  arn    = aws_sns_topic.inbound[0].arn
  policy = data.aws_iam_policy_document.inbound_topic[0].json
}

# SNS posts a SubscriptionConfirmation to the URL (with its token) first; the api verifies
# the SNS signature and confirms it, then verifies every notification the same way. The
# envelope is kept (no raw delivery) because the signature covers it; the SES action
# below puts the full raw message into it.
resource "aws_sns_topic_subscription" "inbound" {
  count                           = local.inbound
  topic_arn                       = aws_sns_topic.inbound[0].arn
  protocol                        = "https"
  endpoint                        = var.inbound_url
  endpoint_auto_confirms          = false
  confirmation_timeout_in_minutes = 5
}

resource "aws_ses_receipt_rule_set" "inbound" {
  count         = local.inbound
  rule_set_name = "${var.name_prefix}-inbound"
}

resource "aws_ses_receipt_rule" "inbound" {
  count         = local.inbound
  name          = "${var.name_prefix}-to-supportdesk"
  rule_set_name = aws_ses_receipt_rule_set.inbound[0].rule_set_name
  recipients    = local.inbound_recipients
  enabled       = true
  scan_enabled  = true
  tls_policy    = "Require"

  s3_action {
    bucket_name       = var.objects_bucket_name
    object_key_prefix = "inbound/"
    position          = 1
  }

  # The SNS action always carries the raw message ("content", Base64) for mail up to
  # 150 KB; larger mail is in S3 under inbound/.
  sns_action {
    topic_arn = aws_sns_topic.inbound[0].arn
    encoding  = "Base64"
    position  = 2
  }

  depends_on = [aws_sns_topic_policy.inbound]
}

resource "aws_ses_active_receipt_rule_set" "inbound" {
  count         = local.inbound
  rule_set_name = aws_ses_receipt_rule_set.inbound[0].rule_set_name
}

resource "aws_route53_record" "mx" {
  count   = var.enable_inbound && var.route53_zone_id != null ? 1 : 0
  zone_id = var.route53_zone_id
  name    = var.domain
  type    = "MX"
  ttl     = 600
  records = ["10 inbound-smtp.${data.aws_region.current.region}.amazonaws.com"]
}
