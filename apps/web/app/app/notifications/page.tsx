"use client";

import { useState } from "react";
import Shell from "@/components/Shell";
import { Chip } from "@/components/Table";
import { PageTitle, Pill, SectionLabel } from "@/components/ui";
import { NOTIFICATIONS, type Notification } from "@/lib/mock-notifications";

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

export default function NotificationsPage() {
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
        <button
          className="btn btn-ghost btn-sm"
          onClick={() => setItems((prev) => prev.map((n) => ({ ...n, read: true })))}
          disabled={unread === 0}
        >
          Mark all read
        </button>
      }
    >
      <PageTitle
        title="Notifications"
        lede={
          unread > 0
            ? `${unread} unread. Campaign outcomes and reliability events land here.`
            : "You are all caught up."
        }
      />

      <div className="mb-4 flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <Chip key={f} active={filter === f} onClick={() => setFilter(f)}>
            {f}
          </Chip>
        ))}
      </div>

      <SectionLabel>Recent</SectionLabel>

      <div className="flex flex-col gap-3">
        {visible.map((n) => (
          <div
            key={n.id}
            className="card"
            style={{
              borderLeft: `3px solid ${
                n.read ? "var(--line-2)" : "var(--color-accent)"
              }`,
            }}
          >
            <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-2.5">
                <Pill tone={TONE[n.kind]}>{LABEL[n.kind]}</Pill>
                <span className="text-[.92rem] font-semibold tracking-[-.01em]">
                  {n.title}
                </span>
              </div>
              <span
                className="text-faint"
                style={{ fontFamily: "var(--font-mono)", fontSize: ".66rem" }}
              >
                {n.at}
              </span>
            </div>
            <p className="text-muted m-0 max-w-[70ch] text-[.82rem] leading-[1.55]">
              {n.detail}
            </p>
          </div>
        ))}

        {visible.length === 0 && (
          <div className="text-faint py-10 text-center">Nothing here.</div>
        )}
      </div>
    </Shell>
  );
}
