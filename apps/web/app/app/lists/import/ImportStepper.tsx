const STEPS = ["Get data in", "Map columns", "Preview", "Result"];

/** 4-step import wizard stepper — same visual pattern as campaigns/new/Stepper. */
export default function ImportStepper({ current }: { current: number }) {
  return (
    <div className="mb-6 flex flex-wrap gap-0">
      {STEPS.map((label, i) => {
        const step = i + 1;
        const done = step < current;
        const now = step === current;
        return (
          <div
            key={label}
            className="flex items-center gap-2"
            style={{
              padding: "8px 16px 8px 0",
              fontSize: ".78rem",
              color: now ? "var(--color-paper)" : done ? "var(--muted)" : "var(--faint)",
            }}
          >
            <b
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: ".62rem",
                width: 20,
                height: 20,
                borderRadius: "50%",
                border: `1px solid ${now ? "var(--color-accent)" : done ? "var(--color-ok)" : "var(--line-2)"}`,
                display: "grid",
                placeItems: "center",
                fontWeight: 400,
                background: now ? "var(--color-accent)" : "transparent",
                color: now ? "var(--color-accent-ink)" : done ? "var(--color-ok)" : "inherit",
              }}
            >
              {done ? "✓" : step}
            </b>
            {label}
            {step !== STEPS.length && (
              <span style={{ marginLeft: 6, color: "var(--line-2)" }}>→</span>
            )}
          </div>
        );
      })}
    </div>
  );
}
