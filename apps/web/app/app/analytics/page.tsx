"use client";

import Shell from "@/components/Shell";
import { PageTitle, Pill, Stat } from "@/components/ui";
import { ANALYTICS_CAMPAIGNS, DOMAIN_DELIVERABILITY } from "@/lib/mock-ops";

const TOTAL_SENT = ANALYTICS_CAMPAIGNS.reduce((sum, c) => sum + c.sent, 0);
const AVG_DELIVERY =
  ANALYTICS_CAMPAIGNS.reduce((sum, c) => sum + c.deliveryRate * c.sent, 0) / TOTAL_SENT;
const AVG_OPEN =
  ANALYTICS_CAMPAIGNS.reduce((sum, c) => sum + c.openRate * c.sent, 0) / TOTAL_SENT;
const AVG_CLICK =
  ANALYTICS_CAMPAIGNS.reduce((sum, c) => sum + c.clickRate * c.sent, 0) / TOTAL_SENT;

function DeliveryChart() {
  const w = 640;
  const h = 200;
  const padL = 36;
  const padB = 24;
  const padT = 12;
  const padR = 12;
  const chartW = w - padL - padR;
  const chartH = h - padT - padB;
  const n = ANALYTICS_CAMPAIGNS.length;
  const barGap = 18;
  const barW = (chartW - barGap * (n - 1)) / n;
  const minRate = 90;
  const maxRate = 100;

  const yFor = (rate: number) =>
    padT + chartH - ((rate - minRate) / (maxRate - minRate)) * chartH;

  const barColor = (rate: number) => {
    if (rate >= 96) return "var(--color-ok)";
    if (rate >= 93) return "var(--color-warn)";
    return "var(--color-crit)";
  };

  const gridLines = [90, 92.5, 95, 97.5, 100];

  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      role="img"
      aria-label="Delivery rate over the last five campaigns"
      style={{ width: "100%", height: "auto", display: "block" }}
    >
      {gridLines.map((g) => (
        <g key={g}>
          <line
            x1={padL}
            x2={w - padR}
            y1={yFor(g)}
            y2={yFor(g)}
            stroke="var(--line)"
            strokeWidth={1}
          />
          <text
            x={padL - 8}
            y={yFor(g) + 3}
            textAnchor="end"
            fontFamily="var(--font-mono)"
            fontSize="9"
            fill="var(--faint)"
          >
            {g}%
          </text>
        </g>
      ))}
      {ANALYTICS_CAMPAIGNS.map((c, i) => {
        const x = padL + i * (barW + barGap);
        const yTop = yFor(c.deliveryRate);
        const barH = padT + chartH - yTop;
        return (
          <g key={c.id}>
            <rect
              x={x}
              y={yTop}
              width={barW}
              height={barH}
              fill={barColor(c.deliveryRate)}
              rx={2}
            />
            <text
              x={x + barW / 2}
              y={yTop - 6}
              textAnchor="middle"
              fontFamily="var(--font-mono)"
              fontSize="9.5"
              fill="var(--color-paper)"
            >
              {c.deliveryRate}%
            </text>
            <text
              x={x + barW / 2}
              y={h - padB + 14}
              textAnchor="middle"
              fontFamily="var(--font-mono)"
              fontSize="8.5"
              fill="var(--faint)"
            >
              {c.name.length > 14 ? c.name.slice(0, 13) + "…" : c.name}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export default function AnalyticsPage() {
  return (
    <Shell crumb="Analytics">
      <PageTitle
        title="Analytics"
        lede="Delivery, opens, and clicks across every campaign you've run."
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat value={TOTAL_SENT.toLocaleString()} label="Total sent" tone="accent" />
        <Stat value={`${AVG_DELIVERY.toFixed(1)}%`} label="Delivery rate" tone="ok" />
        <Stat value={`${AVG_OPEN.toFixed(1)}%`} label="Open rate" tone="warn" />
        <Stat value={`${AVG_CLICK.toFixed(1)}%`} label="Click rate" />
      </div>

      <div className="h-6" />
      <div className="sec">Delivery rate by campaign</div>
      <div className="card mb-6">
        <DeliveryChart />
      </div>

      <div className="sec">Campaign comparison</div>
      <div className="overflow-x-auto mb-6" style={{ border: "1px solid var(--line)", borderRadius: 3 }}>
        <table className="w-full border-collapse text-[.82rem]" style={{ minWidth: 640 }}>
          <thead>
            <tr>
              {["Campaign", "Sent", "Delivery rate", "Open rate", "Click rate"].map((h) => (
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
            {ANALYTICS_CAMPAIGNS.map((c) => (
              <tr key={c.id} style={{ borderBottom: "1px solid var(--line)" }}>
                <td className="px-3.5 py-3 font-semibold">{c.name}</td>
                <td className="num px-3.5 py-3">{c.sent.toLocaleString()}</td>
                <td className="num px-3.5 py-3" style={{ color: "var(--color-ok)" }}>
                  {c.deliveryRate}%
                </td>
                <td className="num px-3.5 py-3" style={{ color: "var(--color-warn)" }}>
                  {c.openRate}%
                </td>
                <td className="num px-3.5 py-3">{c.clickRate}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="sec">Deliverability by domain</div>
      <div className="overflow-x-auto" style={{ border: "1px solid var(--line)", borderRadius: 3 }}>
        <table className="w-full border-collapse text-[.82rem]" style={{ minWidth: 560 }}>
          <thead>
            <tr>
              {["Domain", "Sent", "Delivered", "Bounced", "Bounce rate", ""].map((h) => (
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
            {DOMAIN_DELIVERABILITY.map((d) => (
              <tr key={d.domain} style={{ borderBottom: "1px solid var(--line)" }}>
                <td
                  className="px-3.5 py-3"
                  style={{ fontFamily: "var(--font-mono)", fontSize: ".78rem" }}
                >
                  {d.domain}
                </td>
                <td className="num px-3.5 py-3">{d.sent}</td>
                <td className="num px-3.5 py-3">{d.delivered}</td>
                <td className="num px-3.5 py-3">{d.bounced}</td>
                <td
                  className="num px-3.5 py-3"
                  style={{ color: d.flagged ? "var(--color-crit)" : "var(--color-ok)" }}
                >
                  {d.bounceRate}%
                </td>
                <td className="px-3.5 py-3">
                  {d.flagged && <Pill tone="crit">High bounce rate</Pill>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}
