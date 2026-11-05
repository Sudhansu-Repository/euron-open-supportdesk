/**
 * Canned replies may use placeholders, filled in the browser before the reply is sent so
 * the agent sees exactly what the customer will read:
 *   {{customer.name}}  {{customer.first_name}}  {{customer.email}}
 *   {{agent.name}}  {{agent.first_name}}  {{ticket.number}}  {{company}}
 * Unknown placeholders are left as written, so a typo is visible, not silently blank.
 */
export interface MacroContext {
  customerName?: string | null;
  customerEmail?: string | null;
  agentName?: string | null;
  ticketNumber?: number | null;
  company?: string | null;
}

export const PLACEHOLDERS = [
  "{{customer.first_name}}",
  "{{customer.name}}",
  "{{customer.email}}",
  "{{agent.first_name}}",
  "{{agent.name}}",
  "{{ticket.number}}",
  "{{company}}",
] as const;

function first(name: string | null | undefined): string | null {
  return name ? (name.trim().split(/\s+/)[0] ?? null) : null;
}

export function fillPlaceholders(body: string, ctx: MacroContext): string {
  const values: Record<string, string | null | undefined> = {
    "customer.name": ctx.customerName,
    "customer.first_name": first(ctx.customerName),
    "customer.email": ctx.customerEmail,
    "agent.name": ctx.agentName,
    "agent.first_name": first(ctx.agentName),
    "ticket.number": ctx.ticketNumber != null ? String(ctx.ticketNumber) : null,
    company: ctx.company,
  };
  return body.replace(/\{\{\s*([a-z_.]+)\s*\}\}/gi, (match, key: string) => {
    const v = values[key.toLowerCase()];
    return v ? v : match;
  });
}
