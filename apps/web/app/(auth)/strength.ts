/** Password strength scoring ported from design/prototypes/auth.html. */

export function scorePassword(pw: string): number {
  if (!pw) return 0;
  let score = 0;
  if (pw.length >= 8) score++;
  if (pw.length >= 12) score++;
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) score++;
  if (/[0-9]/.test(pw)) score++;
  if (/[^A-Za-z0-9]/.test(pw)) score++;
  return score; // 0..5
}

export type StrengthResult = {
  pct: number;
  color: string;
  label: string;
};

/** Colors are ok/warn/crit tokens per the brand contract — never the accent. */
export function evaluateStrength(pw: string): StrengthResult {
  const score = scorePassword(pw);
  if (!pw) return { pct: 0, color: "var(--color-crit)", label: "enter a password" };
  if (score <= 1) return { pct: 25, color: "var(--color-crit)", label: "weak" };
  if (score <= 3) return { pct: 60, color: "var(--color-warn)", label: "fair" };
  return { pct: 100, color: "var(--color-ok)", label: "strong" };
}
