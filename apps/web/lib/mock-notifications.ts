/**
 * Notification data. Kept in its own module so parallel work on `mock.ts`
 * never conflicts with it.
 */

export interface Notification {
  id: string;
  kind: "campaign_complete" | "dlq" | "bounce_spike" | "invite" | "system";
  title: string;
  detail: string;
  at: string;
  read: boolean;
}

export const NOTIFICATIONS: Notification[] = [
  {
    id: "n1",
    kind: "campaign_complete",
    title: "Hackathon Speaker Outreach completed",
    detail: "122 attempted · 117 delivered · 4 bounced · 1 failed. Delivery 95.9%.",
    at: "14:01:20",
    read: false,
  },
  {
    id: "n2",
    kind: "dlq",
    title: "1 job moved to the dead-letter queue",
    detail:
      "t.banerjee@example.com failed 5 attempts with 503. Requeue creates a new job with a new idempotency key.",
    at: "14:01:18",
    read: false,
  },
  {
    id: "n3",
    kind: "bounce_spike",
    title: "Bounce rate above normal for old-domain.test",
    detail: "4 of 4 addresses on this domain hard-bounced. Consider retiring them.",
    at: "14:01:16",
    read: true,
  },
  {
    id: "n4",
    kind: "system",
    title: "Worker worker_a restarted",
    detail: "3 orphaned leases were reaped and re-picked. No duplicate sends.",
    at: "14:00:52",
    read: true,
  },
  {
    id: "n5",
    kind: "invite",
    title: "Priya Nair accepted your invitation",
    detail: "Joined AI Research Club as Editor.",
    at: "Yesterday",
    read: true,
  },
];
