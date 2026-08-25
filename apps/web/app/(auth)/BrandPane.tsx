import { Pill } from "@/components/ui";

/** Static campaign panel used on the auth split-screen brand pane. */
export default function BrandPane() {
  return (
    <aside className="a-brandpane">
      <div>
        <div className="a-brand-lockup" style={{ marginBottom: 0 }}>
          <span className="a-mark" /> Sendrun
        </div>
        <p className="a-thesis">
          Every recipient is an independent, <span className="accent">idempotent</span> job.
        </p>

        <div className="card a-mockcard">
          <div className="row-between">
            <div>
              <div style={{ fontWeight: 600, fontSize: ".9rem", letterSpacing: "-.01em" }}>
                Hackathon Speaker Outreach
              </div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: ".62rem", color: "var(--faint)", marginTop: 3 }}>
                campaign_8231 &middot; running
              </div>
            </div>
            <Pill tone="run" pulse>
              Live
            </Pill>
          </div>
          <div className="a-bar">
            <i style={{ width: "59%", background: "var(--color-ok)" }} />
            <i style={{ width: "8%", background: "var(--color-accent)" }} />
            <i style={{ width: "3%", background: "var(--color-warn)" }} />
            <i style={{ width: "2%", background: "rgba(228,73,31,.42)" }} />
          </div>
          <div className="a-mini-stats">
            <div className="a-mini-stat g">
              <u>97.4%</u>
              <span>Delivered</span>
            </div>
            <div className="a-mini-stat">
              <u>8/sec</u>
              <span>Send rate</span>
            </div>
          </div>
          <div className="a-proof-row">
            <span>Duplicate sends</span>
            <b className="num">0</b>
          </div>
        </div>
      </div>
    </aside>
  );
}
