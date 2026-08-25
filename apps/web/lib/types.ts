/**
 * Domain types, mirroring packages/shared/transitions.py.
 *
 * The two status axes on an email job are deliberately separate and must never be
 * collapsed into one field — see CLAUDE.md invariants. `opened`/`clicked` are NOT
 * statuses; they are engagement counters.
 */

export type SendStatus =
  | "queued"
  | "sending"
  | "sent"
  | "failed_transient"
  | "failed_permanent"
  | "cancelled"
  | "skipped";

export type DeliveryStatus =
  | null
  | "deferred"
  | "delivered"
  | "bounced"
  | "complained";

export type CampaignStatus =
  | "draft"
  | "scheduled"
  | "launching"
  | "running"
  | "paused"
  | "completed"
  | "cancelled"
  | "failed";

export interface Contact {
  id: string;
  name: string;
  email: string;
  tags: string[];
  sentCount: number;
  /** Model output, 0–1. Shown with its inputs on the contact page. */
  engagement: number;
  bounceRisk: "low" | "medium" | "high";
  specialization: string | null;
}

export interface Campaign {
  id: string;
  name: string;
  event: string;
  status: CampaignStatus;
  recipients: number;
  attempted: number;
  delivered: number;
  bounced: number;
  failed: number;
  opened: number;
  clicked: number;
  startedAt: string | null;
}

export interface EmailJob {
  id: string;
  campaignId: string;
  contactEmail: string;
  sendStatus: SendStatus;
  deliveryStatus: DeliveryStatus;
  attempt: number;
  providerMessageId: string | null;
  lastError: string | null;
}

export interface ProgressSnapshot {
  campaignId: string;
  total: number;
  attempted: number;
  delivered: number;
  sending: number;
  retrying: number;
  failed: number;
  bounced: number;
  /** The invariant. Must stay 0 through any number of crashes. */
  duplicateSends: number;
  idempotencyHits: number;
  orphanEvents: number;
  providerCalls: number;
  status: CampaignStatus;
}

export interface FeedEvent {
  at: string;
  kind: "delivered" | "sending" | "retry" | "bounced" | "failed" | "system";
  who: string;
  detail: string;
}

export interface PreflightCheck {
  id: string;
  severity: "ok" | "warn" | "crit";
  title: string;
  detail: string;
  /** Present when the user can act on it. AI recommends; the human decides. */
  action?: string;
  meta?: string;
}

export interface PreflightReport {
  spamRisk: number;
  personalizationScore: number;
  predictedDelivery: number;
  checks: PreflightCheck[];
}
