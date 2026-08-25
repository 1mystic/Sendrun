import Link from "next/link";
import Shell from "@/components/Shell";
import { SectionLabel } from "@/components/ui";
import { PREFLIGHT } from "@/lib/mock";
import type { PreflightCheck } from "@/lib/types";
import Stepper from "../../Stepper";

const SEVERITY_ICON: Record<PreflightCheck["severity"], { icon: string; color: string }> = {
  ok: { icon: "✓", color: "var(--color-ok)" },
  warn: { icon: "⚠", color: "var(--color-warn)" },
  crit: { icon: "✕", color: "var(--color-crit)" },
};

export default function PreflightPage() {
  return (
    <Shell crumb="Preflight">
      <h1 className="m-0 mb-1.5 text-[clamp(1.5rem,3vw,2.1rem)] font-bold leading-[1.02] tracking-[-.035em] text-balance">
        Preflight report
      </h1>
      <p className="text-muted m-0 mb-6 max-w-[62ch] text-[.88rem] leading-[1.6]">
        Checks run before anything is sent. You decide what to do about each one.
      </p>

      <Stepper current={2} />

      <div className="mb-5 grid gap-[clamp(12px,1.1vw,18px)] md:grid-cols-3">
        <div className="card">
          <SectionLabel>Spam risk</SectionLabel>
          <div className="flex items-baseline gap-[10px]">
            <span
              style={{
                fontSize: "2.6rem",
                fontWeight: 700,
                letterSpacing: "-.04em",
                lineHeight: 1,
                color: "var(--color-ok)",
              }}
              className="num"
            >
              {PREFLIGHT.spamRisk}
            </span>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: ".68rem", color: "var(--muted)" }}>
              / 100 · low
            </span>
          </div>
          <p
            style={{ fontFamily: "var(--font-mono)", fontSize: ".62rem", color: "var(--faint)", marginTop: 8 }}
          >
            Heuristic score from link density, caps ratio, and promotional terms. Not a prediction of
            any provider&rsquo;s filter.
          </p>
        </div>

        <div className="card">
          <SectionLabel>Personalization</SectionLabel>
          <div className="flex items-baseline gap-[10px]">
            <span
              style={{
                fontSize: "2.6rem",
                fontWeight: 700,
                letterSpacing: "-.04em",
                lineHeight: 1,
                color: "var(--color-warn)",
              }}
              className="num"
            >
              {PREFLIGHT.personalizationScore}
            </span>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: ".68rem", color: "var(--muted)" }}>
              / 100
            </span>
          </div>
          <p
            style={{ fontFamily: "var(--font-mono)", fontSize: ".62rem", color: "var(--faint)", marginTop: 8 }}
          >
            120 of 127 recipients resolve every variable.
          </p>
        </div>

        <div className="card">
          <SectionLabel>Predicted delivery</SectionLabel>
          <div className="flex items-baseline gap-[10px]">
            <span
              style={{
                fontSize: "2.6rem",
                fontWeight: 700,
                letterSpacing: "-.04em",
                lineHeight: 1,
                color: "var(--color-ok)",
              }}
              className="num"
            >
              {PREFLIGHT.predictedDelivery}
              <span style={{ fontSize: ".5em" }}>%</span>
            </span>
          </div>
          <p
            style={{ fontFamily: "var(--font-mono)", fontSize: ".62rem", color: "var(--faint)", marginTop: 8 }}
          >
            Bounce model over recipient history. 5 addresses flagged high-risk.
          </p>
        </div>
      </div>

      <div className="card">
        <SectionLabel>Checks</SectionLabel>
        {PREFLIGHT.checks.map((check, i) => {
          const sev = SEVERITY_ICON[check.severity];
          return (
            <div
              key={check.id}
              className="grid items-start gap-3"
              style={{
                gridTemplateColumns: "18px 1fr auto",
                padding: "13px 0",
                borderBottom: i === PREFLIGHT.checks.length - 1 ? "none" : "1px solid var(--line)",
              }}
            >
              <span style={{ fontSize: ".9rem", lineHeight: 1.4, color: sev.color }}>{sev.icon}</span>
              <div>
                <h4 style={{ margin: "0 0 3px", fontSize: ".86rem", fontWeight: 600, letterSpacing: "-.01em" }}>
                  {check.title}
                </h4>
                <p style={{ margin: 0, fontSize: ".78rem", color: "var(--muted)", lineHeight: 1.55 }}>
                  {check.detail}
                </p>
              </div>
              {check.action ? (
                <button
                  type="button"
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: ".61rem",
                    color: "var(--color-accent)",
                    background: "none",
                    border: 0,
                    textDecoration: "underline",
                    textUnderlineOffset: 3,
                    padding: 0,
                  }}
                >
                  {check.action}
                </button>
              ) : (
                check.meta && (
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: ".62rem", color: "var(--faint)" }}>
                    {check.meta}
                  </span>
                )
              )}
            </div>
          );
        })}
      </div>

      <div className="h-6" />
      <div className="flex flex-wrap items-center gap-[9px]">
        <Link href="/app/campaigns/new/approve" className="btn no-underline">
          Continue to approval →
        </Link>
        <Link href="/app/campaigns/new" className="btn btn-ghost no-underline">
          ← Back to compose
        </Link>
      </div>
    </Shell>
  );
}
