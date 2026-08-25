"use client";

import { useState } from "react";
import Shell from "@/components/Shell";
import { PageTitle, Pill } from "@/components/ui";
import { DEAD_LETTER_QUEUE, JOB_FILTERS, JOB_INSPECTOR } from "@/lib/mock-ops";

type JobFilterId = (typeof JOB_FILTERS)[number]["id"];

function toneColor(tone: string | undefined): string {
  if (tone === "ok") return "var(--color-ok)";
  if (tone === "warn") return "var(--color-warn)";
  if (tone === "crit") return "var(--color-crit)";
  return "var(--muted)";
}

export default function JobsPage() {
  const [filter, setFilter] = useState<JobFilterId>("all");
  const [requeued, setRequeued] = useState<Record<string, boolean>>({});

  return (
    <Shell crumb="Job inspector">
      <PageTitle
        title="Job inspector"
        lede="Every attempt of every job, and the provider events that resolved it."
      />

      <div className="mb-4 flex flex-wrap gap-[7px]">
        {JOB_FILTERS.map((f) => {
          const active = f.id === filter;
          return (
            <button
              key={f.id}
              type="button"
              aria-pressed={active}
              onClick={() => setFilter(f.id)}
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

      <div className="card mb-4">
        <div className="mb-3.5 flex flex-wrap items-center justify-between gap-4">
          <div>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: ".8rem", fontWeight: 500 }}>
              {JOB_INSPECTOR.id}
            </div>
            <div
              className="text-faint mt-[3px]"
              style={{ fontFamily: "var(--font-mono)", fontSize: ".66rem" }}
            >
              {JOB_INSPECTOR.recipient} · {JOB_INSPECTOR.campaignId}
            </div>
          </div>
          <Pill tone="ok">{JOB_INSPECTOR.outcome}</Pill>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-[.82rem]" style={{ minWidth: 600 }}>
            <thead>
              <tr>
                {["#", "Event", "At", "Detail"].map((h) => (
                  <th
                    key={h}
                    className="text-faint px-3.5 py-2.5 text-left font-normal uppercase"
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: ".58rem",
                      letterSpacing: ".12em",
                      borderBottom: "1px solid var(--line)",
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {JOB_INSPECTOR.timeline.map((ev, i) => (
                <tr key={i} style={{ borderBottom: "1px solid var(--line)" }}>
                  <td className="px-3.5 py-2.5" style={{ fontFamily: "var(--font-mono)" }}>
                    {ev.attempt}
                  </td>
                  <td
                    className="px-3.5 py-2.5"
                    style={{ color: toneColor(ev.tone), fontWeight: ev.tone === "ok" || ev.tone === "warn" ? 500 : 400 }}
                  >
                    {ev.event}
                  </td>
                  <td
                    className="px-3.5 py-2.5"
                    style={{ fontFamily: "var(--font-mono)", fontSize: ".72rem", color: "var(--muted)" }}
                  >
                    {ev.at}
                  </td>
                  <td
                    className="px-3.5 py-2.5"
                    style={{ fontFamily: "var(--font-mono)", fontSize: ".7rem", color: "var(--muted)" }}
                  >
                    {ev.detail}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <div className="sec">Dead letter queue · {DEAD_LETTER_QUEUE.length}</div>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-[.82rem]" style={{ minWidth: 560 }}>
            <thead>
              <tr>
                {["Job", "Recipient", "Attempts", "Last error", ""].map((h) => (
                  <th
                    key={h}
                    className="text-faint px-3.5 py-2.5 text-left font-normal uppercase"
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: ".58rem",
                      letterSpacing: ".12em",
                      borderBottom: "1px solid var(--line)",
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {DEAD_LETTER_QUEUE.map((job) => (
                <tr key={job.id} style={{ borderBottom: "1px solid var(--line)" }}>
                  <td
                    className="px-3.5 py-3"
                    style={{ fontFamily: "var(--font-mono)", fontSize: ".74rem" }}
                  >
                    {job.id}
                  </td>
                  <td
                    className="px-3.5 py-3"
                    style={{ fontFamily: "var(--font-mono)", fontSize: ".74rem", color: "var(--muted)" }}
                  >
                    {job.recipient}
                  </td>
                  <td className="num px-3.5 py-3">{job.attempts}</td>
                  <td className="px-3.5 py-3 text-muted text-[.78rem]">{job.lastError}</td>
                  <td className="px-3.5 py-3 text-right">
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      disabled={!!requeued[job.id]}
                      onClick={() => setRequeued((r) => ({ ...r, [job.id]: true }))}
                    >
                      {requeued[job.id] ? "Requeued" : "Requeue"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-faint mt-2.5" style={{ fontFamily: "var(--font-mono)", fontSize: ".62rem" }}>
          Requeue creates a new job with a new idempotency key. The original row is kept for audit.
        </p>
      </div>
    </Shell>
  );
}
