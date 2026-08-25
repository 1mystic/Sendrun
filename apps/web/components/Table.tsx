import type { ReactNode } from "react";

/**
 * Table primitives.
 *
 * Every table is wrapped in its own overflow-x-auto container so wide content
 * scrolls inside the table rather than making the page body scroll sideways.
 */

export function TableWrap({
  children,
  minWidth = 660,
}: {
  children: ReactNode;
  minWidth?: number;
}) {
  return (
    <div
      className="overflow-x-auto"
      style={{ border: "1px solid var(--line)", borderRadius: 3 }}
    >
      <table className="w-full border-collapse text-[.82rem]" style={{ minWidth }}>
        {children}
      </table>
    </div>
  );
}

export function Th({
  children,
  align = "left",
}: {
  children: ReactNode;
  align?: "left" | "right";
}) {
  return (
    <th
      className="text-faint px-3.5 py-2.5 font-normal uppercase"
      style={{
        fontFamily: "var(--font-mono)",
        fontSize: ".58rem",
        letterSpacing: ".12em",
        textAlign: align,
        borderBottom: "1px solid var(--line)",
        background: "var(--color-ink-2)",
      }}
    >
      {children}
    </th>
  );
}

export function Td({
  children,
  align = "left",
  mono = false,
  muted = false,
}: {
  children: ReactNode;
  align?: "left" | "right";
  mono?: boolean;
  muted?: boolean;
}) {
  return (
    <td
      className={`px-3.5 py-3 align-middle ${mono ? "num" : ""} ${muted ? "text-muted" : ""}`}
      style={{
        borderBottom: "1px solid var(--line)",
        textAlign: align,
        ...(mono ? { fontFamily: "var(--font-mono)", fontSize: ".74rem" } : {}),
      }}
    >
      {children}
    </td>
  );
}

/** Filter chips with single or multi select. */
export function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick?: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className="inline-flex items-center gap-1.5 uppercase transition-all"
      style={{
        fontFamily: "var(--font-mono)",
        fontSize: ".66rem",
        fontWeight: active ? 700 : 500,
        padding: "6px 11px",
        borderRadius: 3,
        border: `1px solid ${active ? "var(--color-accent)" : "var(--line-2)"}`,
        color: active ? "var(--color-accent)" : "var(--muted)",
        background: active ? "var(--accent-dim)" : "transparent",
        letterSpacing: ".04em",
      }}
    >
      {children}
    </button>
  );
}
