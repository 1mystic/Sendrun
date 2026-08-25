import type { ReactNode } from "react";

/** Shared primitives matching design/prototypes/. */

export function Pill({
  tone = "default",
  children,
  pulse = false,
}: {
  tone?: "default" | "ok" | "run" | "warn" | "crit";
  children: ReactNode;
  pulse?: boolean;
}) {
  const cls = tone === "default" ? "pill" : `pill pill-${tone}`;
  return (
    <span className={cls}>
      {tone !== "default" && (
        <span
          className="inline-block h-[5px] w-[5px] rounded-full bg-current"
          style={pulse ? { animation: "blink 1.6s cubic-bezier(.16,1,.3,1) infinite" } : undefined}
        />
      )}
      {children}
    </span>
  );
}

export function Stat({
  value,
  label,
  tone = "default",
}: {
  value: string | number;
  label: string;
  tone?: "default" | "accent" | "ok" | "warn";
}) {
  const rail = {
    default: "var(--line-2)",
    accent: "var(--color-accent)",
    ok: "var(--color-ok)",
    warn: "var(--color-warn)",
  }[tone];

  return (
    <div
      className="card flex flex-col justify-center gap-2"
      style={{ borderLeft: `3px solid ${rail}` }}
    >
      <span className="num text-[clamp(1.55rem,2.1vw,2.15rem)] font-bold leading-[1.04] tracking-[-.035em]">
        {value}
      </span>
      <span
        className="text-muted uppercase"
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: ".6rem",
          fontWeight: 500,
          letterSpacing: ".12em",
        }}
      >
        {label}
      </span>
    </div>
  );
}

/** Multi-segment progress bar. Segments are ordered by lifecycle, not by size. */
export function ProgressBar({
  delivered,
  sending,
  retrying,
  failed,
  total,
  height = 7,
}: {
  delivered: number;
  sending: number;
  retrying: number;
  failed: number;
  total: number;
  height?: number;
}) {
  const pct = (v: number) => (total > 0 ? (v / total) * 100 : 0);
  const seg = (w: number, color: string) => (
    <span
      style={{
        display: "block",
        height: "100%",
        width: `${w}%`,
        background: color,
        transition: "width .5s cubic-bezier(.16,1,.3,1)",
      }}
    />
  );
  return (
    <div className="flex overflow-hidden" style={{ height, background: "var(--line)" }}>
      {seg(pct(delivered), "var(--color-ok)")}
      {seg(pct(sending), "var(--color-accent)")}
      {seg(pct(retrying), "var(--color-warn)")}
      {seg(pct(failed), "rgba(228,73,31,.42)")}
    </div>
  );
}

export function SectionLabel({ children }: { children: ReactNode }) {
  return <div className="sec">{children}</div>;
}

export function PageTitle({ title, lede }: { title: string; lede?: string }) {
  return (
    <div className="mb-6">
      <h1 className="m-0 mb-1.5 text-[clamp(1.5rem,3vw,2.1rem)] font-bold leading-[1.02] tracking-[-.035em] text-balance">
        {title}
      </h1>
      {lede && <p className="text-muted m-0 max-w-[62ch] text-[.88rem] leading-[1.6]">{lede}</p>}
    </div>
  );
}
