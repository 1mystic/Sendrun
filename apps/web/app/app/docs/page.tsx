import Shell from "@/components/Shell";
import { PageTitle, SectionLabel } from "@/components/ui";

/**
 * In-app architecture reference. Exists because the reliability model is the point
 * of the product — a user watching jobs retry needs to understand what guarantees
 * they actually have.
 */

function Rule({ n, title, children }: { n: string; title: string; children: React.ReactNode }) {
  return (
    <div className="card">
      <div className="mb-2 flex items-baseline gap-3">
        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: ".62rem",
            color: "var(--color-accent)",
            letterSpacing: ".1em",
          }}
        >
          {n}
        </span>
        <h3 className="m-0 text-[.96rem] font-semibold tracking-[-.015em]">{title}</h3>
      </div>
      <div className="text-muted max-w-[74ch] text-[.84rem] leading-[1.65]">{children}</div>
    </div>
  );
}

export default function DocsPage() {
  return (
    <Shell crumb="How it works">
      <PageTitle
        title="How Sendrun works"
        lede="The guarantees behind the numbers on your dashboard, and where they stop."
      />

      <SectionLabel>The guarantee</SectionLabel>
      <div className="card mb-6">
        <p className="m-0 max-w-[70ch] text-[1rem] leading-[1.6]">
          Every recipient is an <b>independent, idempotent job</b>. Kill a worker
          mid-campaign and nothing is lost and nothing is sent twice.
        </p>
        <p className="text-muted m-0 mt-3 max-w-[70ch] text-[.84rem] leading-[1.6]">
          The queue gives at-least-once delivery: a lease expires and the job is
          re-picked. The provider&apos;s idempotency key gives at-most-once: a repeated
          key returns the original message instead of sending again. Together they give
          effectively-once. Neither half is sufficient alone.
        </p>
      </div>

      <SectionLabel>What happens when you launch</SectionLabel>
      <div className="mb-6 flex flex-col gap-3">
        <Rule n="01" title="Fan out">
          One <span className="font-mono">EmailJob</span> row per recipient is written in
          the same transaction as the campaign. Each carries its own retry budget and its
          own idempotency key — the job id itself, never a hash of the content.
        </Rule>
        <Rule n="02" title="Claim before sending">
          A worker takes a time-boxed lease, then makes a guarded write moving the job to{" "}
          <span className="font-mono">sending</span>. The guard is the mutex: two workers
          cannot both claim the same job.
        </Rule>
        <Rule n="03" title="Send, then record">
          The provider call carries the idempotency key. Only after it is accepted do we
          write the message id. If the process dies between those two steps, the retry
          re-sends, the provider recognises the key, and returns the{" "}
          <em>original</em> message id. No second email.
        </Rule>
        <Rule n="04" title="Reconcile from webhooks">
          Delivery state is driven by provider events, not by our own optimism. Events
          arrive duplicated and out of order, so each is applied only if it outranks what
          is already recorded — a late <span className="font-mono">delivered</span> can
          never overwrite a <span className="font-mono">bounced</span>.
        </Rule>
      </div>

      <SectionLabel>Two things people expect that are not true</SectionLabel>
      <div className="mb-6 grid gap-3 md:grid-cols-2">
        <div className="card" style={{ borderLeft: "3px solid var(--color-warn)" }}>
          <h4 className="m-0 mb-2 text-[.9rem] font-semibold">
            &ldquo;Completed&rdquo; does not mean &ldquo;delivered&rdquo;
          </h4>
          <p className="text-muted m-0 text-[.82rem] leading-[1.6]">
            A campaign completes when every send has been <b>attempted</b>. Provider
            events keep arriving for hours afterward. Waiting for them would be an
            unbounded wait with no clean end, so delivery settling is tracked separately.
          </p>
        </div>
        <div className="card" style={{ borderLeft: "3px solid var(--color-warn)" }}>
          <h4 className="m-0 mb-2 text-[.9rem] font-semibold">
            Spam risk is a heuristic, not a prediction
          </h4>
          <p className="text-muted m-0 text-[.82rem] leading-[1.6]">
            The preflight score reads link density, capitalisation, and promotional
            phrasing. It cannot know what any particular provider&apos;s filter will do,
            and does not claim to.
          </p>
        </div>
      </div>

      <SectionLabel>Where the guarantee stops</SectionLabel>
      <div className="card">
        <p className="text-muted m-0 max-w-[74ch] text-[.84rem] leading-[1.65]">
          The durable engine is built on Postgres leasing — not event-sourced replay. It
          gives crash recovery, retry with backoff, and a dead-letter queue. It does{" "}
          <b>not</b> give cross-process determinism or a workflow history you can replay
          step by step, the way a dedicated engine such as Temporal would. A send already
          in flight cannot be recalled, and cancelling a running campaign stops only the
          jobs that have not started.
        </p>
      </div>
    </Shell>
  );
}
