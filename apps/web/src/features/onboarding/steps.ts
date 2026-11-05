/**
 * The first-run checklist on the inbox home. Pure, so the "is this org new" rule is
 * tested: the checklist shows until every step is done or the admin hides it.
 */
export interface OnboardingInput {
  sources: number;
  articles: number;
  widgetConfigured: boolean;
  widgetConversations: number;
  teammates: number;
  invitations: number;
  conversations: number;
  askedTestQuestion: boolean;
}

export interface Step {
  id: "docs" | "widget" | "invite" | "ask";
  title: string;
  body: string;
  action: string;
  href: string;
  done: boolean;
}

export function onboardingSteps(i: OnboardingInput): Step[] {
  return [
    {
      id: "docs",
      title: "Upload your docs",
      body: "PDF, Word, Markdown, a web page or an FAQ CSV. The AI answers only from what you give it.",
      action: "Add knowledge",
      href: "/knowledge?tab=sources",
      done: i.sources + i.articles > 0,
    },
    {
      id: "widget",
      title: "Install the widget",
      body: "Paste one script tag into your site. Customers chat, the AI answers with sources.",
      action: "Get the snippet",
      href: "/settings/inboxes",
      done: i.widgetConfigured || i.widgetConversations > 0,
    },
    {
      id: "invite",
      title: "Invite a teammate",
      body: "Escalated conversations need a person. Invite who answers customers today.",
      action: "Invite",
      href: "/settings/team",
      done: i.teammates > 1 || i.invitations > 0,
    },
    {
      id: "ask",
      title: "Ask a test question",
      body: "See the answer, its sources, the policy decision and what it cost, before a customer does.",
      action: "Try it",
      href: "/knowledge?tab=test",
      done: i.askedTestQuestion || i.conversations > 0,
    },
  ];
}

export function onboardingProgress(steps: Step[]): { done: number; total: number; complete: boolean } {
  const done = steps.filter((s) => s.done).length;
  return { done, total: steps.length, complete: done === steps.length };
}
