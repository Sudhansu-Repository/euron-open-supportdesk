import { describe, expect, it } from "vitest";

import { onboardingProgress, onboardingSteps } from "@/features/onboarding/steps";
import { normalizeOrigin, readAppearance } from "@/features/settings/components/inboxes-section";
import { acceptedFile, sourceStatus } from "@/features/knowledge/components/sources-tab";
import { cleanFilters } from "@/features/tickets/api";
import { messageView } from "@/features/tickets/components/message-item";
import { parseSearch, stepSelection, viewSpec, VIEWS } from "@/features/tickets/views";
import { fillPlaceholders } from "@/lib/macros";
import { passwordIssues, passwordMessage } from "@/lib/password";

describe("inbox views and search", () => {
  it("covers every view of the API, defaulting to All open", () => {
    expect(VIEWS.map((v) => v.id)).toEqual(["all", "mine", "unassigned", "ai", "approvals", "escalated", "sla", "resolved"]);
    expect(viewSpec("nope").id).toBe("all");
    expect(viewSpec("approvals").count).toBe("approvals");
    for (const v of VIEWS) expect(v.empty.body.length).toBeGreaterThan(20);
  });
  it("reads #123 as a conversation number", () => {
    expect(parseSearch("#123")).toEqual({ kind: "number", value: 123 });
    expect(parseSearch(" 42 ")).toEqual({ kind: "number", value: 42 });
    expect(parseSearch("refund #2")).toEqual({ kind: "text", value: "refund #2" });
    expect(parseSearch("   ")).toBeNull();
  });
  it("moves with j and k, staying put at the ends", () => {
    const ids = ["a", "b", "c"];
    expect(stepSelection(ids, null, 1)).toBe("a");
    expect(stepSelection(ids, "a", 1)).toBe("b");
    expect(stepSelection(ids, "c", 1)).toBe("c");
    expect(stepSelection(ids, "a", -1)).toBe("a");
    expect(stepSelection(ids, "gone", -1)).toBe("a");
    expect(stepSelection([], "a", 1)).toBeNull();
  });
  it("drops empty filters so equal filter sets share a cache entry", () => {
    expect(cleanFilters({ view: "all", status: "", q: undefined, priority: null })).toEqual({ view: "all" });
  });
});

describe("messages in the transcript", () => {
  it("draws notes, drafts, approvals and discards distinctly", () => {
    expect(messageView({ author_type: "agent", kind: "note", status: "sent" })).toBe("note");
    expect(messageView({ author_type: "ai", kind: "reply", status: "pending" })).toBe("pending");
    expect(messageView({ author_type: "ai", kind: "draft", status: "draft" })).toBe("draft");
    expect(messageView({ author_type: "ai", kind: "reply", status: "rejected" })).toBe("discarded");
    expect(messageView({ author_type: "ai", kind: "draft", status: "discarded" })).toBe("discarded");
    expect(messageView({ author_type: "system", kind: "reply", status: "sent" })).toBe("system");
    expect(messageView({ author_type: "customer", kind: "reply", status: "sent" })).toBe("customer");
    expect(messageView({ author_type: "ai", kind: "reply", status: "sent" })).toBe("ai");
    expect(messageView({ author_type: "agent", kind: "reply", status: "sent" })).toBe("agent");
  });
});

describe("canned reply placeholders", () => {
  it("fills known placeholders and leaves unknown ones visible", () => {
    const out = fillPlaceholders("Hi {{customer.first_name}}, this is {{ agent.name }} about #{{ticket.number}} at {{company}}. {{oops}}", {
      customerName: "Maria Lopez",
      agentName: "Sam Lee",
      ticketNumber: 42,
      company: "Acme",
    });
    expect(out).toBe("Hi Maria, this is Sam Lee about #42 at Acme. {{oops}}");
    expect(fillPlaceholders("{{customer.email}}", {})).toBe("{{customer.email}}");
  });
});

describe("password rules", () => {
  it("lists every missing piece the API would refuse", () => {
    expect(passwordIssues("short")).toEqual(["at least 10 characters", "upper and lower case letters", "a digit"]);
    expect(passwordMessage("Longenough1")).toBeNull();
    expect(passwordMessage("longenough1")).toBe("Use upper and lower case letters.");
    expect(passwordMessage("abc")).toBe("Use at least 10 characters, upper and lower case letters and a digit.");
  });
});

describe("onboarding checklist", () => {
  const base = { sources: 0, articles: 0, widgetConfigured: false, widgetConversations: 0, teammates: 1, invitations: 0, conversations: 0, askedTestQuestion: false };
  it("starts with every step open for a new organisation", () => {
    const steps = onboardingSteps(base);
    expect(steps.map((s) => s.id)).toEqual(["docs", "widget", "invite", "ask"]);
    expect(onboardingProgress(steps)).toEqual({ done: 0, total: 4, complete: false });
    for (const s of steps) expect(s.href.startsWith("/")).toBe(true);
  });
  it("ticks steps off from real data", () => {
    const steps = onboardingSteps({ ...base, articles: 1, widgetConfigured: true, invitations: 1, askedTestQuestion: true });
    expect(onboardingProgress(steps).complete).toBe(true);
    expect(onboardingSteps({ ...base, conversations: 3 }).find((s) => s.id === "ask")?.done).toBe(true);
    expect(onboardingSteps({ ...base, teammates: 2 }).find((s) => s.id === "invite")?.done).toBe(true);
  });
});

describe("settings helpers", () => {
  it("normalises allowed origins like the API", () => {
    expect(normalizeOrigin("https://WWW.Example.com/path?q=1")).toBe("https://www.example.com");
    expect(normalizeOrigin("http://localhost:4815")).toBe("http://localhost:4815");
    expect(normalizeOrigin("ftp://x.test")).toBeNull();
    expect(normalizeOrigin("example.com")).toBeNull();
  });
  it("reads widget appearance with safe defaults", () => {
    expect(readAppearance({ color: "javascript:x", position: "left", suggestions: ["a", 2] })).toMatchObject({ color: "#4f46e5", position: "left", suggestions: ["a"], title: "Support" });
  });
  it("accepts the documented upload types only", () => {
    for (const f of ["a.pdf", "b.DOCX", "c.md", "d.txt", "e.html", "faq.csv"]) expect(acceptedFile(f)).toBe(true);
    expect(acceptedFile("virus.exe")).toBe(false);
    expect(acceptedFile("noext")).toBe(false);
  });
  it("labels source statuses", () => {
    expect(sourceStatus("ready").tone).toBe("success");
    expect(sourceStatus("processing").label).toBe("Indexing");
    expect(sourceStatus("failed").tone).toBe("danger");
    expect(sourceStatus("queued").label).toBe("Queued");
  });
});


describe("unverified contact email", () => {
  it("reads the address left in the widget's email form, and nothing else", async () => {
    const { contactEmail } = await import("@/lib/contact");
    expect(contactEmail({ contact_email: " lee@example.com " })).toBe("lee@example.com");
    expect(contactEmail({ contact_email: "nope" })).toBeNull();
    expect(contactEmail({})).toBeNull();
    expect(contactEmail(null)).toBeNull();
  });
});
