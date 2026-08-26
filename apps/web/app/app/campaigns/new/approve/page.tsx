"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import Link from "next/link";
import Shell from "@/components/Shell";
import { SectionLabel } from "@/components/ui";
import { createCampaign, launchCampaign, getCampaignDraft, getCurrentOrgId, useMocks } from "@/lib/api";
import Stepper from "../../Stepper";

const GUARANTEES = [
  "Each recipient is an independent job with its own retry budget",
  "Every send carries an idempotency key — a retry cannot duplicate it",
  "If a worker dies, its leases expire and its jobs are re-picked",
  "Close this tab freely; execution is server-side",
];

export default function ApprovePage() {
  const router = useRouter();
  const [launching, setLaunching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleLaunch() {
    if (useMocks) {
      setLaunching(true);
      setTimeout(() => router.push("/app/campaigns/campaign_8231"), 550);
      return;
    }

    const draft = getCampaignDraft();
    const orgId = getCurrentOrgId();
    if (!draft || !orgId) {
      setError("No campaign draft found — go back and compose your message first.");
      return;
    }

    setError(null);
    setLaunching(true);
    try {
      const created = await createCampaign(orgId, { name: draft.name, template_id: draft.templateId, recipients: draft.recipients });
      const launched = await launchCampaign(orgId, created.id, { name: draft.name, template_id: draft.templateId, recipients: draft.recipients });
      router.push(`/app/campaigns/${launched.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Launch failed");
      setLaunching(false);
    }
  }

  return (
    <Shell crumb="Approve">
      <h1 className="m-0 mb-1.5 text-[clamp(1.5rem,3vw,2.1rem)] font-bold leading-[1.02] tracking-[-.035em] text-balance">
        Approve and launch
      </h1>
      <p className="text-muted m-0 mb-6 max-w-[62ch] text-[.88rem] leading-[1.6]">
        Nothing has been sent yet. This is the last reversible moment.
      </p>

      <Stepper current={3} />

      <div className="grid items-start gap-[22px] lg:grid-cols-2">
        <div className="card">
          <SectionLabel>Summary</SectionLabel>
          <table style={{ minWidth: 0, width: "100%", borderCollapse: "collapse" }}>
            <tbody>
              {[
                ["Campaign", <b key="c">Hackathon Speaker Outreach</b>],
                [
                  "Recipients",
                  <>
                    <b className="num">122</b>{" "}
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: ".64rem", color: "var(--faint)" }}>
                      (127 − 5 excluded)
                    </span>
                  </>,
                ],
                ["Independent jobs", <b key="j" className="num">122</b>],
                [
                  "Batches",
                  <>
                    <b className="num">1</b>{" "}
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: ".64rem", color: "var(--faint)" }}>
                      (500/batch)
                    </span>
                  </>,
                ],
                [
                  "Send rate",
                  <>
                    <b className="num">8</b>{" "}
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: ".64rem", color: "var(--faint)" }}>
                      /sec
                    </span>
                  </>,
                ],
                ["Est. duration", <b key="d">~16 sec</b>],
              ].map(([label, value], i) => (
                <tr key={i} style={{ borderBottom: i === 5 ? "none" : "1px solid var(--line)" }}>
                  <td style={{ padding: "11px 0", color: "var(--muted)" }}>{label}</td>
                  <td style={{ padding: "11px 0", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                    {value}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="flex flex-col gap-3">
          <div
            style={{
              border: "1px solid rgba(228,73,31,.4)",
              background: "var(--accent-dim)",
              borderRadius: 3,
              padding: "13px 15px",
              display: "flex",
              gap: 12,
              alignItems: "center",
              flexWrap: "wrap",
            }}
          >
            <p style={{ margin: 0, fontSize: ".82rem", lineHeight: 1.5 }}>
              <b style={{ color: "var(--color-accent)" }}>This action sends real email.</b> Once
              launched, delivered messages cannot be recalled. Remaining queued jobs can be
              cancelled at any time.
            </p>
          </div>

          <div className="card">
            <SectionLabel>Durability guarantees</SectionLabel>
            <div className="flex flex-col gap-[9px]" style={{ fontSize: ".8rem", color: "var(--muted)", lineHeight: 1.5 }}>
              {GUARANTEES.map((g) => (
                <div key={g} className="flex flex-wrap items-center gap-[9px]">
                  <span style={{ color: "var(--color-ok)" }}>✓</span> {g}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="h-6" />
      {error && (
        <p style={{ color: "var(--color-crit)", fontSize: ".82rem", marginBottom: 12 }}>{error}</p>
      )}
      <div className="flex flex-wrap items-center gap-[9px]">
        <button type="button" className="btn" disabled={launching} onClick={handleLaunch}>
          {launching ? "Launching…" : "Launch 122 jobs"}
        </button>
        <Link href="/app/campaigns/new/preflight" className="btn btn-ghost no-underline">
          ← Back to preflight
        </Link>
      </div>
    </Shell>
  );
}
