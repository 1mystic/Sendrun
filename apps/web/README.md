# `apps/web/`

Next.js 16 + TypeScript + Tailwind 4. Run: `npm install && npm run dev`, serves `:3000`.

**Currently runs entirely against mock data** — `lib/api.ts` is the seam that will be
pointed at the real FastAPI backend; see below.

## Routes

**Public** (`app/(marketing)/`, `app/(auth)/`) — the route-group parentheses are folder
names only, not URL segments:

- `/` — landing page. The durability-thesis worked example is the centerpiece.
- `/signin` `/signup` `/forgot` `/check-email` `/reset` `/two-factor` `/create-org` `/invite`

**App** (`app/app/`):

| Route | What |
|---|---|
| `/app` | Overview |
| `/app/campaigns` → `/new` → `/new/preflight` → `/new/approve` | The compose flow |
| `/app/campaigns/[id]` | **Live execution + the kill-worker demo** — the centerpiece screen |
| `/app/campaigns/[id]/report` | Completion report |
| `/app/contacts`, `/app/templates`, `/app/analytics`, `/app/notifications`, `/app/settings` | |
| `/app/jobs` | Job inspector — a real per-attempt crash-and-recovery timeline |
| `/app/chaos` | Failure-injection knobs, mirroring `packages/shared/providers/fake.ChaosConfig` |
| `/app/docs` | In-app architecture reference |

## Design system

`app/globals.css` defines the approved brand tokens as Tailwind `@theme` values — Ledger
palette (ink `#14110F`, paper `#F5F1E8`, vermillion `#E4491F` as the *only* accent), Signal
typography (Space Grotesk, tight negative tracking), 3px radius, mono 600–700 weight on
every button/pill/chip. `design/prototypes/*.html` at the repo root are the approved
visual contract this was ported from — match them rather than reinventing.

Semantic color (ok `#7FB069`, warn `#D9A441`, crit `#E4491F`) is kept separate from the
accent hue on purpose: vermillion means *running/attention*, not *error*.

## Wiring to the real backend

`lib/api.ts` is the one file every page calls through — never `fetch` directly. Today its
functions resolve from `lib/mock.ts`; setting `NEXT_PUBLIC_API_URL` switches every call to
the real FastAPI backend with no other code change. The mock data layer
(`lib/mock.ts`, `lib/mock-ops.ts`, `lib/mock-notifications.ts`) mirrors the backend's
actual Pydantic response shapes, so the swap is mechanical once the backend endpoints it
targets exist (most do — see [`../../services/api/README.md`](../../services/api/README.md)).

## Notable implementation details

- **The live execution screen's kill-worker button** runs a real client-side simulation of
  the crash-recovery sequence (worker dies → lease orphans → reaper requeues → re-pick →
  idempotency hit, duplicate count stays 0) — it's demonstrating the actual mechanism the
  backend implements, timed to be legible, not a fake animation.
- **Mobile nav** is a slide-in drawer with a real focus trap and Escape-to-close, not a
  CSS-only toggle.
- **Auth pages** split brand-pane/form-pane by CSS grid column order, not DOM reordering —
  keeps the form first in source order for keyboard and screen-reader users regardless of
  which side it renders on visually.

## Not yet built

- Real API calls (currently all mock)
- The AI preflight page's data comes from `lib/mock.ts`'s static `PREFLIGHT` object; the
  real backend endpoint (`POST /api/organizations/{org_id}/preflight`) already exists and
  returns the same shape — see `services/api/routers/preflight.py`.
