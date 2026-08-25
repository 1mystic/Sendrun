/**
 * Additional mock data for contacts detail, job inspector, chaos mode,
 * analytics, settings, and templates. Kept separate from lib/mock.ts to
 * avoid collisions with other agents editing that file — same rule
 * applies here: swapping in the real backend is a change to this module
 * alone.
 */

import type { Contact } from "./types";

/** Model-prediction inputs, keyed by contact id. ML transparency: never show
 *  a bare score — always pair it with the features that produced it. */
export interface PredictionFeatures {
  emailsSent: number;
  opens: number;
  clicks: number;
  lastEngagedDaysAgo: number | null;
  domainAgeYears: number;
  priorBounces: number;
  priorComplaints: number;
}

export const CONTACT_FEATURES: Record<string, PredictionFeatures> = {
  c1: { emailsSent: 7, opens: 6, clicks: 3, lastEngagedDaysAgo: 4, domainAgeYears: 12, priorBounces: 0, priorComplaints: 0 },
  c2: { emailsSent: 4, opens: 2, clicks: 1, lastEngagedDaysAgo: 19, domainAgeYears: 9, priorBounces: 0, priorComplaints: 0 },
  c3: { emailsSent: 9, opens: 3, clicks: 0, lastEngagedDaysAgo: 61, domainAgeYears: 12, priorBounces: 1, priorComplaints: 0 },
  c4: { emailsSent: 3, opens: 3, clicks: 2, lastEngagedDaysAgo: 8, domainAgeYears: 15, priorBounces: 0, priorComplaints: 0 },
  c5: { emailsSent: 6, opens: 6, clicks: 4, lastEngagedDaysAgo: 2, domainAgeYears: 12, priorBounces: 0, priorComplaints: 0 },
  c6: { emailsSent: 11, opens: 0, clicks: 0, lastEngagedDaysAgo: null, domainAgeYears: 1, priorBounces: 3, priorComplaints: 0 },
};

export interface ContactSend {
  campaignId: string;
  campaignName: string;
  sentAt: string;
  outcome: "delivered" | "opened" | "clicked" | "bounced" | "failed";
}

export const CONTACT_SENDS: Record<string, ContactSend[]> = {
  c1: [
    { campaignId: "campaign_8180", campaignName: "Sponsor Outreach — Q3", sentAt: "2026-07-14 09:12", outcome: "clicked" },
    { campaignId: "campaign_8104", campaignName: "Volunteer Recruitment", sentAt: "2026-06-02 11:30", outcome: "opened" },
    { campaignId: "campaign_8231", campaignName: "Hackathon Speaker Outreach", sentAt: "2026-08-25 14:01", outcome: "delivered" },
  ],
  c2: [
    { campaignId: "campaign_8104", campaignName: "Volunteer Recruitment", sentAt: "2026-06-02 11:30", outcome: "opened" },
    { campaignId: "campaign_8180", campaignName: "Sponsor Outreach — Q3", sentAt: "2026-07-14 09:12", outcome: "delivered" },
  ],
  c3: [
    { campaignId: "campaign_8104", campaignName: "Volunteer Recruitment", sentAt: "2026-06-02 11:30", outcome: "bounced" },
    { campaignId: "campaign_8231", campaignName: "Hackathon Speaker Outreach", sentAt: "2026-08-25 14:01", outcome: "delivered" },
  ],
  c4: [
    { campaignId: "campaign_8180", campaignName: "Sponsor Outreach — Q3", sentAt: "2026-07-14 09:12", outcome: "clicked" },
  ],
  c5: [
    { campaignId: "campaign_8104", campaignName: "Volunteer Recruitment", sentAt: "2026-06-02 11:30", outcome: "clicked" },
    { campaignId: "campaign_8180", campaignName: "Sponsor Outreach — Q3", sentAt: "2026-07-14 09:12", outcome: "opened" },
  ],
  c6: [
    { campaignId: "campaign_8104", campaignName: "Volunteer Recruitment", sentAt: "2026-06-02 11:30", outcome: "bounced" },
    { campaignId: "campaign_8180", campaignName: "Sponsor Outreach — Q3", sentAt: "2026-07-14 09:12", outcome: "bounced" },
    { campaignId: "campaign_8231", campaignName: "Hackathon Speaker Outreach", sentAt: "2026-08-25 14:01", outcome: "failed" },
  ],
};

