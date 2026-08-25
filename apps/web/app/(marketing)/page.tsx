import Link from "next/link";
import Reveal from "./Reveal";
import LivePanel from "./LivePanel";

export default function LandingPage() {
  return (
    <>
      {/* ══════ NAV ══════ */}
      <nav className="m-nav">
        <div className="m-wrap">
          <Link className="m-brand" href="#top">
            <span className="m-mark" /> Sendrun
          </Link>
          <div className="m-navlinks">
            <a href="#how">Platform</a>
            <a href="#durability">Reliability</a>
            <a href="#docs">Docs</a>
            <a href="#pricing">Pricing</a>
          </div>
          <div className="m-navactions">
            <Link href="/signin" className="btn btn-ghost btn-sm">
              Sign in
            </Link>
            <Link href="/signup" className="btn btn-sm">
              Start free
            </Link>
          </div>
        </div>
      </nav>

      {/* ══════ HERO ══════ */}
      <header className="m-hero" id="top">
        <div className="m-wrap m-hero-grid">
          <div>
            <div className="m-eyebrow">
              <span className="m-dot" /> Now reconciling 24,918 sends in production
            </div>
            <h1 className="m-hero-h">
              Every send is a job that <em>cannot</em> duplicate itself.
            </h1>
            <p className="m-hero-lede">
              Sendrun runs email campaigns as independent, idempotent jobs. Kill a
              worker mid-campaign — nothing is lost, and nothing is sent twice. AI
              checks your campaign before launch; it never sends without you.
            </p>
            <div className="m-hero-cta">
              <Link href="/signup" className="btn">
                Start free
              </Link>
              <a href="#how" className="btn btn-ghost">
                See how it works
              </a>
            </div>
            <div className="m-hero-proof">
              <span>
                <b>0</b> duplicate sends
              </span>
              <span>&middot;</span>
              <span>
                <b>97.4%</b> delivery
              </span>
              <span>&middot;</span>
              <span>
                <b>100%</b> events reconciled
              </span>
            </div>
          </div>

          <Reveal className="relative">
            <LivePanel />
          </Reveal>
        </div>
      </header>

      {/* ══════ PROOF STRIP ══════ */}
      <section className="m-proof">
        <div className="m-wrap">
          <Reveal as="div" className="m-proof-item" delayIndex={0}>
            <u className="num">0</u>
            <span>Duplicate sends across 24,918 emails delivered</span>
          </Reveal>
          <Reveal as="div" className="m-proof-item" delayIndex={1}>
            <u className="num">97.4%</u>
            <span>Average delivery rate across all campaigns</span>
          </Reveal>
          <Reveal as="div" className="m-proof-item" delayIndex={2}>
            <u className="num">5</u>
            <span>Retry attempts per job before dead-lettering</span>
          </Reveal>
          <Reveal as="div" className="m-proof-item" delayIndex={3}>
            <u className="num">100%</u>
            <span>Provider events reconciled to a final state</span>
          </Reveal>
        </div>
      </section>

      {/* ══════ HOW IT WORKS ══════ */}
      <section className="m-section" id="how">
        <div className="m-wrap">
          <Reveal className="m-section-head">
            <p className="m-section-eyebrow">Platform</p>
            <h2 className="m-section-h">Five steps, in order, every time.</h2>
            <p className="m-section-p">
              A campaign moves through a fixed sequence. Nothing skips a step, and
              every step leaves a record.
            </p>
          </Reveal>
          <div className="m-flow">
            {[
              {
                n: "01",
                title: "Select",
                body: "Resolve recipients from tags, groups, or a smart filter into a fixed list before anything else runs.",
              },
              {
                n: "02",
                title: "Compose",
                body: "Write once with personalization variables. Preview exactly how each recipient will see it.",
              },
              {
                n: "03",
                title: "Preflight",
                body: "AI checks links, missing variables, and spam risk. You review every flag before approving.",
              },
              {
                n: "04",
                title: "Execute",
                body: "Each recipient becomes an independent job with its own retry budget, sent under an idempotency key.",
              },
              {
                n: "05",
                title: "Reconcile",
                body: "Provider webhooks settle delivery state for hours after completion, deduplicated and ranked.",
              },
            ].map((step, i) => (
              <Reveal key={step.n} as="div" className="m-flow-step" delayIndex={i}>
                <div className="m-flow-num">{step.n}</div>
                <h3>{step.title}</h3>
                <p>{step.body}</p>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* ══════ DURABILITY ══════ */}
      <section className="m-section m-durability" id="durability">
        <div className="m-wrap">
          <Reveal className="m-section-head">
            <p className="m-section-eyebrow">Reliability</p>
            <h2 className="m-section-h">Kill a worker. Watch nothing break.</h2>
            <p className="m-section-p">
              This is the guarantee the whole system is built around. A worker can
              die at any point, mid-send, with no cleanup — and the campaign still
              finishes with exactly one send per recipient.
            </p>
          </Reveal>

          <div className="m-dur-grid">
            <Reveal>
              <div className="card">
                <div className="sec">Why it holds</div>
                <p className="text-muted" style={{ fontSize: ".85rem", lineHeight: 1.7, margin: "0 0 14px" }}>
                  Every job is claimed with a time-boxed lease, not a permanent
                  assignment. If the worker holding it disappears, the lease
                  simply runs out — no signal from the dead worker is required.
                </p>
                <p className="text-muted" style={{ fontSize: ".85rem", lineHeight: 1.7, margin: 0 }}>
                  A background reaper watches for expired leases and returns
                  those jobs to pending. Whichever worker picks a job up next
                  sends under the{" "}
                  <b style={{ color: "var(--color-paper)" }}>same idempotency key</b>{" "}
                  the first attempt would have used — so if the dead worker&apos;s
                  request actually reached the provider, the retry is recognized
                  and discarded, not duplicated.
                </p>
              </div>
              <div className="m-invariant">
                <span className="n num">0</span>
                <span className="t">
                  duplicate sends, held through any number of crashes — the one
                  invariant that cannot break
                </span>
              </div>
            </Reveal>

            <Reveal className="card">
              <div className="sec">job_4f9a&middot;c21e — timeline</div>
              <div className="m-timeline">
                <div className="m-tl-item">
                  <div className="m-tl-time">14:03:19.402</div>
                  <h4>Lease acquired</h4>
                  <p>
                    <span className="kv">worker_a</span> claims the job, 30s lease.
                  </p>
                </div>
                <div className="m-tl-item warn">
                  <div className="m-tl-time">14:03:21.118</div>
                  <h4>Worker dies mid-send</h4>
                  <p>
                    No provider call was made. The lease is now orphaned —
                    nobody is coming back for it.
                  </p>
                </div>
                <div className="m-tl-item crit">
                  <div className="m-tl-time">14:03:49.402</div>
                  <h4>Lease expires</h4>
                  <p>
                    The reaper notices the lease timed out and returns the job
                    to <span className="kv">pending</span>.
                  </p>
                </div>
                <div className="m-tl-item">
                  <div className="m-tl-time">14:03:50.006</div>
                  <h4>Re-picked</h4>
                  <p>
                    <span className="kv">worker_c</span> claims the job fresh.
                    No message_id on record — safe to send.
                  </p>
                </div>
                <div className="m-tl-item ok">
                  <div className="m-tl-time">14:03:50.204</div>
                  <h4>Sent, once</h4>
                  <p>
                    Provider accepts under idempotency key{" "}
                    <span className="kv">job_4f9a&middot;c21e</span>. Duplicate
                    sends: still zero.
                  </p>
                </div>
              </div>
            </Reveal>
          </div>
        </div>
      </section>

      {/* ══════ AI PREFLIGHT ══════ */}
      <section className="m-section" id="preflight">
        <div className="m-wrap">
          <div className="m-preflight-grid">
            <Reveal>
              <p className="m-section-eyebrow">AI preflight</p>
              <h2 className="m-section-h">It recommends. You approve.</h2>
              <p className="m-section-p">
                Before a single email goes out, AI checks the campaign for
                problems a human would otherwise catch too late — missing
                personalization, broken links, addresses likely to bounce. It
                flags every issue with a specific fix. It never sends anything
                on its own.
              </p>
              <div className="m-recommend-badge">
                Preflight <b>recommends</b> — a person <b>approves</b>
              </div>
            </Reveal>

            <Reveal className="card">
              <div className="sec">Preflight report &middot; campaign_8231</div>
              <div style={{ display: "flex", gap: 20, flexWrap: "wrap", marginBottom: 6 }}>
                <div className="m-gauge">
                  <u style={{ color: "var(--color-warn)" }}>91</u>
                  <span>
                    / 100
                    <br />
                    personalization
                  </span>
                </div>
                <div className="m-gauge">
                  <u style={{ color: "var(--color-ok)" }}>18</u>
                  <span>
                    / 100
                    <br />
                    spam risk
                  </span>
                </div>
                <div className="m-gauge">
                  <u style={{ color: "var(--color-ok)" }}>
                    96.1<span style={{ fontSize: ".5em" }}>%</span>
                  </u>
                  <span>
                    predicted
                    <br />
                    delivery
                  </span>
                </div>
              </div>
              <div style={{ marginTop: 8 }}>
                <div className="m-check">
                  <span className="ic" style={{ color: "var(--color-warn)" }}>
                    ⚠
                  </span>
                  <div>
                    <h4>
                      7 recipients missing <span className="m-var">specialization</span>
                    </h4>
                    <p>
                      The sentence referencing it would read broken. Set a
                      fallback, or exclude these 7.
                    </p>
                  </div>
                </div>
                <div className="m-check">
                  <span className="ic" style={{ color: "var(--color-crit)" }}>
                    ✕
                  </span>
                  <div>
                    <h4>5 addresses are high bounce risk</h4>
                    <p>
                      Previously hard-bounced or inactive 18+ months. Sending
                      costs sender reputation.
                    </p>
                  </div>
                </div>
                <div className="m-check">
                  <span className="ic" style={{ color: "var(--color-ok)" }}>
                    ✓
                  </span>
                  <div>
                    <h4>All links resolve</h4>
                    <p>1 link checked &middot; 200 OK &middot; no redirect chain.</p>
                  </div>
                </div>
              </div>
            </Reveal>
          </div>
        </div>
      </section>

      {/* ══════ FEATURE GRID ══════ */}
      <section className="m-section" id="features">
        <div className="m-wrap">
          <Reveal className="m-section-head">
            <p className="m-section-eyebrow">Under the hood</p>
            <h2 className="m-section-h">
              Built for what happens when things go wrong.
            </h2>
            <p className="m-section-p">
              Most email tools are designed for the happy path. Sendrun is
              designed for the rest of it.
            </p>
          </Reveal>
          <div className="m-fgrid">
            {[
              {
                title: "Independent jobs",
                body: "Every recipient is its own job with its own state, retry count, and backoff schedule. One failure never touches another recipient's send.",
                icon: (
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7}>
                    <rect x="4" y="4" width="6" height="6" rx="1" />
                    <rect x="14" y="4" width="6" height="6" rx="1" />
                    <rect x="4" y="14" width="6" height="6" rx="1" />
                    <rect x="14" y="14" width="6" height="6" rx="1" />
                  </svg>
                ),
              },
              {
                title: "Idempotent sends",
                body: "Every send carries an idempotency key. A retry, a webhook replay, or a re-picked job can never turn into a duplicate email.",
                icon: (
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7}>
                    <path d="M9 12l2 2 4-4" />
                    <circle cx="12" cy="12" r="9" />
                  </svg>
                ),
              },
              {
                title: "Crash recovery",
                body: "Leases expire automatically. A reaper returns orphaned jobs to pending so another worker finishes what a dead one started.",
                icon: (
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7}>
                    <path d="M12 3v4" />
                    <circle cx="12" cy="12" r="4" />
                    <path d="M12 17v4" />
                    <path d="m5 7 3 2" />
                    <path d="m16 15 3 2" />
                  </svg>
                ),
              },
              {
                title: "Webhook reconciliation",
                body: "Provider events drive true delivery state. Duplicate and out-of-order events are deduplicated and applied by precedence rank.",
                icon: (
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7}>
                    <path d="M4 6h16M4 12h16M4 18h10" />
                  </svg>
                ),
              },
              {
                title: "AI preflight",
                body: "Links, personalization variables, and spam risk are checked before launch. It flags and recommends — a person always approves.",
                icon: (
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7}>
                    <path d="m13 2-9 12h7l-2 8 9-12h-7z" />
                  </svg>
                ),
              },
              {
                title: "ML recipient intelligence",
                body: "Bounce risk and engagement are predicted per recipient from send history, so you know who's at risk before you send.",
                icon: (
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7}>
                    <circle cx="9" cy="8" r="3" />
                    <path d="M3 20a6 6 0 0 1 12 0" />
                    <path d="M16 6a3 3 0 0 1 0 6" />
                    <path d="M18 20a5 5 0 0 0-2-4" />
                  </svg>
                ),
              },
            ].map((f, i) => (
              <Reveal key={f.title} as="div" className="m-feature" delayIndex={i}>
                <div className="fi">{f.icon}</div>
                <h3>{f.title}</h3>
                <p>{f.body}</p>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* ══════ FINAL CTA ══════ */}
      <section className="m-finalcta">
        <div className="m-wrap">
          <Reveal as="header">
            <h2>Send campaigns that survive their own infrastructure.</h2>
          </Reveal>
          <Reveal as="header">
            <p>
              No duplicate sends. No lost jobs. No manual reconciliation. Start
              a campaign in minutes.
            </p>
          </Reveal>
          <Reveal>
            <Link href="/signup" className="btn">
              Start free
            </Link>
          </Reveal>
        </div>
      </section>

      {/* ══════ FOOTER ══════ */}
      <footer className="m-foot">
        <div className="m-wrap">
          <div className="m-foot-grid">
            <div className="m-foot-brand">
              <Link className="m-brand" href="#top">
                <span className="m-mark" /> Sendrun
              </Link>
              <p>
                A durable, AI-assisted email campaign platform. Every recipient
                is an independent, idempotent job.
              </p>
            </div>
            <div className="m-foot-col">
              <h5>Product</h5>
              <a href="#how">Platform</a>
              <a href="#durability">Reliability</a>
              <a href="#preflight">AI preflight</a>
              <a href="#pricing">Pricing</a>
            </div>
            <div className="m-foot-col">
              <h5>Docs</h5>
              <a href="#docs">Getting started</a>
              <a href="#docs">API reference</a>
              <a href="#docs">Job inspector</a>
              <a href="#docs">Chaos mode</a>
            </div>
            <div className="m-foot-col">
              <h5>Company</h5>
              <a href="#about">About</a>
              <a href="#contact">Contact</a>
              <a href="#status">Status</a>
            </div>
          </div>
          <div className="m-foot-bottom">
            <span>&copy; 2026 Sendrun</span>
            <span className="m-foot-note">
              A final-year engineering project —{" "}
              <b>
                built to demonstrate durable, at-least-once-but-never-twice
                delivery.
              </b>
            </span>
          </div>
        </div>
      </footer>
    </>
  );
}
