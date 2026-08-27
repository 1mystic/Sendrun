/**
 * The API client — one function per real backend endpoint
 * (services/api/routers/*.py). Every type here matches the backend's actual
 * Pydantic response model field-for-field; see the comment above each
 * function group for which router file to check if the shapes ever diverge.
 *
 * `NEXT_PUBLIC_API_URL` unset -> every call is live-blocked in favor of the
 * mock data in mock.ts (see `useMocks` below), so pages that haven't been
 * wired to call these functions yet are unaffected either way. Once set,
 * every function here makes a real `fetch` with credentials included (the
 * session cookie is httponly + samesite=lax, set by the backend on
 * sign-in — see packages/shared/auth.py).
 */

import {
  CAMPAIGNS,
  CONTACTS,
  MOCK_GROUPS,
  MOCK_GROUP_CONTACTS,
  PREFLIGHT,
  ORG,
  RECIPIENT_GROUPS,
} from "./mock";
import type { Campaign, Contact, PreflightReport, ProgressSnapshot } from "./types";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";
export const useMocks = API === "";

class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(`${status}: ${detail}`);
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    ...init,
    credentials: "include", // send the session cookie — required by every org-scoped route
    headers: { "Content-Type": "application/json", ...init.headers },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // non-JSON error body — keep statusText
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined });
}
function put<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "PUT", body: JSON.stringify(body) });
}
function del<T>(path: string): Promise<T> {
  return request<T>(path, { method: "DELETE" });
}

// ─────────────────────────────────────────────────────────────────────────
// Auth — services/api/routers/auth.py
// ─────────────────────────────────────────────────────────────────────────

export interface UserOut {
  id: string;
  name: string;
  email: string;
}

export async function signUp(name: string, email: string, password: string): Promise<UserOut> {
  return post<UserOut>("/api/auth/signup", { name, email, password });
}

export async function signIn(email: string, password: string): Promise<UserOut> {
  return post<UserOut>("/api/auth/signin", { email, password });
}

export async function signOut(): Promise<void> {
  return post<void>("/api/auth/signout");
}

export async function getCurrentUser(): Promise<UserOut | null> {
  if (useMocks) return { id: "mock-user", name: "You", email: "you@example.com" };
  return request<UserOut | null>("/api/auth/me");
}

// ─────────────────────────────────────────────────────────────────────────
// Organizations — services/api/routers/organizations.py
// ─────────────────────────────────────────────────────────────────────────

export interface OrgOut {
  id: string;
  name: string;
  slug: string;
  role: string;
  from_address: string | null;
  from_name: string | null;
  reply_to_address: string | null;
}

export interface MemberOut {
  user_id: string;
  name: string;
  email: string;
  role: string;
}

export async function createOrganization(name: string): Promise<OrgOut> {
  return post<OrgOut>("/api/organizations", { name });
}

export async function listMyOrganizations(): Promise<OrgOut[]> {
  if (useMocks) {
    return [{
      id: "mock-org", name: ORG.name, slug: "mock-org", role: ORG.role,
      from_address: null, from_name: null, reply_to_address: null,
    }];
  }
  return request<OrgOut[]>("/api/organizations");
}

export async function listMembers(orgId: string): Promise<MemberOut[]> {
  return request<MemberOut[]>(`/api/organizations/${orgId}/members`);
}

export async function inviteMember(
  orgId: string,
  email: string,
  role: string,
): Promise<{ status: string; email: string; role: string }> {
  return post(`/api/organizations/${orgId}/invites`, { email, role });
}

// ─────────────────────────────────────────────────────────────────────────
// Contacts — services/api/routers/contacts.py
// ─────────────────────────────────────────────────────────────────────────

export interface ContactOut {
  id: string;
  email: string;
  name: string | null;
  fields: Record<string, string>;
  tags: string[];
  suppressed: boolean;
}

export interface SmartFilter {
  tags?: string[];
  group_id?: string | null;
  exclude_suppressed?: boolean;
  search?: string | null;
}

export async function createContact(
  orgId: string,
  body: { email: string; name?: string; fields?: Record<string, string>; tags?: string[] },
): Promise<ContactOut> {
  return post<ContactOut>(`/api/organizations/${orgId}/contacts`, body);
}

