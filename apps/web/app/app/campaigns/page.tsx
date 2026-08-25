"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import Shell from "@/components/Shell";
import { PageTitle, Pill, ProgressBar } from "@/components/ui";
import { CAMPAIGNS } from "@/lib/mock";
import type { CampaignStatus } from "@/lib/types";

const FILTERS = [
  { id: "all", label: "All" },
  { id: "running", label: "Running" },
  { id: "completed", label: "Completed" },
  { id: "draft", label: "Draft" },
] as const;

type FilterId = (typeof FILTERS)[number]["id"];

function statusMatches(status: CampaignStatus, filter: FilterId) {
  if (filter === "all") return true;
  return status === filter;
}

function segments(c: (typeof CAMPAIGNS)[number]) {
  const total = c.recipients || 1;
  const delivered = c.delivered;
  const sending = c.status === "running" ? Math.max(c.attempted - c.delivered - c.bounced - c.failed, 0) : 0;
  const failed = c.bounced + c.failed;
  return { delivered, sending, retrying: 0, failed, total };
}

export default function CampaignsPage() {
  const [filter, setFilter] = useState<FilterId>("all");

  const filtered = useMemo(
    () => CAMPAIGNS.filter((c) => statusMatches(c.status, filter)),
    [filter],
  );

  return (
    <Shell
      crumb="Campaigns"
      actions={
        <Link href="/app/campaigns/new" className="btn">
          New campaign
        </Link>
      }
    >
      <PageTitle
        title="Campaigns"
        lede="Every campaign, its execution state, and its delivery outcome."
      />

      <div className="mb-3.5 flex flex-wrap gap-[7px]">
        {FILTERS.map((f) => {
          const active = f.id === filter;
          return (
            <button
              key={f.id}
              type="button"
              aria-pressed={active}
              onClick={() => setFilter(f.id)}
              className="chip-btn"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                fontFamily: "var(--font-mono)",
                fontSize: ".66rem",
                fontWeight: active ? 700 : 500,
                padding: "6px 11px",
                borderRadius: 3,
                border: `1px solid ${active ? "var(--color-accent)" : "var(--line-2)"}`,
                color: active ? "var(--color-accent)" : "var(--muted)",
                background: active ? "var(--accent-dim)" : "transparent",
                transition: "all .18s",
              }}
            >
              {f.label}
            </button>
          );
        })}
      </div>

      <div className="overflow-x-auto" style={{ border: "1px solid var(--line)", borderRadius: 3 }}>
        <table className="w-full border-collapse text-[.82rem]" style={{ minWidth: 660 }}>
          <thead>
            <tr>
              {["Campaign", "Event", "Recipients", "Progress", "Status", ""].map((h) => (
                <th
                  key={h}
                  className="text-faint px-3.5 py-2.5 text-left font-normal uppercase"
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: ".58rem",
                    letterSpacing: ".12em",
                    borderBottom: "1px solid var(--line)",
                    background: "var(--color-ink-2)",
                  }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((c) => {
              const seg = segments(c);
              const href = c.status === "draft" ? "/app/campaigns/new" : `/app/campaigns/${c.id}`;
              const actionLabel =
                c.status === "running" ? "Watch" : c.status === "draft" ? "Edit" : "Report";
              const actionHref = c.status === "running" ? `/app/campaigns/${c.id}` : href;

              return (
                <tr key={c.id} style={{ borderBottom: "1px solid var(--line)" }}>
                  <td className="px-3.5 py-3">
                    <Link href={href} className="no-underline" style={{ color: "var(--color-paper)" }}>
                      <b className="font-semibold">{c.name}</b>
                      <div
                        className="text-faint mt-[2px]"
                        style={{ fontFamily: "var(--font-mono)", fontSize: ".62rem" }}
                      >
                        {c.id}
                      </div>
                    </Link>
                  </td>
                  <td className="px-3.5 py-3">{c.event}</td>
                  <td className="num px-3.5 py-3">
                    {c.recipients ? c.recipients.toLocaleString() : "—"}
                  </td>
                  <td className="px-3.5 py-3">
                    {c.status === "draft" ? (
                      <span
                        className="text-faint"
                        style={{ fontFamily: "var(--font-mono)", fontSize: ".66rem" }}
                      >
                        not launched
                      </span>
                    ) : (
                      <div style={{ width: 84 }}>
                        <ProgressBar {...seg} height={4} />
                      </div>
                    )}
                  </td>
                  <td className="px-3.5 py-3">
                    {c.status === "running" && (
                      <Pill tone="run" pulse>
                        Running
                      </Pill>
                    )}
                    {c.status === "completed" && <Pill tone="ok">Completed</Pill>}
                    {c.status === "draft" && <Pill>Draft</Pill>}
                  </td>
                  <td className="px-3.5 py-3 text-right">
                    <Link href={actionHref} className="btn btn-ghost btn-sm no-underline">
                      {actionLabel}
                    </Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}
