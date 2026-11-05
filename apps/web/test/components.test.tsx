// @vitest-environment jsdom
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { citationLabel, Citations, safeHref } from "@/components/citations";
import { Markdown, safeUrl } from "@/components/markdown";
import { TooltipProvider } from "@/components/ui/tooltip";
import { DecisionPanel, ScoreBar } from "@/features/tickets/components/decision-panel";
import { CustomerThread } from "@/features/widget/components/customer-thread";
import { WidgetChat, type WidgetChatProps } from "@/features/widget/components/widget-chat";
import { readAiMeta } from "@/lib/ai-meta";
import type { PublicMessage } from "@/lib/api/types";

function msg(author: string, body: string, extra: Partial<PublicMessage> = {}): PublicMessage {
  return { id: `${author}-${body}`, author_type: author, body, citations: [], feedback: null, created_at: "2026-10-30T10:00:00Z", ...extra };
}

describe("markdown", () => {
  it("renders GitHub-flavoured markdown", () => {
    const { container } = render(<Markdown source={"| a | b |\n|---|---|\n| 1 | 2 |\n\n```\nprint(1)\n```"} />);
    expect(container.querySelector("table")).not.toBeNull();
    expect(container.querySelector("pre code")?.textContent).toContain("print(1)");
  });
  it("never renders raw HTML", () => {
    const { container } = render(<Markdown source={'Hi <script>alert(1)</script><img src=x onerror="alert(1)"><iframe src="https://x.test"></iframe>'} />);
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("iframe")).toBeNull();
    expect(container.querySelector("img[onerror]")).toBeNull();
  });
  it("drops javascript: and data: links", () => {
    const { container } = render(<Markdown source={"[x](javascript:alert(1)) [y](data:text/html,hi) [z](https://ok.example)"} />);
    const hrefs = [...container.querySelectorAll("a")].map((a) => a.getAttribute("href") ?? "");
    expect(hrefs.some((h) => h.startsWith("javascript"))).toBe(false);
    expect(hrefs).toContain("https://ok.example");
    expect(safeUrl("vbscript:x")).toBe("");
  });
});

describe("citations", () => {
  it("shows title > heading and links only http(s) sources", () => {
    expect(citationLabel({ title: "Billing", heading: "Refunds" })).toBe("Billing > Refunds");
    expect(citationLabel({ title: "Billing", heading: "Billing" })).toBe("Billing");
    expect(safeHref("javascript:alert(1)")).toBeNull();
    render(
      <Citations
        citations={[
          { title: "Billing", heading: "Refunds", url: "https://docs.example/billing" },
          { title: "FAQ", heading: null, url: "javascript:alert(1)" },
        ]}
      />,
    );
    expect(screen.getByText("Billing > Refunds").closest("a")?.getAttribute("href")).toBe("https://docs.example/billing");
    expect(screen.getByText("FAQ").closest("a")).toBeNull();
  });
});

describe("decision panel", () => {
  it("explains the policy decision in words, with cost and relevance against the threshold", () => {
    const d = readAiMeta({
      action: "approval",
      reasons: ["sensitive_intent"],
      method: "model",
      grounded: true,
      triage: { intent: "refund", category: "billing", sentiment: "negative", priority: "high", sensitive: ["refund"], source: "rules" },
      best_relevance: 0.72,
      tokens: 812,
      cost_usd: "0.0004",
      timings_ms: { retrieve: 14, generate: 820 },
    });
    render(
      <TooltipProvider>
        <DecisionPanel decision={d} threshold={0.35} />
      </TooltipProvider>,
    );
    expect(screen.getByText("Held for approval")).toBeTruthy();
    expect(screen.getByText("Sensitive request")).toBeTruthy();
    expect(screen.getAllByText("Refund").length).toBeGreaterThan(0);
    expect(screen.getByText("$0.0004")).toBeTruthy();
    expect(screen.getByRole("meter", { name: "Best relevance" }).getAttribute("aria-valuenow")).toBe("0.72");
  });
  it("marks scores below the threshold", () => {
    const { container } = render(<ScoreBar value={0.2} threshold={0.35} label="Relevance" />);
    expect(container.querySelector(".bg-faint")).not.toBeNull();
  });
});

describe("customer thread", () => {
  it("shows AI answers with sources, handoffs and agent names, and takes a vote", () => {
    const onVote = vi.fn();
    render(
      <ol>
        <CustomerThread
          messages={[
            msg("customer", "Where is my order?"),
            msg("ai", "It ships in 2 days.", { citations: [{ title: "Shipping", heading: "Times", url: null }] }),
            msg("system", "A teammate will reply here."),
            msg("agent", "Hi, Sam here.", { author_name: "Sam" }),
          ]}
          accent="#4f46e5"
          accentText="#ffffff"
          votes={{}}
          onVote={onVote}
          company="Acme"
        />
      </ol>,
    );
    expect(screen.getByText("Acme assistant")).toBeTruthy();
    expect(screen.getByText("Shipping > Times")).toBeTruthy();
    expect(screen.getByText("A teammate will reply here.")).toBeTruthy();
    expect(screen.getByText("Sam")).toBeTruthy();
    fireEvent.click(screen.getByLabelText("This did not help"));
    expect(onVote).toHaveBeenCalledWith("ai-It ships in 2 days.", false);
  });
});

describe("widget chat", () => {
  const base: WidgetChatProps = {
    title: "Acme support",
    greeting: "Hi there!",
    company: "Acme",
    accent: "#4f46e5",
    accentText: "#ffffff",
    suggestions: ["Track my order"],
    agentsOnline: true,
    aiEnabled: true,
    messages: [],
    typing: false,
    sending: false,
    votes: {},
    canAskHuman: false,
    showEmail: false,
    emailSent: false,
    showRating: false,
    rated: false,
    onSend: vi.fn(),
    onVote: vi.fn(),
    onHuman: vi.fn(),
    onEmail: vi.fn(),
    onRate: vi.fn(),
  };
  it("greets, offers suggestions, and sends on Enter", () => {
    const onSend = vi.fn();
    render(<WidgetChat {...base} onSend={onSend} />);
    expect(screen.getByText("Hi there!")).toBeTruthy();
    fireEvent.click(screen.getByText("Track my order"));
    expect(onSend).toHaveBeenCalledWith("Track my order");
    const box = screen.getByLabelText("Your message");
    fireEvent.change(box, { target: { value: "  Hello  " } });
    fireEvent.keyDown(box, { key: "Enter" });
    expect(onSend).toHaveBeenLastCalledWith("Hello");
  });
  it("offers a person, the email form and the rating when they apply", () => {
    const onHuman = vi.fn();
    const onEmail = vi.fn();
    const { rerender } = render(<WidgetChat {...base} messages={[msg("customer", "hi"), msg("ai", "hello")]} canAskHuman onHuman={onHuman} />);
    fireEvent.click(screen.getByText("Talk to a person"));
    expect(onHuman).toHaveBeenCalled();
    rerender(<WidgetChat {...base} messages={[msg("customer", "hi")]} showEmail onEmail={onEmail} />);
    fireEvent.change(screen.getByLabelText("Your email"), { target: { value: "me@example.com" } });
    fireEvent.click(screen.getByText("Email me the answer"));
    expect(onEmail).toHaveBeenCalledWith("me@example.com", "");
    rerender(<WidgetChat {...base} messages={[msg("customer", "hi")]} showRating />);
    expect(screen.getByText("How did we do?")).toBeTruthy();
  });
});
