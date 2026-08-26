"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import Shell from "@/components/Shell";
import { PageTitle, Pill } from "@/components/ui";
import { CAMPAIGNS } from "@/lib/mock";
import { getCurrentOrgId, listCampaignsLive, useMocks, type CampaignOut } from "@/lib/api";
import type { CampaignStatus } from "@/lib/types";

const FILTERS = [
  { id: "all", label: "All" },
  { id: "running", label: "Running" },
  { id: "completed", label: "Completed" },
  { id: "draft", label: "Draft" },
] as const;

type FilterId = (typeof FILTERS)[number]["id"];

function statusMatches(status: string, filter: FilterId) {
  if (filter === "all") return true;
  return status === filter;
}

function statusPill(status: string) {
  if (status === "running" || status === "launching") return <Pill tone="run" pulse>Running</Pill>;
  if (status === "completed") return <Pill tone="ok">Completed</Pill>;
  if (status === "cancelled" || status === "failed") return <Pill tone="crit">{status}</Pill>;
  return <Pill>{status}</Pill>;
}

function MockCampaignsPage() {
  const [filter, setFilter] = useState<FilterId>("all");

  const filtered = useMemo(
    () => CAMPAIGNS.filter((c) => statusMatches(c.status as CampaignStatus, filter)),
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
                display: "inline-flex", alignItems: "center", gap: 6, fontFamily: "var(--font-mono)",
                fontSize: ".66rem", fontWeight: active ? 700 : 500, padding: "6px 11px", borderRadius: 3,
                border: `1px solid ${active ? "var(--color-accent)" : "var(--line-2)"}`,
                color: active ? "var(--color-accent)" : "var(--muted)",
                background: active ? "var(--accent-dim)" : "transparent", transition: "all .18s",
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
              {["Campaign", "Event", "Recipients", "Status", ""].map((h) => (
                <th
                  key={h}
                  className="text-faint px-3.5 py-2.5 text-left font-normal uppercase"
                  style={{
                    fontFamily: "var(--font-mono)", fontSize: ".58rem", letterSpacing: ".12em",
                    borderBottom: "1px solid var(--line)", background: "var(--color-ink-2)",
                  }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((c) => {
              const href = c.status === "draft" ? "/app/campaigns/new" : `/app/campaigns/${c.id}`;
              return (
                <tr key={c.id} style={{ borderBottom: "1px solid var(--line)" }}>
                  <td className="px-3.5 py-3">
                    <Link href={href} className="no-underline" style={{ color: "var(--color-paper)" }}>
                      <b className="font-semibold">{c.name}</b>
                    </Link>
                  </td>
                  <td className="px-3.5 py-3">{c.event}</td>
                  <td className="num px-3.5 py-3">{c.recipients ? c.recipients.toLocaleString() : "—"}</td>
                  <td className="px-3.5 py-3">{statusPill(c.status)}</td>
                  <td className="px-3.5 py-3 text-right">
                    <Link href={href} className="btn btn-ghost btn-sm no-underline">
                      View
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

function LiveCampaignsPage() {
  const [filter, setFilter] = useState<FilterId>("all");
  const [campaigns, setCampaigns] = useState<CampaignOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      const orgId = getCurrentOrgId();
      if (!orgId) {
        setError("No organization selected — sign in again.");
        setLoading(false);
        return;
      }
      try {
        setCampaigns(await listCampaignsLive(orgId));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load campaigns");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const filtered = useMemo(() => campaigns.filter((c) => statusMatches(c.status, filter)), [campaigns, filter]);

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
                display: "inline-flex", alignItems: "center", gap: 6, fontFamily: "var(--font-mono)",
                fontSize: ".66rem", fontWeight: active ? 700 : 500, padding: "6px 11px", borderRadius: 3,
                border: `1px solid ${active ? "var(--color-accent)" : "var(--line-2)"}`,
                color: active ? "var(--color-accent)" : "var(--muted)",
                background: active ? "var(--accent-dim)" : "transparent", transition: "all .18s",
              }}
            >
              {f.label}
            </button>
          );
        })}
      </div>

      {error && <p style={{ color: "var(--color-crit)", fontSize: ".82rem" }}>{error}</p>}
      {loading && <p className="text-faint">Loading campaigns…</p>}

      {!loading && !error && (
        <div className="overflow-x-auto" style={{ border: "1px solid var(--line)", borderRadius: 3 }}>
          <table className="w-full border-collapse text-[.82rem]" style={{ minWidth: 660 }}>
            <thead>
              <tr>
                {["Campaign", "Recipients", "Status", ""].map((h) => (
                  <th
                    key={h}
                    className="text-faint px-3.5 py-2.5 text-left font-normal uppercase"
                    style={{
                      fontFamily: "var(--font-mono)", fontSize: ".58rem", letterSpacing: ".12em",
                      borderBottom: "1px solid var(--line)", background: "var(--color-ink-2)",
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((c) => {
                const href = c.status === "draft" ? "/app/campaigns/new" : `/app/campaigns/${c.id}`;
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
                    <td className="num px-3.5 py-3">
                      {c.recipient_count != null ? c.recipient_count.toLocaleString() : "—"}
                    </td>
                    <td className="px-3.5 py-3">{statusPill(c.status)}</td>
                    <td className="px-3.5 py-3 text-right">
                      <Link href={href} className="btn btn-ghost btn-sm no-underline">
                        View
                      </Link>
                    </td>
                  </tr>
                );
              })}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-3.5 py-8 text-center text-faint">
                    No campaigns match this filter.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </Shell>
  );
}

export default function CampaignsPage() {
  return useMocks ? <MockCampaignsPage /> : <LiveCampaignsPage />;
}