export async function listContactsLive(
  orgId: string,
  params?: { tag?: string[]; search?: string },
): Promise<ContactOut[]> {
  if (useMocks) {
    return CONTACTS.map((c) => ({
      id: c.id, email: c.email, name: c.name, fields: {}, tags: c.tags, suppressed: false,
    }));
  }
  const qs = new URLSearchParams();
  params?.tag?.forEach((t) => qs.append("tag", t));
  if (params?.search) qs.set("search", params.search);
  const suffix = qs.toString() ? `?${qs}` : "";
  return request<ContactOut[]>(`/api/organizations/${orgId}/contacts${suffix}`);
}

export async function resolveRecipients(orgId: string, filter: SmartFilter): Promise<string[]> {
  return post<string[]>(`/api/organizations/${orgId}/contacts/resolve`, filter);
}

export async function deleteContact(orgId: string, contactId: string): Promise<void> {
  return del<void>(`/api/organizations/${orgId}/contacts/${contactId}`);
}

// ─────────────────────────────────────────────────────────────────────────
// Groups / mailing lists — services/api/routers/groups.py
// ─────────────────────────────────────────────────────────────────────────

export interface GroupOut {
  id: string;
  name: string;
  contact_count: number;
}

export interface GroupDetailOut extends GroupOut {
  contacts: ContactOut[];
}

export interface ImportRow {
  values: Record<string, string>;
}

export interface BulkImportRequest {
  email_column: string;
  name_column: string | null;
  rows: ImportRow[];
}

export interface BulkImportResult {
  created: number;
  updated: number;
  skipped: Array<{ row_index: number; reason: string }>;
  group_contact_count: number;
}

export async function createGroup(orgId: string, name: string): Promise<GroupOut> {
  if (useMocks) {
    const group: GroupOut = { id: `mock-group-${Date.now()}`, name, contact_count: 0 };
    MOCK_GROUPS.push(group);
    return group;
  }
  return post<GroupOut>(`/api/organizations/${orgId}/groups`, { name });
}

export async function listGroups(orgId: string): Promise<GroupOut[]> {
  if (useMocks) return MOCK_GROUPS;
  return request<GroupOut[]>(`/api/organizations/${orgId}/groups`);
}

export async function getGroup(orgId: string, groupId: string): Promise<GroupDetailOut> {
  if (useMocks) {
    const group = MOCK_GROUPS.find((g) => g.id === groupId);
    if (!group) throw new ApiError(404, "Group not found");
    return { ...group, contacts: MOCK_GROUP_CONTACTS[groupId] ?? [] };
  }
  return request<GroupDetailOut>(`/api/organizations/${orgId}/groups/${groupId}`);
}

export async function deleteGroup(orgId: string, groupId: string): Promise<void> {
  if (useMocks) {
    const idx = MOCK_GROUPS.findIndex((g) => g.id === groupId);
    if (idx !== -1) MOCK_GROUPS.splice(idx, 1);
    delete MOCK_GROUP_CONTACTS[groupId];
    return;
  }
  return del<void>(`/api/organizations/${orgId}/groups/${groupId}`);
}

export async function importContactsToGroup(
  orgId: string,
  groupId: string,
  body: BulkImportRequest,
): Promise<BulkImportResult> {
  if (useMocks) {
    const group = MOCK_GROUPS.find((g) => g.id === groupId);
    const created = body.rows.length;
    if (group) group.contact_count += created;
    return { created, updated: 0, skipped: [], group_contact_count: group?.contact_count ?? created };
  }
  return post<BulkImportResult>(`/api/organizations/${orgId}/groups/${groupId}/import`, body);
}

// ─────────────────────────────────────────────────────────────────────────
// Templates — services/api/routers/templates.py
// ─────────────────────────────────────────────────────────────────────────

export interface TemplateVersionOut {
  version: number;
  subject: string;
  html_body: string;
  text_body: string | null;
  variables: string[];
}

export interface TemplateOut {
  id: string;
  name: string;
  current_version: number;
  archived: boolean;
  latest: TemplateVersionOut;
}

