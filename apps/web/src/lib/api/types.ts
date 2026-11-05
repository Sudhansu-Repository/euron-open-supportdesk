/**
 * Named aliases over the generated OpenAPI types (`pnpm gen:api`). Nothing here is
 * hand-written: every shape comes from `schema.d.ts`, which is generated from
 * docs/api/openapi.yaml.
 */
import type { components, operations } from "./schema";

type S = components["schemas"];

export type User = S["UserOut"];
export type UserPatch = S["UserPatch"];
export type MePatch = S["MePatch"];
export type SignIn = S["SignInOut"];
export type Session = S["SessionOut"];
export type InvitationPreview = S["InvitationPreview"];
export type Invitation = S["InvitationOut"];
export type InviteIn = S["InviteIn"];

export type Settings = S["SettingsOut"];
export type SettingsPatch = S["SettingsPatch"];
export type Brand = S["Brand"];
export type AiConfig = S["AiConfig"];
export type AiTestResult = S["AiTestResult"];
export type Policy = S["Policy"];
export type Budgets = S["Budgets"];
export type TokenSaver = S["TokenSaver"];
export type Team = S["TeamOut"];
export type TeamIn = S["TeamIn"];
export type Price = S["PriceOut"];
export type PriceIn = S["PriceIn"];

export type Ticket = S["TicketOut"];
export type TicketDetail = S["TicketDetail"];
export type TicketPage = S["Page_TicketOut_"];
export type TicketPatch = S["TicketPatch"];
export type TicketCreate = S["TicketCreate"];
export type BulkPatch = S["BulkPatch"];
export type ViewCounts = S["ViewCounts"];
export type Message = S["MessageOut"];
export type Citation = S["Citation"];
export type TicketEvent = S["EventOut"];
export type ReplyIn = S["ReplyIn"];
export type DraftIn = S["DraftIn"];
export type DraftOut = S["DraftOut"];
export type Macro = S["MacroOut"];
export type MacroIn = S["MacroIn"];
export type SlaPolicy = S["SlaPolicyOut"];
export type SlaPolicyIn = S["SlaPolicyIn"];

export type Customer = S["CustomerOut"];
export type CustomerDetail = S["CustomerDetail"];
export type CustomerPatch = S["CustomerPatch"];

export type Inbox = S["InboxOut"];
export type InboxPatch = S["InboxPatch"];
export type InboxSaved = S["InboxSaved"];

export type WidgetSession = S["WidgetSessionOut"];
export type WidgetConfig = S["WidgetConfig"];
export type WidgetConversation = S["WidgetConversation"];
export type PortalSession = S["PortalSessionOut"];
export type PublicMessage = S["PublicMessage"];
export type PublicCitation = S["PublicCitation"];
export type PortalTicket = S["PortalTicket"];
export type PortalTicketDetail = S["PortalTicketDetail"];

export type KnowledgeStats = S["KnowledgeStats"];
export type Source = S["SourceOut"];
export type Article = S["ArticleOut"];
export type ArticleIn = S["ArticleIn"];
export type ArticleBrief = S["ArticleBrief"];
export type ArticleDraft = S["ArticleDraft"];
export type Playground = S["PlaygroundOut"];
export type Passage = S["Passage"];
export type HelpCenter = S["HelpCenter"];

export type Gap = S["GapOut"];
export type GapDetail = S["GapDetail"];

export type ApiKey = S["ApiKeyOut"];
export type ApiKeyCreated = S["ApiKeyCreated"];
export type Webhook = S["WebhookOut"];
export type WebhookCreated = S["WebhookCreated"];
export type WebhookPatch = S["WebhookPatch"];
export type Delivery = S["DeliveryOut"];
export type AuditEntry = S["AuditOut"];
export type AuditPage = S["Page_AuditOut_"];

export type TicketStatus = NonNullable<TicketPatch["status"]>;
export type Priority = NonNullable<TicketPatch["priority"]>;
export type PolicyMode = NonNullable<Policy["mode"]>;
export type AiProvider = NonNullable<AiConfig["provider"]>;
export type Embedder = NonNullable<AiConfig["embedder"]>;
export type Tone = NonNullable<DraftIn["tone"]>;
export type Role = NonNullable<UserPatch["role"]>;
export type Availability = NonNullable<MePatch["availability"]>;

/** Query parameters of the ticket list, straight from the contract. */
export type TicketQuery = NonNullable<operations["list_tickets_api_v1_tickets_get"]["parameters"]["query"]>;
export type TicketView = NonNullable<TicketQuery["view"]>;