export function getContact(contacts: Contact[], id: string): Contact | undefined {
  return contacts.find((c) => c.id === id);
}

/* ── Job inspector ─────────────────────────────────────────── */

export interface JobAttemptEvent {
  attempt: number | "—";
  event: string;
  at: string;
  detail: string;
  tone?: "ok" | "warn" | "crit" | "muted";
}

export const JOB_INSPECTOR = {
  id: "job_4f9a·c21e",
  recipient: "arjun@example.com",
  campaignId: "campaign_8231",
  outcome: "Sent · Delivered",
  timeline: [
    { attempt: 1, event: "Lease acquired", at: "14:03:19.402", detail: "worker_a · lease 30s", tone: "muted" },
    { attempt: 1, event: "Worker died", at: "14:03:21.118", detail: "lease orphaned, no provider call made", tone: "warn" },
    { attempt: 1, event: "Lease expired", at: "14:03:49.402", detail: "reaper → status back to pending", tone: "muted" },
    { attempt: 2, event: "Lease acquired", at: "14:03:50.006", detail: "worker_c", tone: "muted" },
    { attempt: 2, event: "Claim → sending", at: "14:03:50.011", detail: "no message_id present → safe to send", tone: "muted" },
    { attempt: 2, event: "Provider accepted", at: "14:03:50.204", detail: "msg_7c1f… · idem key job_4f9a·c21e", tone: "ok" },
    { attempt: 2, event: "Recorded sent", at: "14:03:50.209", detail: "adopted 1 orphan event", tone: "muted" },
    { attempt: "—", event: "Webhook: delivered", at: "14:03:52.771", detail: "rank 3 > 2 · applied", tone: "ok" },
    { attempt: "—", event: "Webhook: sent (dup)", at: "14:03:54.010", detail: "rank 2 ≤ 3 · discarded", tone: "muted" },
  ] as JobAttemptEvent[],
};

export interface DeadLetterJob {
  id: string;
  recipient: string;
  attempts: number;
  lastError: string;
}

export const DEAD_LETTER_QUEUE: DeadLetterJob[] = [
  { id: "job_9d02·8871", recipient: "t.banerjee@example.com", attempts: 5, lastError: "503 Service Unavailable" },
];

export const JOB_FILTERS = [
  { id: "all", label: "All" },
  { id: "retried", label: "Retried" },
  { id: "dead-letter", label: "Dead letter" },
  { id: "orphan", label: "Orphan events" },
] as const;

/* ── Chaos mode ────────────────────────────────────────────── */

export interface ChaosSlider {
  id: string;
  label: string;
  description: string;
  min: number;
  max: number;
  defaultValue: number;
  /** How to format the live readout. */
  format: "pct" | "sec";
}

export const FAILURE_SLIDERS: ChaosSlider[] = [
  { id: "transient", label: "Transient provider errors", description: "5xx and timeouts → retried with backoff", min: 0, max: 50, defaultValue: 5, format: "pct" },
  { id: "hardBounce", label: "Hard bounces", description: "Permanent — job fails without retry", min: 0, max: 50, defaultValue: 3, format: "pct" },
  { id: "rateLimit", label: "Rate limiting", description: "429 responses from the provider", min: 0, max: 50, defaultValue: 2, format: "pct" },
  { id: "workerCrash", label: "Random worker crashes", description: "Kill a worker mid-send, no cleanup", min: 0, max: 50, defaultValue: 0, format: "pct" },
];

export const EVENT_SLIDERS: ChaosSlider[] = [
  { id: "dupWebhook", label: "Duplicate webhooks", description: "Same event id delivered twice", min: 0, max: 100, defaultValue: 10, format: "pct" },
  { id: "outOfOrder", label: "Out-of-order delivery", description: "Delivered arrives before sent", min: 0, max: 100, defaultValue: 15, format: "pct" },
  { id: "webhookBeforeAck", label: "Webhook before send ack", description: "Forces the orphan-event race on demand", min: 0, max: 100, defaultValue: 5, format: "pct" },
  { id: "webhookDelay", label: "Webhook delay", description: "Latency before the event arrives", min: 0, max: 100, defaultValue: 24, format: "sec" },
];

export const DEFAULT_SEED = 42;

/* ── Analytics ─────────────────────────────────────────────── */