export interface LinkCheckOut {
  url: string;
  ok: boolean;
  reason: string;
}

export interface PreviewOut {
  subject: string;
  html_body: string;
  text_body: string | null;
  missing_variables: string[];
  is_complete: boolean;
  links: LinkCheckOut[];
}

export async function createTemplate(
  orgId: string,
  body: { name: string; subject: string; html_body: string; text_body?: string; variables: string[] },
): Promise<TemplateOut> {
  return post<TemplateOut>(`/api/organizations/${orgId}/templates`, body);
}

export async function listTemplates(orgId: string): Promise<TemplateOut[]> {
  if (useMocks) {
    return [{
      id: "mock-template", name: "Default", current_version: 1, archived: false,
      latest: {
        version: 1, subject: "", html_body: "", text_body: null, variables: [],
      },
    }];
  }
  return request<TemplateOut[]>(`/api/organizations/${orgId}/templates`);
}

export async function getTemplate(orgId: string, templateId: string): Promise<TemplateOut> {
  return request<TemplateOut>(`/api/organizations/${orgId}/templates/${templateId}`);
}

export async function updateTemplate(
  orgId: string,
  templateId: string,
  body: { name: string; subject: string; html_body: string; text_body?: string; variables: string[] },
): Promise<TemplateOut> {
  return put<TemplateOut>(`/api/organizations/${orgId}/templates/${templateId}`, body);
}

export async function archiveTemplate(orgId: string, templateId: string): Promise<TemplateOut> {
  return del<TemplateOut>(`/api/organizations/${orgId}/templates/${templateId}`);
}

export async function previewTemplate(
  orgId: string,
  templateId: string,
  contactId: string,
  overrides?: { subject?: string; html_body?: string; text_body?: string; variables?: string[] },
): Promise<PreviewOut> {
  return post<PreviewOut>(`/api/organizations/${orgId}/templates/${templateId}/preview`, {
    contact_id: contactId,
    ...overrides,
  });
}

// ─────────────────────────────────────────────────────────────────────────
// Campaigns — services/api/routers/campaigns.py
// ─────────────────────────────────────────────────────────────────────────

export interface CampaignOut {
  id: string;
  name: string;
  status: string;
  template_id: string;
  template_version: number;
  recipient_count: number | null;
}

export interface ProgressOut {
  campaign_id: string;
  status: string;
  total: number;
  delivered: number;
  sending: number;
  retrying: number;
  failed_permanent: number;
  bounced: number;
  complained: number;
  attempted: number;
}

export async function createCampaign(
  orgId: string,
  body: { name: string; template_id: string; recipients: SmartFilter; event_id?: string; send_rate_per_second?: number },
): Promise<CampaignOut> {
  return post<CampaignOut>(`/api/organizations/${orgId}/campaigns`, body);
}

export async function launchCampaign(
  orgId: string,
  campaignId: string,
  body: { name: string; template_id: string; recipients: SmartFilter },
): Promise<CampaignOut> {
  return post<CampaignOut>(`/api/organizations/${orgId}/campaigns/${campaignId}/launch`, body);
}

export async function cancelCampaign(orgId: string, campaignId: string): Promise<CampaignOut> {
  return post<CampaignOut>(`/api/organizations/${orgId}/campaigns/${campaignId}/cancel`);
}

export async function getCampaignLive(orgId: string, campaignId: string): Promise<CampaignOut> {
  return request<CampaignOut>(`/api/organizations/${orgId}/campaigns/${campaignId}`);
}

export async function getProgress(orgId: string, campaignId: string): Promise<ProgressOut> {
  return request<ProgressOut>(`/api/organizations/${orgId}/campaigns/${campaignId}/progress`);
}

export async function listCampaignsLive(orgId: string): Promise<CampaignOut[]> {
  return request<CampaignOut[]>(`/api/organizations/${orgId}/campaigns`);
}

