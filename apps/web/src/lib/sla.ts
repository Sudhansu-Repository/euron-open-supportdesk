import { formatDuration } from "./format";
import type { Tone } from "./labels";

/**
 * The SLA badge on a conversation. The API computes `sla_state` (ok, at_risk, breached)
 * and the next due time; the badge adds the countdown or the overdue time, and stays
 * quiet when nothing is due (resolved, closed, or no policy).
 */
export interface SlaBadge {
  show: boolean;
  tone: Tone;
  label: string;
  /** Sentence for a tooltip or screen readers. */
  detail: string;
}

const NONE: SlaBadge = { show: false, tone: "neutral", label: "", detail: "No SLA timer is running." };

export function slaBadge(
  state: string | null | undefined,
  dueAt: string | null | undefined,
  status: string,
  now: Date = new Date(),
): SlaBadge {
  if (status === "resolved" || status === "closed") return NONE;
  const due = dueAt ? new Date(dueAt) : null;
  const ms = due && !Number.isNaN(due.getTime()) ? due.getTime() - now.getTime() : null;
  if (state === "breached" || (ms != null && ms < 0)) {
    const over = ms != null ? formatDuration(-ms / 1000) : null;
    return {
      show: true,
      tone: "danger",
      label: over ? `Overdue ${over}` : "SLA breached",
      detail: over ? `The SLA target passed ${over} ago.` : "The SLA target has passed.",
    };
  }
  if (state === "at_risk") {
    const left = ms != null ? formatDuration(ms / 1000) : null;
    return {
      show: true,
      tone: "warning",
      label: left ? `Due in ${left}` : "SLA at risk",
      detail: left ? `Less than a quarter of the SLA time is left: due in ${left}.` : "The SLA target is close.",
    };
  }
  if (ms != null) {
    const left = formatDuration(ms / 1000);
    return { show: true, tone: "neutral", label: left, detail: `On track: the next SLA target is due in ${left}.` };
  }
  return NONE;
}
