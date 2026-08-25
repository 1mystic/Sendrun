"use client";

import Link from "next/link";
import Shell from "@/components/Shell";
import { PageTitle, Pill, ProgressBar, SectionLabel, Stat } from "@/components/ui";
import { CAMPAIGNS } from "@/lib/mock";

export default function OverviewPage() {
  const live = CAMPAIGNS.find((c) => c.status === "running")!;
  const recent = CAMPAIGNS.filter((c) => c.status !== "running");

  return (
    <Shell
      crumb="Overview"
      actions={
        <Link href="/app/campaigns/new" className="btn">
          New campaign
        </Link>
      }
    >
      <PageTitle title="Overview" lede="Four campaigns this month. One running now." />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat value="24,918" label="Emails sent" tone="accent" />
        <Stat value="97.4%" label="Delivery rate" tone="ok" />
        <Stat value="31.2%" label="Open rate" tone="warn" />
        <Stat value="0" label="Duplicate sends" />
      </div>

      <div className="h-6" />
      <SectionLabel>Running now</SectionLabel>

      <Link
        href={`/app/campaigns/${live.id}`}
        className="card card-interactive block no-underline"
      >
        <div className="mb-3.5 flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="text-[1rem] font-semibold tracking-[-.02em]">{live.name}</div>
            <div
              className="text-faint mt-[3px]"
              style={{ fontFamily: "var(--font-mono)", fontSize: ".66rem" }}
            >
              {live.id} · started {live.startedAt}
            </div>
          </div>
          <Pill tone="run" pulse>
            Running
          </Pill>
        </div>
        <ProgressBar delivered={59} sending={8} retrying={3} failed={2} total={100} />
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
          <span
            className="num text-muted"
            style={{ fontFamily: "var(--font-mono)", fontSize: ".72rem" }}
          >
            <b style={{ color: "var(--color-paper)", fontWeight: 500 }}>7,821</b> / 10,000 attempted
          </span>
          <span
            className="text-faint"
            style={{ fontFamily: "var(--font-mono)", fontSize: ".66rem" }}
          >
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
            {recent.map((c) => (
              <tr key={c.id} style={{ borderBottom: "1px solid var(--line)" }}>
                <td className="px-3.5 py-3">
                  <Link
                    href={c.status === "draft" ? "/app/campaigns/new" : `/app/campaigns/${c.id}`}
                    className="no-underline"
                    style={{ color: "var(--color-paper)" }}
                  >
                    {c.name}
                  </Link>
                </td>
                <td className="num px-3.5 py-3">{c.recipients || "—"}</td>
                <td className="num px-3.5 py-3">{c.delivered || "—"}</td>
                <td className="num px-3.5 py-3">{c.opened || "—"}</td>
                <td className="px-3.5 py-3">
                  {c.status === "completed" ? (
                    <Pill tone="ok">Completed</Pill>
                  ) : (
                    <Pill>Draft</Pill>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}
