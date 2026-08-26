"use client";

import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { Chip } from "@/components/Table";
import { PageTitle, Pill, SectionLabel } from "@/components/ui";
import { NOTIFICATIONS, type Notification } from "@/lib/mock-notifications";
import { getCurrentOrgId, listAuditLog, useMocks, type AuditLogOut } from "@/lib/api";

const TONE: Record<Notification["kind"], "ok" | "warn" | "crit" | "run" | "default"> = {
  campaign_complete: "ok",
  dlq: "crit",
  bounce_spike: "warn",
  invite: "default",
  system: "run",
};

const LABEL: Record<Notification["kind"], string> = {
  campaign_complete: "Completed",
  dlq: "Dead letter",
  bounce_spike: "Deliverability",
  invite: "Team",
  system: "System",
};

const FILTERS = ["All", "Unread", "Reliability"] as const;

function MockNotificationsPage() {
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("All");
  const [items, setItems] = useState(NOTIFICATIONS);

  const visible = items.filter((n) => {
    if (filter === "Unread") return !n.read;
    if (filter === "Reliability") return n.kind === "dlq" || n.kind === "system" || n.kind === "bounce_spike";
    return true;
  });
  const unread = items.filter((n) => !n.read).length;

  return (
    <Shell
      crumb="Notifications"
      actions={
        <button className="btn btn-ghost btn-sm" onClick={() => setItems((prev) => prev.map((n) => ({ ...n, read: true })))} disabled={unread === 0}>
          Mark all read
        </button>
      }
    >
      <PageTitle title="Notifications" lede={unread > 0 ? `${unread} unread. Campaign outcomes and reliability events land here.` : "You are all caught up."} />
      <div className="mb-4 flex flex-wrap gap-2">
        {FILTERS.map((f) => <Chip key={f} active={filter === f} onClick={() => setFilter(f)}>{f}</Chip>)}
      </div>
      <SectionLabel>Recent</SectionLabel>
      <div className="flex flex-col gap-3">
        {visible.map((n) => (
          <div key={n.id} className="card" style={{ borderLeft: `3px solid ${n.read ? "var(--line-2)" : "var(--color-accent)"}` }}>
            <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-2.5">
                <Pill tone={TONE[n.kind]}>{LABEL[n.kind]}</Pill>
                <span className="text-[.92rem] font-semibold tracking-[-.01em]">{n.title}</span>
              </div>
              <span className="text-faint" style={{ fontFamily: "var(--font-mono)", fontSize: ".66rem" }}>{n.at}</span>
            </div>
            <p className="text-muted m-0 max-w-[70ch] text-[.82rem] leading-[1.55]">{n.detail}</p>
          </div>
        ))}
        {visible.length === 0 && <div className="text-faint py-10 text-center">Nothing here.</div>}
      </div>
    </Shell>
  );
}

const RELIABILITY_ACTIONS = new Set([
  "template.archived", "campaign.cancelled",
]);

function labelFor(action: string): string {
  if (action.startsWith("campaign.")) return "Campaign";
  if (action.startsWith("template.")) return "Template";
  if (action.startsWith("member.") || action === "organization.created") return "Team";
  if (action.startsWith("contact.")) return "Contact";
  return "System";
}

function toneFor(action: string): "ok" | "warn" | "crit" | "run" | "default" {
  if (action === "campaign.launched") return "run";
  if (action === "campaign.cancelled") return "crit";
  if (RELIABILITY_ACTIONS.has(action)) return "warn";
  return "default";
}

function LiveNotificationsPage() {
  const [entries, setEntries] = useState<AuditLogOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"All" | "Reliability">("All");

  useEffect(() => {
    async function load() {
      const orgId = getCurrentOrgId();
      if (!orgId) {
        setError("No organization selected — sign in again.");
        setLoading(false);
        return;
      }
      try {
        setEntries(await listAuditLog(orgId, { limit: 100 }));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load notifications");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const visible = entries.filter((e) => filter === "All" || RELIABILITY_ACTIONS.has(e.action));

  return (
    <Shell crumb="Notifications">
      <PageTitle title="Notifications" lede="Every audited action across this organization — campaign, template, and team events." />
      <div className="mb-4 flex flex-wrap gap-2">
        {(["All", "Reliability"] as const).map((f) => (
          <Chip key={f} active={filter === f} onClick={() => setFilter(f)}>{f}</Chip>
        ))}
      </div>
      <SectionLabel>Recent</SectionLabel>
      {error && <p style={{ color: "var(--color-crit)", fontSize: ".82rem" }}>{error}</p>}
      {loading && <p className="text-faint">Loading…</p>}
      {!loading && !error && (
        <div className="flex flex-col gap-3">
          {visible.map((e) => (
            <div key={e.id} className="card" style={{ borderLeft: "3px solid var(--line-2)" }}>
              <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap items-center gap-2.5">
                  <Pill tone={toneFor(e.action)}>{labelFor(e.action)}</Pill>
                  <span className="text-[.92rem] font-semibold tracking-[-.01em]">{e.action}</span>
                </div>
                <span className="text-faint" style={{ fontFamily: "var(--font-mono)", fontSize: ".66rem" }}>
                  {new Date(e.created_at).toLocaleString()}
                </span>
              </div>
              {e.target_type && (
                <p className="text-muted m-0 max-w-[70ch] text-[.82rem] leading-[1.55]">
                  {e.target_type} · {e.target_id} · by {e.actor_kind}
                </p>
              )}
            </div>
          ))}
          {visible.length === 0 && <div className="text-faint py-10 text-center">Nothing here.</div>}
        </div>
      )}
    </Shell>
  );
}

export default function NotificationsPage() {
  return useMocks ? <MockNotificationsPage /> : <LiveNotificationsPage />;
}