// Legacy mock-shaped helpers — kept so pages not yet migrated to live data
// (see NEXT.md) keep compiling. New code should call the *Live/typed
// functions above directly.
export async function listCampaigns(): Promise<Campaign[]> {
  return CAMPAIGNS;
}
export async function getCampaign(id: string): Promise<Campaign | undefined> {
  return CAMPAIGNS.find((c) => c.id === id);
}
export async function listContacts(): Promise<Contact[]> {
  return CONTACTS;
}
export async function getContact(id: string): Promise<Contact | undefined> {
  return CONTACTS.find((c) => c.id === id);
}
export async function getPreflight(): Promise<PreflightReport> {
  return PREFLIGHT;
}

// ─────────────────────────────────────────────────────────────────────────
// AI Preflight — services/api/routers/preflight.py
// ─────────────────────────────────────────────────────────────────────────

export interface SpamSignalOut {
  name: string;
  triggered: boolean;
  weight: number;
  explanation: string;
}

export interface CheckOut {
  id: string;
  severity: "ok" | "warn" | "crit";
  title: string;
  detail: string;
  action: string | null;
  meta: string | null;
}

export interface PreflightOutLive {
  spam_risk: number;
  spam_signals: SpamSignalOut[];
  personalization_score: number;
  predicted_delivery: number;
  checks: CheckOut[];
  recipients_missing_variables: Record<string, string[]>;
  recipient_count: number;
}

export async function runPreflight(
  orgId: string,
  templateId: string,
  recipients: SmartFilter,
): Promise<PreflightOutLive> {
  return post<PreflightOutLive>(`/api/organizations/${orgId}/preflight`, {
    template_id: templateId, recipients,
  });
}

// ─────────────────────────────────────────────────────────────────────────
// Agents — services/api/routers/agents.py
// ─────────────────────────────────────────────────────────────────────────

export interface ProposalOut {
  id: string;
  agent_name: string;
  summary: string;
  detail: string;
  action: Record<string, unknown> | null;
  status: string;
  model_used: string;
}

export async function qaReviewTemplate(
  orgId: string,
  templateId: string,
  exampleContactId?: string,
): Promise<ProposalOut> {
  return post<ProposalOut>(`/api/organizations/${orgId}/templates/${templateId}/qa-review`, {
    template_id: templateId, example_contact_id: exampleContactId,
  });
}

export async function analyzeCampaign(orgId: string, campaignId: string): Promise<ProposalOut> {
  return post<ProposalOut>(`/api/organizations/${orgId}/campaigns/${campaignId}/analyze`);
}

// ─────────────────────────────────────────────────────────────────────────
// Live progress stream — SSE, not a plain fetch
// ─────────────────────────────────────────────────────────────────────────

/**
 * Subscribe to live campaign progress over SSE — a 1s poll of the same
 * Postgres aggregate the plain getProgress() call above uses, pushed by the
 * server (services/api/routers/progress.py), not a WebSocket.
 *
 * Returns an unsubscribe function. In mock mode the caller drives its own
 * simulation instead (see the campaign detail page), so this is a no-op.
 */
export function subscribeProgress(
  orgId: string,
  campaignId: string,
  onUpdate: (snapshot: ProgressOut) => void,
): () => void {
  if (useMocks) return () => {};

  const source = new EventSource(
    `${API}/api/organizations/${orgId}/campaigns/${campaignId}/progress/stream`,
    { withCredentials: true },
  );
  source.onmessage = (event) => {
    try {
      onUpdate(JSON.parse(event.data) as ProgressOut);
    } catch {
      // A malformed frame should not tear down the stream; the next tick recovers.
    }
  };
  return () => source.close();
}

export { RECIPIENT_GROUPS };
export type { ProgressSnapshot };

// ─────────────────────────────────────────────────────────────────────────
// Organization settings — services/api/routers/organizations.py
// ─────────────────────────────────────────────────────────────────────────

export interface UpdateOrgFields {
  name: string;
  from_address?: string | null;
  from_name?: string | null;
  reply_to_address?: string | null;
}

export async function updateOrganization(orgId: string, fields: UpdateOrgFields): Promise<OrgOut> {
  return request<OrgOut>(`/api/organizations/${orgId}`, {
    method: "PATCH",
    body: JSON.stringify(fields),
  });
}

// ─────────────────────────────────────────────────────────────────────────
// Audit log / notifications — services/api/routers/organizations.py
// ─────────────────────────────────────────────────────────────────────────

