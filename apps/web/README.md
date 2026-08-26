# `apps/web/`

Next.js 16 + TypeScript + Tailwind 4. Run: `npm install && npm run dev`, serves `:3000`.

Copy `.env.example` to `.env.local`. Leave `NEXT_PUBLIC_API_URL` empty for mock-data mode;
set it to a running FastAPI backend to switch every wired page to live data.

## Routes

**Public** (`app/(marketing)/`, `app/(auth)/`) — the route-group parentheses are folder
names only, not URL segments:

- `/` — landing page. The durability-thesis worked example is the centerpiece.
- `/signin` `/signup` `/forgot` `/check-email` `/reset` `/two-factor` `/create-org` `/invite`
  — **live**: sign-in/up/create-org call the real API and store the session cookie + current
  org id.

**App** (`app/app/`):

| Route | Status | What |
|---|---|---|
| `/app` | live | Overview — real campaign/contact counts |
| `/app/campaigns` | live | Campaign list |
| `/app/campaigns/new` → `/new/preflight` → `/new/approve` | live | Compose → real AI preflight → real launch |
| `/app/campaigns/[id]` | **live + demo** | Real progress polling (`LiveCampaignView`) when `NEXT_PUBLIC_API_URL` is set; falls back to a client-side kill-worker simulation (`DemoCampaignView`) in mock mode — that simulation is the interview/demo centerpiece and is deliberately not backed by real data, see below |
| `/app/contacts`, `/app/contacts/[id]` | live | Real contact list/detail, delete wired |
| `/app/lists`, `/app/lists/new`, `/app/lists/[id]`, `/app/lists/import/[groupId]` | live | Mailing lists — create a named group, then import recipients by pasting text (auto delimiter/header detection) or uploading CSV/Excel, map columns to email/name/custom `{{variables}}`, preview, import. Upserts on re-import; never touches an existing suppression. |
| `/app/templates` | live | Full CRUD — create, edit (always versions, never overwrites), archive. Every new org is seeded with starter templates. |
| `/app/jobs` | live (read-only) | Durable-engine dead-letter/in-flight task inspector |
| `/app/notifications` | live | Reads the org's audit log |
| `/app/analytics` | live | Real per-campaign delivered/bounced/opened/clicked aggregates |
| `/app/settings` | partially live | Org name + team members are real; sending/provider/danger-zone controls are visibly disabled — no backend field exists for them yet, see below |
| `/app/chaos` | mock only | Tunes `FakeEmailProvider`'s in-process chaos config — there's no live provider for this to mean anything against, see below |
| `/app/campaigns/[id]/report` | mock | Completion report |
| `/app/docs` | static | In-app architecture reference |

## Design system

`app/globals.css` defines the approved brand tokens as Tailwind `@theme` values — Ledger
palette (ink `#14110F`, paper `#F5F1E8`, vermillion `#E4491F` as the *only* accent), Signal
typography (Space Grotesk, tight negative tracking), 3px radius, mono 600–700 weight on
every button/pill/chip. `design/prototypes/*.html` at the repo root are the approved
visual contract this was ported from — match them rather than reinventing.

Semantic color (ok `#7FB069`, warn `#D9A441`, crit `#E4491F`) is kept separate from the
accent hue on purpose: vermillion means *running/attention*, not *error*.

## The mock/live seam

`lib/api.ts` is the one file every page calls through — never `fetch` directly. Every
function has a `useMocks` branch (true when `NEXT_PUBLIC_API_URL` is unset) that resolves
from `lib/mock.ts`/`lib/mock-ops.ts`/`lib/mock-notifications.ts` instead of hitting the
network, so the app is always runnable with zero backend. Setting `NEXT_PUBLIC_API_URL`
flips every wired page to the real FastAPI backend with no other code change.
`getCurrentOrgId()`/`setCurrentOrgId()` (localStorage) and `getCampaignDraft()`/
`setCampaignDraft()` (sessionStorage) carry org/campaign context across page boundaries the
router alone can't (auth → app, compose → preflight → launch).

## What's deliberately still mock or partial, and why

- **`/app/chaos`** — chaos config tunes `FakeEmailProvider` in-process; there's no
  Redis-backed live config it reads at runtime yet, so wiring this "live" would be
  cosmetic. Left as a demo-mode-only panel.
- **`/app/campaigns/[id]`'s kill-worker simulation** — intentionally not real data even in
  live mode. It demonstrates the actual crash-recovery mechanism (lease orphan → reaper →
  re-pick → idempotency hit) at a legible pace; the real `ProgressOut` payload from the
  backend doesn't carry per-worker/per-lease detail, so faking that level of detail against
  live data would be dishonest. `LiveCampaignView` (real counts, 2s poll) is what live mode
  actually shows.
- **`/app/settings`** — sending-rate-cap, provider switching, and org deletion have no
  backend field/endpoint yet. Rather than a save button that silently no-ops, these
  controls render visibly disabled with a "not yet configurable" note.

## Notable implementation details

- **Mailing-list import** (`lib/import.ts`) — delimiter detection tries comma, then tab,
  then runs of 2+ spaces, then single space, in that order, so "John Smith" in a pasted
  name column isn't misread as two columns when a stronger delimiter exists. A first line
  with no `@` is treated as a header row; a first line containing `@` (headerless paste) is
  given synthetic `Column 1, Column 2, …` labels instead. File uploads always treat row 1
  as headers. Parsing (`papaparse` for CSV, `xlsx`/SheetJS for Excel) runs entirely
  client-side — **`xlsx` currently has an unpatched high-severity advisory
  (GHSA-4r6h-8v6p-xvw6, GHSA-5pgg-2g8v-p4x9, no fix on npm)**; acceptable for now since
  files never leave the browser, but re-run `npm audit` before shipping this feature to
  real users and swap the dependency if a patched release lands.
- **Mobile nav** is a slide-in drawer with a real focus trap and Escape-to-close, not a
  CSS-only toggle.
- **Auth pages** split brand-pane/form-pane by CSS grid column order, not DOM reordering —
  keeps the form first in source order for keyboard and screen-reader users regardless of
  which side it renders on visually.
