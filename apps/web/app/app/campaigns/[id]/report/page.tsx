import Shell from "@/components/Shell";
import { Pill, SectionLabel, Stat } from "@/components/ui";

const FAILURES = [
  { recipient: "vikram@old-domain.test", outcome: "Bounced" as const, attempts: 1, reason: "550 — mailbox unavailable" },
  { recipient: "s.rao@old-domain.test", outcome: "Bounced" as const, attempts: 1, reason: "550 — mailbox unavailable" },
  { recipient: "k.patel@old-domain.test", outcome: "Bounced" as const, attempts: 1, reason: "550 — mailbox unavailable" },
  { recipient: "m.joshi@old-domain.test", outcome: "Bounced" as const, attempts: 1, reason: "550 — mailbox unavailable" },
  { recipient: "t.banerjee@example.com", outcome: "Failed" as const, attempts: 5, reason: "Provider 503 after 5 attempts → dead letter" },
];

export default async function CampaignReportPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return (
    <Shell crumb="Report">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="m-0 mb-1.5 text-[clamp(1.5rem,3vw,2.1rem)] font-bold leading-[1.02] tracking-[-.035em] text-balance">
            Campaign report
          </h1>
          <p className="m-0" style={{ fontFamily: "var(--font-mono)", fontSize: ".74rem", color: "var(--muted)" }}>
            {id} · completed in 00:16 · all sends attempted
          </p>
        </div>
        <Pill tone="ok">Completed</Pill>
      </div>

      <div className="mb-5 grid grid-cols-2 gap-[clamp(12px,1.1vw,18px)] lg:grid-cols-4">
        <Stat value={117} label="Delivered" tone="ok" />
        <Stat value={4} label="Bounced" tone="warn" />
        <Stat value={1} label="Failed" />
        <Stat value="95.9%" label="Delivery rate" tone="accent" />
      </div>

      <div className="mb-[18px] grid items-start gap-[18px] lg:grid-cols-2">
        <div className="card">
          <SectionLabel>What the analyst found</SectionLabel>
          <p style={{ fontSize: ".86rem", lineHeight: 1.65, color: "var(--muted)", margin: "0 0 12px" }}>
            Delivery was <b style={{ color: "var(--color-paper)" }}>95.9%</b>, slightly below your
            97.4% average. All four bounces came from a single domain whose mail server rejected the
            messages — those contacts were imported in 2023 and have not engaged since.
          </p>
          <p style={{ fontSize: ".86rem", lineHeight: 1.65, color: "var(--muted)", margin: "0 0 12px" }}>
            Open rate reached <b style={{ color: "var(--color-paper)" }}>38%</b> within two hours,
            which is <b style={{ color: "var(--color-ok)" }}>11 points above</b> your previous
            speaker campaign. The shorter subject line is the most likely cause.
          </p>
          <div style={{ borderTop: "1px solid var(--line)", paddingTop: 12 }}>
            <div
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: ".62rem",
                letterSpacing: ".12em",
                textTransform: "uppercase",
                color: "var(--faint)",
                marginBottom: 8,
              }}
            >
              Suggested
            </div>
            <div className="flex flex-col gap-2">
              <div className="flex flex-wrap items-center gap-[9px]">
                <span style={{ color: "var(--color-accent)" }}>→</span>
                <span style={{ fontSize: ".82rem" }}>Retire 4 bounced addresses</span>
                <button type="button" className="btn btn-ghost btn-sm">
                  Apply
                </button>
              </div>
              <div className="flex flex-wrap items-center gap-[9px]">
                <span style={{ color: "var(--color-accent)" }}>→</span>
                <span style={{ fontSize: ".82rem" }}>Keep subject lines under 50 characters</span>
                <button type="button" className="btn btn-ghost btn-sm">
                  Note it
                </button>
              </div>
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-3">
          <div className="card">
            <SectionLabel>Delivery settling</SectionLabel>
            <p style={{ fontFamily: "var(--font-mono)", fontSize: ".62rem", color: "var(--faint)", margin: "0 0 12px" }}>
              The campaign completed when every send was attempted. Provider events continued
              arriving for 41 minutes afterward.
            </p>
            <table style={{ minWidth: 0, width: "100%", borderCollapse: "collapse" }}>
              <tbody>
                {[
                  ["Sends attempted", "122"],
                  ["Events received", "389"],
                  ["Duplicates discarded", "37"],
                  ["Out-of-order applied", "12"],
                ].map(([label, value]) => (
                  <tr key={label} style={{ borderBottom: "1px solid var(--line)" }}>
                    <td style={{ padding: "9px 0", color: "var(--muted)" }}>{label}</td>
                    <td className="num" style={{ padding: "9px 0", textAlign: "right", fontFamily: "var(--font-mono)" }}>
                      {value}
                    </td>
                  </tr>
                ))}
                <tr>
                  <td style={{ padding: "9px 0", color: "var(--muted)" }}>Settled</td>
                  <td
                    className="num"
                    style={{ padding: "9px 0", textAlign: "right", fontFamily: "var(--font-mono)", color: "var(--color-ok)" }}
                  >
                    100%
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div className="card">
            <SectionLabel>Engagement</SectionLabel>
            <table style={{ minWidth: 0, width: "100%", borderCollapse: "collapse" }}>
              <tbody>
                {[
                  ["Opened", "46", "38%"],
                  ["Clicked", "19", "16%"],
                  ["Replied", "7", "6%"],
                ].map(([label, value, rate]) => (
                  <tr key={label} style={{ borderBottom: "1px solid var(--line)" }}>
                    <td style={{ padding: "9px 0", color: "var(--muted)" }}>{label}</td>
                    <td className="num" style={{ padding: "9px 0", textAlign: "right", fontFamily: "var(--font-mono)" }}>
                      {value} <span style={{ color: "var(--faint)" }}>({rate})</span>
                    </td>
                  </tr>
                ))}
                <tr>
                  <td style={{ padding: "9px 0", color: "var(--muted)" }}>Complaints</td>
                  <td
                    className="num"
                    style={{ padding: "9px 0", textAlign: "right", fontFamily: "var(--font-mono)", color: "var(--color-ok)" }}
                  >
                    0
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="card">
        <SectionLabel>Failures</SectionLabel>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-[.82rem]" style={{ minWidth: 560 }}>
            <thead>
              <tr>
                {["Recipient", "Outcome", "Attempts", "Reason"].map((h) => (
                  <th
                    key={h}
                    className="text-faint px-3.5 py-2.5 text-left font-normal uppercase"
                    style={{ fontFamily: "var(--font-mono)", fontSize: ".58rem", letterSpacing: ".12em", borderBottom: "1px solid var(--line)" }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {FAILURES.map((f, i) => (
                <tr key={f.recipient} style={{ borderBottom: i === FAILURES.length - 1 ? "none" : "1px solid var(--line)" }}>
                  <td className="px-3.5 py-3" style={{ fontFamily: "var(--font-mono)", fontSize: ".74rem" }}>
                    {f.recipient}
                  </td>
                  <td className="px-3.5 py-3">
                    <Pill tone="crit">{f.outcome}</Pill>
                  </td>
                  <td className="num px-3.5 py-3">{f.attempts}</td>
                  <td className="px-3.5 py-3" style={{ color: "var(--muted)", fontSize: ".78rem" }}>
                    {f.reason}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Shell>
  );
}