export interface AuditLogOut {
  id: string;
  actor_user_id: string | null;
  actor_kind: string;
  action: string;
  target_type: string | null;
  target_id: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export async function listAuditLog(
  orgId: string,
  params?: { limit?: number; offset?: number },
): Promise<AuditLogOut[]> {
  const qs = new URLSearchParams();
  if (params?.limit) qs.set("limit", String(params.limit));
  if (params?.offset) qs.set("offset", String(params.offset));
  const suffix = qs.toString() ? `?${qs}` : "";
  return request<AuditLogOut[]>(`/api/organizations/${orgId}/audit-log${suffix}`);
}

// ─────────────────────────────────────────────────────────────────────────
// Analytics — services/api/routers/analytics.py
// ─────────────────────────────────────────────────────────────────────────

export interface CampaignStatsOut {
  campaign_id: string;
  name: string;
  sent: number;
  delivered: number;
  bounced: number;
  opened: number;
  clicked: number;
  delivery_rate: number;
  open_rate: number;
  click_rate: number;
}

export interface DomainStatsOut {
  domain: string;
  sent: number;
  delivered: number;
  bounced: number;
  bounce_rate: number;
}

export interface AnalyticsOut {
  total_sent: number;
  delivery_rate: number;
  open_rate: number;
  click_rate: number;
  campaigns: CampaignStatsOut[];
  domains: DomainStatsOut[];
}

export async function getAnalytics(orgId: string): Promise<AnalyticsOut> {
  return request<AnalyticsOut>(`/api/organizations/${orgId}/analytics`);
}

// ─────────────────────────────────────────────────────────────────────────
// Jobs / DLQ inspector — services/api/routers/jobs.py, read-only over the
// durable engine's own `tasks` table
// ─────────────────────────────────────────────────────────────────────────

export interface TaskOut {
  id: string;
  queue: string;
  task_type: string;
  status: string;
  attempt: number;
  max_attempts: number;
  last_error: string | null;
  email_job_id: string | null;
  campaign_id: string | null;
  created_at: string;
  updated_at: string;
}

export async function listDeadLetterTasks(orgId: string): Promise<TaskOut[]> {
  return request<TaskOut[]>(`/api/organizations/${orgId}/jobs/dead-letter`);
}

export async function listInFlightTasks(orgId: string): Promise<TaskOut[]> {
  return request<TaskOut[]>(`/api/organizations/${orgId}/jobs/in-flight`);
}

// ─────────────────────────────────────────────────────────────────────────
// Current-org context — which org_id every /api/organizations/{org_id}/...
// call below should target. Set once at sign-in/org-creation, read by every
// app/ page. Mock mode never needs this (org_id is ignored by useMocks
// branches above), so it's a plain localStorage cache, not app state.
// ─────────────────────────────────────────────────────────────────────────

const ORG_ID_KEY = "sendrun:org_id";

export function setCurrentOrgId(orgId: string): void {
  try {
    localStorage.setItem(ORG_ID_KEY, orgId);
  } catch {
    // storage unavailable (private mode, SSR) — org id just won't persist
  }
}

export function getCurrentOrgId(): string | null {
  if (useMocks) return "mock-org";
  try {
    return localStorage.getItem(ORG_ID_KEY);
  } catch {
    return null;
  }
}

// ─────────────────────────────────────────────────────────────────────────
// Compose draft — carries the in-progress campaign (template id, name,
// recipient filter) across the compose -> preflight -> approve steps, which
// are three separate pages/routes. sessionStorage, not component state,
// since a full navigation unmounts the compose page.
// ─────────────────────────────────────────────────────────────────────────

const DRAFT_KEY = "sendrun:campaign_draft";

export interface CampaignDraft {
  name: string;
  templateId: string;
  recipients: SmartFilter;
}

export function setCampaignDraft(draft: CampaignDraft): void {
  try {
    sessionStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
  } catch {
    // storage unavailable — the approve step will find nothing and no-op
  }
}

export function getCampaignDraft(): CampaignDraft | null {
  try {
    const raw = sessionStorage.getItem(DRAFT_KEY);
    return raw ? (JSON.parse(raw) as CampaignDraft) : null;
  } catch {
    return null;
  }
}
