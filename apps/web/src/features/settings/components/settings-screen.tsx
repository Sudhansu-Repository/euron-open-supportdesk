"use client";

import { PageHeader } from "@/components/page-header";
import { usePermissions } from "@/features/auth/api";
import { SETTINGS_ITEMS } from "@/lib/nav";

import { AiSection } from "./ai-section";
import { ApiKeysSection } from "./api-keys-section";
import { AuditSection } from "./audit-section";
import { BudgetsSection } from "./budgets-section";
import { InboxesSection } from "./inboxes-section";
import { MacrosSection } from "./macros-section";
import { OrganisationSection } from "./organisation-section";
import { PolicySection } from "./policy-section";
import { PricesSection } from "./prices-section";
import { AdminOnly } from "./shared";
import { SlaSection } from "./sla-section";
import { TeamSection } from "./team-section";
import { WebhooksSection } from "./webhooks-section";

const SECTIONS: Record<string, () => React.ReactNode> = {
  organisation: () => <OrganisationSection />,
  team: () => <TeamSection />,
  inboxes: () => <InboxesSection />,
  ai: () => <AiSection />,
  policy: () => <PolicySection />,
  budgets: () => <BudgetsSection />,
  prices: () => <PricesSection />,
  sla: () => <SlaSection />,
  macros: () => <MacrosSection />,
  "api-keys": () => <ApiKeysSection />,
  webhooks: () => <WebhooksSection />,
  audit: () => <AuditSection />,
};

export function SettingsScreen({ section }: { section: string }) {
  const { admin, user } = usePermissions();
  const item = SETTINGS_ITEMS.find((i) => i.href === `/settings/${section}`);
  const render = SECTIONS[section];
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader eyebrow={<span className="text-[11px] font-semibold tracking-[0.08em] text-subtle uppercase">Settings</span>} title={item?.label ?? "Settings"} description={item?.description} />
      {user && !admin ? <AdminOnly /> : render ? render() : null}
    </div>
  );
}
