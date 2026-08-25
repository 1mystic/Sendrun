"use client";

import { evaluateStrength } from "./strength";

/** Password strength bar + label, driven by the password value. */
export default function StrengthMeter({ password }: { password: string }) {
  const { pct, color, label } = evaluateStrength(password);

  return (
    <div className="a-strength" aria-live="polite">
      <div className="a-bar">
        <i style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="a-lbl">
        Strength: <b style={{ color: password ? color : "var(--faint)" }}>{label}</b>
      </span>
    </div>
  );
}
