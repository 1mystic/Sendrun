/**
 * Mock data layer.
 *
 * Every page reads through this module rather than calling `fetch` directly, so
 * swapping in the real FastAPI backend is a change to this file alone. Function
 * shapes match the planned API responses.
 */

import type {
  Campaign,
  Contact,
  FeedEvent,
  PreflightReport,
  ProgressSnapshot,
} from "./types";

export const ORG = { name: "AI Research Club", members: 4, role: "Owner" };

/** The signed-in user. Replaced by the session response once auth is wired. */
export const USER = {
  name: "Aarav Sharma",
  email: "aarav@airesearch.club",
  initials: "AS",
};

export const CONTACTS: Contact[] = [
  { id: "c1", name: "Rahul Menon", email: "rahul@example.com", tags: ["speaker", "AI"], sentCount: 7, engagement: 0.82, bounceRisk: "low", specialization: "computer vision" },
  { id: "c2", name: "Ananya Iyer", email: "ananya@example.com", tags: ["alumni"], sentCount: 4, engagement: 0.61, bounceRisk: "low", specialization: "reinforcement learning" },
  { id: "c3", name: "Arjun Desai", email: "arjun@example.com", tags: ["speaker"], sentCount: 9, engagement: 0.34, bounceRisk: "medium", specialization: null },
  { id: "c4", name: "Priya Nair", email: "priya@example.com", tags: ["sponsor"], sentCount: 3, engagement: 0.77, bounceRisk: "low", specialization: "systems" },
  { id: "c5", name: "Neha Kulkarni", email: "neha@example.com", tags: ["alumni", "ML"], sentCount: 6, engagement: 0.88, bounceRisk: "low", specialization: "NLP" },
  { id: "c6", name: "Vikram Shah", email: "vikram@old-domain.test", tags: ["participant"], sentCount: 11, engagement: 0.04, bounceRisk: "high", specialization: null },
];

export const CAMPAIGNS: Campaign[] = [
  { id: "campaign_8231", name: "Hackathon Speaker Outreach", event: "Hackathon 2026", status: "running", recipients: 122, attempted: 0, delivered: 0, bounced: 0, failed: 0, opened: 0, clicked: 0, startedAt: "14:01:04" },
  { id: "campaign_8180", name: "Sponsor Outreach — Q3", event: "Hackathon 2026", status: "completed", recipients: 412, attempted: 412, delivered: 401, bounced: 8, failed: 3, opened: 147, clicked: 52, startedAt: "09:12:40" },
  { id: "campaign_8104", name: "Volunteer Recruitment", event: "Hackathon 2026", status: "completed", recipients: 1204, attempted: 1204, delivered: 1166, bounced: 31, failed: 7, opened: 388, clicked: 121, startedAt: "11:30:02" },
  { id: "campaign_8244", name: "Demo Day Invitations", event: "Demo Day", status: "draft", recipients: 0, attempted: 0, delivered: 0, bounced: 0, failed: 0, opened: 0, clicked: 0, startedAt: null },
];

export const RECIPIENT_GROUPS = [
  { id: "speaker", label: "Tag: speaker", count: 127 },
  { id: "alumni", label: "Group: alumni", count: 402 },
  { id: "sponsors", label: "Group: sponsors", count: 64 },
  { id: "participant", label: "Tag: participant", count: 1204 },
];

export const DEFAULT_TEMPLATE = {
  subject: "Speak at AI Hackathon 2026, {{first_name}}?",
  body: `Hi {{first_name}},

We'd love to invite you to speak at {{event_name}}.

Your work in {{specialization}} is exactly what our attendees want to hear about.

Apply here: https://airesearch.club/hackathon-2026/speak

— The AI Research Club`,
};

export const PREFLIGHT: PreflightReport = {
  spamRisk: 18,
  personalizationScore: 91,
  predictedDelivery: 96.1,
  checks: [
    { id: "vars", severity: "warn", title: "7 recipients missing {{specialization}}", detail: "The sentence referencing it would read broken. Use a fallback phrase, or exclude these 7.", action: "Set fallback" },
    { id: "bounce", severity: "crit", title: "5 addresses are high bounce risk", detail: "Previously hard-bounced or inactive for 18+ months. Sending costs you sender reputation.", action: "Exclude 5" },
    { id: "links", severity: "ok", title: "All 1 link resolves", detail: "airesearch.club/hackathon-2026/speak returned 200 · no redirect chain.", meta: "200 OK" },
    { id: "subject", severity: "ok", title: "Subject line is well-formed", detail: "46 characters, no all-caps, personalized. Reads naturally in an inbox list.", meta: "46 chars" },
    { id: "sensitive", severity: "ok", title: "No sensitive content detected", detail: "No credentials, personal data, or unapproved claims in the body.", meta: "clean" },
  ],
};

/** Render a template for one contact, exactly as the send pipeline would. */
export function renderTemplate(
  text: string,
  contact: Contact,
  eventName = "AI Hackathon 2026",
): string {
  return text
    .replace(/\{\{first_name\}\}/g, contact.name.split(" ")[0])
    .replace(/\{\{event_name\}\}/g, eventName)
    .replace(/\{\{specialization\}\}/g, contact.specialization ?? "⟨missing⟩");
}

export function emptyProgress(campaignId: string, total: number): ProgressSnapshot {
  return {
    campaignId, total, attempted: 0, delivered: 0, sending: 0, retrying: 0,
    failed: 0, bounced: 0, duplicateSends: 0, idempotencyHits: 0,
    orphanEvents: 0, providerCalls: 0, status: "running",
  };
}

export const WORKERS = ["worker_a", "worker_b", "worker_c"];

export const NAMES = [
  "rahul", "priya", "neha", "arjun", "ananya", "vikram",
  "kiran", "meera", "dev", "sana", "rohit", "asha", "nikhil", "tara",
];

export type { Campaign, Contact, FeedEvent, PreflightReport, ProgressSnapshot };
