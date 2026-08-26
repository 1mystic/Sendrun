"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { PageTitle, Pill, ProgressBar, SectionLabel, Stat } from "@/components/ui";
import { CAMPAIGNS } from "@/lib/mock";
import { getCurrentOrgId, listCampaignsLive, listContactsLive, useMocks, type CampaignOut } from "@/lib/api";

function MockOverviewPage() {
  const live = CAMPAIGNS.find((c) => c.status === "running")!;
  const recent = CAMPAIGNS.filter((c) => c.status !== "running");

  return (
    <Shell crumb="Overview" actions={<Link href="/app/campaigns/new" className="btn">New campaign</Link>}>
      <PageTitle title="Overview" lede="Four campaigns this month. One running now." />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat value="24,918" label="Emails sent" tone="accent" />
        <Stat value="97.4%" label="Delivery rate" tone="ok" />
        <Stat value="31.2%" label="Open rate" tone="warn" />
        <Stat value="0" label="Duplicate sends" />
      </div>

      <div className="h-6" />
      <SectionLabel>Running now</SectionLabel>

      <Link href={`/app/campaigns/${live.id}`} className="card card-interactive block no-underline">
        <div className="mb-3.5 flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="text-[1rem] font-semibold tracking-[-.02em]">{live.name}</div>
            <div className="text-faint mt-[3px]" style={{ fontFamily: "var(--font-mono)", fontSize: ".66rem" }}>
              {live.id} · started {live.startedAt}
            </div>
          </div>
          <Pill tone="run" pulse>Running</Pill>
        </div>
        <ProgressBar delivered={59} sending={8} retrying={3} failed={2} total={100} />
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
          <span className="num text-muted" style={{ fontFamily: "var(--font-mono)", fontSize: ".72rem" }}>
            <b style={{ color: "var(--color-paper)", fontWeight: 500 }}>7,821</b> / 10,000 attempted
          </span>
          <span className="text-faint" style={{ fontFamily: "var(--font-mono)", fontSize: ".66rem" }}>
            ~4 min remaining
          </span>
        </div>
      </Link>

      <div className="h-6" />
      <SectionLabel>Recent campaigns</SectionLabel>

      <div className="overflow-x-auto" style={{ border: "1px solid var(--line)", borderRadius: 3 }}>
        <table className="w-full border-collapse text-[.82rem]" style={{ minWidth: 660 }}>
          <thead>
            <tr>
              {["Campaign", "Recipients", "Delivered", "Opened", "Status"].map((h) => (
                <th key={h} className="text-faint px-3.5 py-2.5 text-left font-normal uppercase" style={{ fontFamily: "var(--font-mono)", fontSize: ".58rem", letterSpacing: ".12em", borderBottom: "1px solid var(--line)", background: "var(--color-ink-2)" }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {recent.map((c) => (
              <tr key={c.id} style={{ borderBottom: "1px solid var(--line)" }}>
                <td className="px-3.5 py-3">
                  <Link href={c.status === "draft" ? "/app/campaigns/new" : `/app/campaigns/${c.id}`} className="no-underline" style={{ color: "var(--color-paper)" }}>
                    {c.name}
                  </Link>
                </td>
                <td className="num px-3.5 py-3">{c.recipients || "—"}</td>
                <td className="num px-3.5 py-3">{c.delivered || "—"}</td>
                <td className="num px-3.5 py-3">{c.opened || "—"}</td>
                <td className="px-3.5 py-3">
                  {c.status === "completed" ? <Pill tone="ok">Completed</Pill> : <Pill>Draft</Pill>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}

function statusPill(status: string) {
  if (status === "running" || status === "launching") return <Pill tone="run" pulse>Running</Pill>;
  if (status === "completed") return <Pill tone="ok">Completed</Pill>;
  if (status === "cancelled" || status === "failed") return <Pill tone="crit">{status}</Pill>;
  return <Pill>{status}</Pill>;
}

function LiveOverviewPage() {
  const [campaigns, setCampaigns] = useState<CampaignOut[]>([]);
  const [contactCount, setContactCount] = useState<number | null>(null);
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
        const [c, contacts] = await Promise.all([
          listCampaignsLive(orgId),
          listContactsLive(orgId, { search: undefined }),
        ]);
        setCampaigns(c);
        // listContactsLive caps at 500 — an honest floor, not a true total, so
        // it's labeled "500+" below rather than presented as an exact count.
        setContactCount(contacts.length);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load overview");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const running = campaigns.find((c) => c.status === "running" || c.status === "launching");
  const draftCount = campaigns.filter((c) => c.status === "draft").length;
  const completedCount = campaigns.filter((c) => c.status === "completed").length;

  return (
    <Shell crumb="Overview" actions={<Link href="/app/campaigns/new" className="btn">New campaign</Link>}>
      <PageTitle
        title="Overview"
        lede={`${campaigns.length} campaign${campaigns.length === 1 ? "" : "s"} · ${completedCount} completed · ${draftCount} draft.`}
      />

      {error && <p style={{ color: "var(--color-crit)", fontSize: ".82rem" }}>{error}</p>}
      {loading && <p className="text-faint">Loading…</p>}

      {!loading && !error && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat value={campaigns.length} label="Campaigns" tone="accent" />
            <Stat value={completedCount} label="Completed" tone="ok" />
            <Stat value={draftCount} label="Draft" tone="warn" />
            <Stat value={contactCount !== null ? (contactCount >= 500 ? "500+" : contactCount) : "—"} label="Contacts" />
          </div>

          <div className="h-6" />

          {running && (
            <>
              <SectionLabel>Running now</SectionLabel>
              <Link href={`/app/campaigns/${running.id}`} className="card card-interactive block no-underline">
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div>
                    <div className="text-[1rem] font-semibold tracking-[-.02em]">{running.name}</div>
                    <div className="text-faint mt-[3px]" style={{ fontFamily: "var(--font-mono)", fontSize: ".66rem" }}>
                      {running.id}
                    </div>
                  </div>
                  {statusPill(running.status)}
                </div>
              </Link>
              <div className="h-6" />
            </>
          )}

          <SectionLabel>Recent campaigns</SectionLabel>
          <div className="overflow-x-auto" style={{ border: "1px solid var(--line)", borderRadius: 3 }}>
            <table className="w-full border-collapse text-[.82rem]" style={{ minWidth: 560 }}>
              <thead>
                <tr>
                  {["Campaign", "Recipients", "Status"].map((h) => (
                    <th key={h} className="text-faint px-3.5 py-2.5 text-left font-normal uppercase" style={{ fontFamily: "var(--font-mono)", fontSize: ".58rem", letterSpacing: ".12em", borderBottom: "1px solid var(--line)", background: "var(--color-ink-2)" }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {campaigns.slice(0, 10).map((c) => (
                  <tr key={c.id} style={{ borderBottom: "1px solid var(--line)" }}>
                    <td className="px-3.5 py-3">
                      <Link href={c.status === "draft" ? "/app/campaigns/new" : `/app/campaigns/${c.id}`} className="no-underline" style={{ color: "var(--color-paper)" }}>
                        {c.name}
                      </Link>
                    </td>
                    <td className="num px-3.5 py-3">{c.recipient_count ?? "—"}</td>
                    <td className="px-3.5 py-3">{statusPill(c.status)}</td>
                  </tr>
                ))}
                {campaigns.length === 0 && (
                  <tr><td colSpan={3} className="px-3.5 py-8 text-center text-faint">No campaigns yet.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Shell>
  );
}

export default function OverviewPage() {
  return useMocks ? <MockOverviewPage /> : <LiveOverviewPage />;
}
