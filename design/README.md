# `design/prototypes/`

Self-contained HTML files — open any of them directly in a browser, no build step. These
are the **approved visual contract**: `apps/web/` was built by porting these, not the
other way around. If a frontend page and a prototype disagree, the prototype is the source
of truth until deliberately updated.

| File | What |
|---|---|
| `brand-directions.html` | Three brand-direction comparisons on one page — how the final Ledger palette + Signal typography combination got chosen |
| `sendrun-prototype.html` | The campaign console — dashboard, contacts, the compose flow, and **the live execution screen with a working kill-worker simulation** (a real client-side model of the crash-recovery sequence, timed to be legible) |
| `landing.html` | The marketing page |
| `auth.html` | All eight auth/onboarding screens (sign in, sign up, forgot password, 2FA, create org, invite team) with genuinely working interactions — password strength meter, 2FA auto-advance, live slug derivation |

## Brand tokens

Ledger palette (ink `#14110F`, paper `#F5F1E8`, vermillion `#E4491F` — the *only* accent
hue) with Signal typography (Space Grotesk, tight negative tracking), 3px border radius,
JetBrains Mono at weight 600–700 on every button/pill/chip. Semantic color (ok, warn, crit)
is kept separate from the accent — vermillion means *running/attention*, never *error*.
See [`../CLAUDE.md`](../CLAUDE.md) for the full token table.
