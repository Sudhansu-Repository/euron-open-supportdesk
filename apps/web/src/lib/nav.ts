import {
  BarChart3Icon,
  BookOpenIcon,
  Building2Icon,
  CheckCheckIcon,
  CircleDollarSignIcon,
  ClockIcon,
  CpuIcon,
  GaugeIcon,
  InboxIcon,
  KeyRoundIcon,
  LightbulbIcon,
  MessageSquareTextIcon,
  ScaleIcon,
  ScrollTextIcon,
  ShieldCheckIcon,
  UsersIcon,
  UsersRoundIcon,
  WebhookIcon,
  type LucideIcon,
} from "lucide-react";

export type Audience = "agent" | "admin";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  audience: Audience;
  /** Short line under the settings page title. */
  description?: string;
}

export interface NavGroup {
  label: string;
  items: NavItem[];
  /** Advanced groups start collapsed; core daily surfaces are always open. */
  collapsible?: boolean;
}

export const SETTINGS_ITEMS: NavItem[] = [
  { href: "/settings/organisation", label: "Organisation", icon: Building2Icon, audience: "admin", description: "Your company name, brand colour and help center." },
  { href: "/settings/team", label: "Team and agents", icon: UsersRoundIcon, audience: "admin", description: "Agents, roles, capacity, invitations and teams." },
  { href: "/settings/inboxes", label: "Inboxes and widget", icon: MessageSquareTextIcon, audience: "admin", description: "Design the chat widget, install it, and connect email." },
  { href: "/settings/ai", label: "AI provider", icon: CpuIcon, audience: "admin", description: "Which model answers, and where it runs." },
  { href: "/settings/policy", label: "Policy and escalation", icon: ShieldCheckIcon, audience: "admin", description: "When the AI may answer, and when a person takes over." },
  { href: "/settings/budgets", label: "Budgets and Token Saver", icon: GaugeIcon, audience: "admin", description: "Hard token and cost limits, and the caches that avoid spending." },
  { href: "/settings/prices", label: "Model prices", icon: CircleDollarSignIcon, audience: "admin", description: "Price per million tokens, used for every cost figure." },
  { href: "/settings/sla", label: "SLA policies", icon: ClockIcon, audience: "admin", description: "Response and resolution targets per priority." },
  { href: "/settings/macros", label: "Canned replies", icon: ScaleIcon, audience: "admin", description: "Reusable answers agents insert with one click." },
  { href: "/settings/api-keys", label: "API keys", icon: KeyRoundIcon, audience: "admin", description: "Keys for the REST API, read or write." },
  { href: "/settings/webhooks", label: "Webhooks", icon: WebhookIcon, audience: "admin", description: "Signed events to your own systems." },
  { href: "/settings/audit", label: "Audit log", icon: ScrollTextIcon, audience: "admin", description: "Every change, who made it and when." },
];

export const NAV: NavGroup[] = [
  {
    label: "Support",
    items: [
      { href: "/inbox", label: "Inbox", icon: InboxIcon, audience: "agent" },
      { href: "/approvals", label: "Approvals", icon: CheckCheckIcon, audience: "agent" },
      { href: "/customers", label: "Customers", icon: UsersIcon, audience: "agent" },
    ],
  },
  {
    label: "Knowledge",
    items: [
      { href: "/knowledge", label: "Knowledge", icon: BookOpenIcon, audience: "agent" },
      { href: "/gaps", label: "Knowledge gaps", icon: LightbulbIcon, audience: "agent" },
    ],
  },
  {
    label: "Insights",
    items: [{ href: "/analytics", label: "Analytics", icon: BarChart3Icon, audience: "agent" }],
  },
  { label: "Settings", items: SETTINGS_ITEMS, collapsible: true },
];

export const NAV_ITEMS: NavItem[] = NAV.flatMap((g) => g.items);

/** Whether someone with this role sees an item. */
export function visibleTo(item: NavItem, role: string | null | undefined): boolean {
  if (!role) return false;
  if (item.audience === "agent") return true;
  return role === "admin" || role === "owner";
}

/** The nav item a path belongs to: the longest matching prefix. */
export function activeNavItem(pathname: string): NavItem | undefined {
  const path = pathname.replace(/\/+$/, "") || "/";
  return NAV_ITEMS.filter((i) => path === i.href || path.startsWith(`${i.href}/`)).sort((a, b) => b.href.length - a.href.length)[0];
}

export function isActive(item: NavItem, pathname: string): boolean {
  return activeNavItem(pathname)?.href === item.href;
}

/** A collapsible group opens by itself when the current page lives in it. */
export function groupContains(group: NavGroup, pathname: string): boolean {
  return group.items.some((i) => isActive(i, pathname));
}