export interface CampaignAnalyticsRow {
  id: string;
  name: string;
  sent: number;
  deliveryRate: number;
  openRate: number;
  clickRate: number;
}

export const ANALYTICS_CAMPAIGNS: CampaignAnalyticsRow[] = [
  { id: "campaign_7912", name: "Workshop Reminder", sent: 308, deliveryRate: 96.4, openRate: 65.3, clickRate: 24.1 },
  { id: "campaign_8020", name: "Alumni Newsletter — July", sent: 402, deliveryRate: 94.1, openRate: 29.4, clickRate: 8.7 },
  { id: "campaign_8104", name: "Volunteer Recruitment", sent: 1204, deliveryRate: 96.8, openRate: 32.2, clickRate: 10.0 },
  { id: "campaign_8180", name: "Sponsor Outreach — Q3", sent: 412, deliveryRate: 97.3, openRate: 35.7, clickRate: 12.6 },
  { id: "campaign_8231", name: "Hackathon Speaker Outreach", sent: 122, deliveryRate: 95.9, openRate: 38.0, clickRate: 15.6 },
];

export interface DomainDeliverability {
  domain: string;
  sent: number;
  delivered: number;
  bounced: number;
  bounceRate: number;
  flagged: boolean;
}

export const DOMAIN_DELIVERABILITY: DomainDeliverability[] = [
  { domain: "gmail.com", sent: 1042, delivered: 1024, bounced: 4, bounceRate: 0.4, flagged: false },
  { domain: "outlook.com", sent: 618, delivered: 601, bounced: 6, bounceRate: 1.0, flagged: false },
  { domain: "example.com", sent: 312, delivered: 303, bounced: 3, bounceRate: 1.0, flagged: false },
  { domain: "old-domain.test", sent: 44, delivered: 21, bounced: 19, bounceRate: 43.2, flagged: true },
];

/* ── Settings ──────────────────────────────────────────────── */

export interface TeamMember {
  id: string;
  name: string;
  email: string;
  role: "Owner" | "Admin" | "Member";
}

export const TEAM_MEMBERS: TeamMember[] = [
  { id: "u1", name: "Sana Fernandes", email: "sana@airesearch.club", role: "Owner" },
  { id: "u2", name: "Dev Kapoor", email: "dev@airesearch.club", role: "Admin" },
  { id: "u3", name: "Rohit Bhat", email: "rohit@airesearch.club", role: "Member" },
  { id: "u4", name: "Asha Verma", email: "asha@airesearch.club", role: "Member" },
];

export const ORG_SETTINGS = {
  name: "AI Research Club",
  slug: "ai-research-club",
  timezone: "Asia/Kolkata (UTC+5:30)",
};

export const SENDING_SETTINGS = {
  fromName: "AI Research Club",
  fromAddress: "hello@airesearch.club",
  replyTo: "team@airesearch.club",
  dailyCap: 5000,
  ratePerSecond: 8,
};

/* ── Templates ─────────────────────────────────────────────── */

export interface Template {
  id: string;
  name: string;
  subjectPreview: string;
  variables: string[];
  lastEdited: string;
  usageCount: number;
  version: number;
}

export const TEMPLATES: Template[] = [
  { id: "t1", name: "Speaker Invitation", subjectPreview: "Speak at AI Hackathon 2026, {{first_name}}?", variables: ["first_name", "event_name", "specialization"], lastEdited: "2026-08-20", usageCount: 3, version: 4 },
  { id: "t2", name: "Sponsor Outreach", subjectPreview: "Partner with us for {{event_name}}", variables: ["first_name", "event_name", "company"], lastEdited: "2026-07-10", usageCount: 2, version: 2 },
  { id: "t3", name: "Volunteer Recruitment", subjectPreview: "Help run {{event_name}}, {{first_name}}", variables: ["first_name", "event_name"], lastEdited: "2026-06-01", usageCount: 5, version: 6 },
  { id: "t4", name: "Workshop Reminder", subjectPreview: "Reminder: {{workshop_name}} starts soon", variables: ["first_name", "workshop_name", "start_time"], lastEdited: "2026-05-18", usageCount: 8, version: 3 },
  { id: "t5", name: "Alumni Newsletter", subjectPreview: "What's new at {{event_name}} this quarter", variables: ["first_name", "event_name"], lastEdited: "2026-07-28", usageCount: 4, version: 5 },
];
