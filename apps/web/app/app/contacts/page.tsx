"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import Shell from "@/components/Shell";
import { PageTitle, Pill } from "@/components/ui";
import { CONTACTS } from "@/lib/mock";

const FILTERS = [
  { id: "all", label: "All", tag: null, count: 1847 },
  { id: "speaker", label: "Speakers", tag: "speaker", count: 127 },
  { id: "alumni", label: "Alumni", tag: "alumni", count: 402 },
  { id: "sponsor", label: "Sponsors", tag: "sponsor", count: 64 },
  { id: "participant", label: "Participants", tag: "participant", count: 1204 },
] as const;

type FilterId = (typeof FILTERS)[number]["id"];

function engagementColor(v: number): string {
  if (v >= 0.5) return "var(--color-ok)";
  if (v >= 0.15) return "var(--color-warn)";
  return "var(--faint)";
}

function riskTone(risk: "low" | "medium" | "high"): "ok" | "warn" | "crit" {
  if (risk === "low") return "ok";
  if (risk === "medium") return "warn";
  return "crit";
}

export default function ContactsPage() {
  const [filter, setFilter] = useState<FilterId>("all");
  const [smart, setSmart] = useState(false);

  const active = useMemo(() => FILTERS.find((f) => f.id === filter)!, [filter]);

  const filtered = useMemo(() => {
    let list = CONTACTS;
    if (active.tag) list = list.filter((c) => c.tags.includes(active.tag));
    if (smart) list = list.filter((c) => c.engagement >= 0.5 && c.bounceRisk === "low");
    return list;
  }, [active, smart]);

  return (
    <Shell
      crumb="Contacts"
      actions={
        <button type="button" className="btn btn-ghost btn-sm" disabled>
          Import contacts
        </button>
      }
    >
      <PageTitle
        title="Contacts"
        lede="1,847 contacts across 6 groups. Select by tag, group, or smart filter."
      />

      <div className="mb-4 flex flex-wrap gap-[7px]">
        {FILTERS.map((f) => {
          const isActive = f.id === filter;
          return (
            <button
              key={f.id}
              type="button"
              aria-pressed={isActive}
              onClick={() => setFilter(f.id)}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                fontFamily: "var(--font-mono)",
                fontSize: ".66rem",
                fontWeight: isActive ? 700 : 500,
                padding: "6px 11px",
                borderRadius: 3,
                border: `1px solid ${isActive ? "var(--color-accent)" : "var(--line-2)"}`,
                color: isActive ? "var(--color-accent)" : "var(--muted)",
                background: isActive ? "var(--accent-dim)" : "transparent",
                transition: "all .18s",
              }}
            >
              {f.label} · {f.count.toLocaleString()}
            </button>
          );
        })}
        <button
          type="button"
          aria-pressed={smart}
          onClick={() => setSmart((s) => !s)}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            fontFamily: "var(--font-mono)",
            fontSize: ".66rem",
            fontWeight: smart ? 700 : 500,
            padding: "6px 11px",
            borderRadius: 3,
            border: `1px solid ${smart ? "var(--color-accent)" : "var(--line-2)"}`,
            color: smart ? "var(--color-accent)" : "var(--muted)",
            background: smart ? "var(--accent-dim)" : "transparent",
            transition: "all .18s",
          }}
        >
          + Smart filter
        </button>
      </div>

      <div className="overflow-x-auto" style={{ border: "1px solid var(--line)", borderRadius: 3 }}>
        <table className="w-full border-collapse text-[.82rem]" style={{ minWidth: 720 }}>
          <thead>
            <tr>
              {["Name", "Email", "Tags", "Sent", "Engagement", "Risk"].map((h) => (
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
            {filtered.map((c) => (
              <tr key={c.id} style={{ borderBottom: "1px solid var(--line)" }}>
                <td className="px-3.5 py-3">
                  <Link
                    href={`/app/contacts/${c.id}`}
                    className="no-underline font-semibold"
                    style={{ color: "var(--color-paper)" }}
                  >
                    {c.name}
                  </Link>
                </td>
                <td
                  className="px-3.5 py-3"
                  style={{ fontFamily: "var(--font-mono)", fontSize: ".74rem", color: "var(--muted)" }}
                >
                  {c.email}
                </td>
                <td className="px-3.5 py-3">
                  <div className="flex flex-wrap gap-1.5">
                    {c.tags.map((t) => (
                      <Pill key={t}>{t}</Pill>
                    ))}
                  </div>
                </td>
                <td className="num px-3.5 py-3">{c.sentCount}</td>
                <td
                  className="num px-3.5 py-3"
                  style={{ color: engagementColor(c.engagement) }}
                >
                  {Math.round(c.engagement * 100)}%
                </td>
                <td className="px-3.5 py-3">
                  <Pill tone={riskTone(c.bounceRisk)}>{c.bounceRisk}</Pill>
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3.5 py-8 text-center text-faint">
                  No contacts match this filter.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="text-faint mt-2.5" style={{ fontFamily: "var(--font-mono)", fontSize: ".62rem" }}>
        Engagement and risk are model predictions, shown with their inputs on the contact detail page.
      </p>
    </Shell>
  );
}
