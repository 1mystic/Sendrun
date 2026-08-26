"use client";

import Link from "next/link";
import { notFound, useParams } from "next/navigation";
import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { PageTitle, Pill } from "@/components/ui";
import { CONTACTS } from "@/lib/mock";
import { CONTACT_FEATURES, CONTACT_SENDS } from "@/lib/mock-ops";
import { getCurrentOrgId, listContactsLive, useMocks, type ContactOut } from "@/lib/api";

function riskTone(risk: "low" | "medium" | "high"): "ok" | "warn" | "crit" {
  if (risk === "low") return "ok";
  if (risk === "medium") return "warn";
  return "crit";
}

function outcomeTone(o: string): "ok" | "warn" | "crit" | "default" {
  if (o === "clicked" || o === "opened" || o === "delivered") return "ok";
  if (o === "bounced" || o === "failed") return "crit";
  return "default";
}

function MockContactDetail({ id }: { id: string }) {
  const contact = CONTACTS.find((c) => c.id === id);
  if (!contact) notFound();

  const features = CONTACT_FEATURES[id];
  const sends = CONTACT_SENDS[id] ?? [];

  function engagementColor(v: number): string {
    if (v >= 0.5) return "var(--color-ok)";
    if (v >= 0.15) return "var(--color-warn)";
    return "var(--faint)";
  }

  return (
    <Shell
      crumb={contact.name}
      actions={<Link href="/app/contacts" className="btn btn-ghost btn-sm no-underline">← All contacts</Link>}
    >
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <PageTitle title={contact.name} />
          <div style={{ fontFamily: "var(--font-mono)", fontSize: ".78rem", color: "var(--muted)" }} className="mb-2 -mt-4">
            {contact.email}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {contact.tags.map((t) => <Pill key={t}>{t}</Pill>)}
          </div>
        </div>
        <div className="flex gap-2">
          <Pill tone={riskTone(contact.bounceRisk)}>{contact.bounceRisk} risk</Pill>
        </div>
      </div>

      <div className="sec">Model predictions</div>
      <div className="card mb-6">
        <p className="text-muted mb-4 text-[.82rem] leading-[1.6]">
          Engagement and bounce risk are model outputs. They are always shown with the features
          that drove them — never as a bare score.
        </p>
        <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
          <div>
            <div className="mb-2" style={{ fontFamily: "var(--font-mono)", fontSize: ".6rem", letterSpacing: ".12em", color: "var(--faint)", textTransform: "uppercase" }}>
              Engagement probability
            </div>
            <div className="num mb-3" style={{ fontSize: "2.2rem", fontWeight: 700, letterSpacing: "-.03em", color: engagementColor(contact.engagement) }}>
              {Math.round(contact.engagement * 100)}%
            </div>
            {features && (
              <table style={{ width: "100%" }}>
                <tbody>
                  <FeatureRow label="Emails sent" value={features.emailsSent} />
                  <FeatureRow label="Opens" value={features.opens} />
                  <FeatureRow label="Clicks" value={features.clicks} />
                  <FeatureRow label="Last engaged" value={features.lastEngagedDaysAgo === null ? "never" : `${features.lastEngagedDaysAgo}d ago`} />
                </tbody>
              </table>
            )}
          </div>
          <div>
            <div className="mb-2" style={{ fontFamily: "var(--font-mono)", fontSize: ".6rem", letterSpacing: ".12em", color: "var(--faint)", textTransform: "uppercase" }}>
              Bounce risk
            </div>
            <div className="mb-3"><Pill tone={riskTone(contact.bounceRisk)}>{contact.bounceRisk}</Pill></div>
            {features && (
              <table style={{ width: "100%" }}>
                <tbody>
                  <FeatureRow label="Domain age" value={`${features.domainAgeYears}y`} />
                  <FeatureRow label="Prior bounces" value={features.priorBounces} />
                  <FeatureRow label="Prior complaints" value={features.priorComplaints} />
                  <FeatureRow label="Specialization on file" value={contact.specialization ?? "none"} />
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>

      <div className="sec">Send history</div>
      <div className="overflow-x-auto" style={{ border: "1px solid var(--line)", borderRadius: 3 }}>
        <table className="w-full border-collapse text-[.82rem]" style={{ minWidth: 560 }}>
          <thead>
            <tr>
              {["Campaign", "Sent at", "Outcome"].map((h) => (
                <th key={h} className="text-faint px-3.5 py-2.5 text-left font-normal uppercase" style={{ fontFamily: "var(--font-mono)", fontSize: ".58rem", letterSpacing: ".12em", borderBottom: "1px solid var(--line)", background: "var(--color-ink-2)" }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sends.map((s, i) => (
              <tr key={i} style={{ borderBottom: "1px solid var(--line)" }}>
                <td className="px-3.5 py-3">
                  <Link href={`/app/campaigns/${s.campaignId}`} className="no-underline" style={{ color: "var(--color-paper)" }}>
                    {s.campaignName}
                  </Link>
                </td>
                <td className="px-3.5 py-3" style={{ fontFamily: "var(--font-mono)", fontSize: ".74rem", color: "var(--muted)" }}>
                  {s.sentAt}
                </td>
                <td className="px-3.5 py-3"><Pill tone={outcomeTone(s.outcome)}>{s.outcome}</Pill></td>
              </tr>
            ))}
            {sends.length === 0 && (
              <tr><td colSpan={3} className="px-3.5 py-8 text-center text-faint">No sends recorded for this contact yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}

function LiveContactDetail({ id }: { id: string }) {
  const [contact, setContact] = useState<ContactOut | null | undefined>(undefined);

  useEffect(() => {
    async function load() {
      const orgId = getCurrentOrgId();
      if (!orgId) {
        setContact(null);
        return;
      }
      try {
        const all = await listContactsLive(orgId);
        setContact(all.find((c) => c.id === id) ?? null);
      } catch {
        setContact(null);
      }
    }
    load();
  }, [id]);

  if (contact === undefined) {
    return (
      <Shell crumb="Contact" actions={<Link href="/app/contacts" className="btn btn-ghost btn-sm no-underline">← All contacts</Link>}>
        <p className="text-faint">Loading…</p>
      </Shell>
    );
  }

  if (contact === null) {
    return (
      <Shell crumb="Contact" actions={<Link href="/app/contacts" className="btn btn-ghost btn-sm no-underline">← All contacts</Link>}>
        <p className="text-faint">Contact not found.</p>
      </Shell>
    );
  }

  return (
    <Shell
      crumb={contact.name || contact.email}
      actions={<Link href="/app/contacts" className="btn btn-ghost btn-sm no-underline">← All contacts</Link>}
    >
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <PageTitle title={contact.name || contact.email} />
          <div style={{ fontFamily: "var(--font-mono)", fontSize: ".78rem", color: "var(--muted)" }} className="mb-2 -mt-4">
            {contact.email}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {contact.tags.map((t) => <Pill key={t}>{t}</Pill>)}
          </div>
        </div>
        <div className="flex gap-2">
          {contact.suppressed ? <Pill tone="crit">Suppressed</Pill> : <Pill tone="ok">Active</Pill>}
        </div>
      </div>

      {Object.keys(contact.fields).length > 0 && (
        <>
          <div className="sec">Fields</div>
          <div className="card mb-6">
            <table style={{ width: "100%" }}>
              <tbody>
                {Object.entries(contact.fields).map(([k, v]) => (
                  <FeatureRow key={k} label={k} value={v} />
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <p className="text-faint" style={{ fontFamily: "var(--font-mono)", fontSize: ".62rem" }}>
        Engagement scoring and per-campaign send history are not yet computed for this view —
        see the campaign detail pages for delivery outcomes on a specific send.
      </p>
    </Shell>
  );
}

function FeatureRow({ label, value }: { label: string; value: string | number }) {
  return (
    <tr style={{ borderBottom: "1px solid var(--line)" }}>
      <td className="py-2 text-muted text-[.78rem]">{label}</td>
      <td className="num py-2 text-right text-[.78rem]" style={{ color: "var(--color-paper)" }}>{value}</td>
    </tr>
  );
}

export default function ContactDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  return useMocks ? <MockContactDetail id={id} /> : <LiveContactDetail id={id} />;
}
