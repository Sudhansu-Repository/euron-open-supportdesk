import { describe, expect, it } from "vitest";

import { slaBadge } from "@/lib/sla";

const now = new Date("2026-10-30T12:00:00Z");

describe("SLA badge", () => {
  it("is quiet when nothing is due or the conversation is done", () => {
    expect(slaBadge("ok", null, "open", now).show).toBe(false);
    expect(slaBadge("breached", "2026-10-30T11:00:00Z", "resolved", now).show).toBe(false);
    expect(slaBadge("at_risk", "2026-10-30T12:10:00Z", "closed", now).show).toBe(false);
    expect(slaBadge("none", null, "pending", now).show).toBe(false);
  });
  it("shows the time left while on track", () => {
    const b = slaBadge("ok", "2026-10-30T14:00:00Z", "open", now);
    expect(b).toMatchObject({ show: true, tone: "neutral", label: "2h" });
  });
  it("warns when at risk with the countdown", () => {
    const b = slaBadge("at_risk", "2026-10-30T12:20:00Z", "open", now);
    expect(b).toMatchObject({ show: true, tone: "warning", label: "Due in 20m" });
  });
  it("flags breaches with how overdue", () => {
    expect(slaBadge("breached", "2026-10-30T10:30:00Z", "open", now)).toMatchObject({ tone: "danger", label: "Overdue 1h 30m" });
    expect(slaBadge("breached", null, "open", now)).toMatchObject({ tone: "danger", label: "SLA breached" });
  });
  it("treats a passed due time as breached even before the server flags it", () => {
    expect(slaBadge("ok", "2026-10-30T11:59:00Z", "pending", now).tone).toBe("danger");
  });
});
