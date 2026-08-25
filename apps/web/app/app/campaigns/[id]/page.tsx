"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import Shell from "@/components/Shell";
import { SectionLabel } from "@/components/ui";
import { NAMES } from "@/lib/mock";

const TOTAL = 122;
const MAX_FEED_ROWS = 60;

interface Worker {
  id: string;
  n: number;
  up: boolean;
}

interface FeedRow {
  key: number;
  time: string;
  icon: string;
  cls: "g" | "w" | "c" | "";
  who: string;
  what: string;
}

interface SimState {
  d: number;
  s: number;
  r: number;
  f: number;
  done: number;
  calls: number;
  ids: number;
  hits: number;
  orph: number;
  dupes: number;
  paused: boolean;
  killed: boolean;
  over: boolean;
  workers: Worker[];
}

function freshState(): SimState {
  return {
    d: 0,
    s: 0,
    r: 0,
    f: 0,
    done: 0,
    calls: 0,
    ids: 0,
    hits: 0,
    orph: 0,
    dupes: 0,
    paused: false,
    killed: false,
    over: false,
    workers: [
      { id: "worker_a", n: 0, up: true },
      { id: "worker_b", n: 0, up: true },
      { id: "worker_c", n: 0, up: true },
    ],
  };
}

function randomName() {
  return NAMES[Math.floor(Math.random() * NAMES.length)] + "@…";
}

export default function LiveCampaignPage() {
  const params = useParams<{ id: string }>();
  const campaignId = params.id;

  const [state, setState] = useState<SimState>(() => freshState());
  const [feedRows, setFeedRows] = useState<FeedRow[]>([]);
  const [killBanner, setKillBanner] = useState<{ detail: string } | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [killDisabled, setKillDisabled] = useState(false);

  const stateRef = useRef(state);
  const tick0Ref = useRef(0);
  const feedKeyRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timeoutsRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  function clockLabel() {
    const s = Math.floor((Date.now() - tick0Ref.current) / 1000);
    return String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");
  }

  function pushFeed(icon: string, cls: FeedRow["cls"], who: string, what: string) {
    feedKeyRef.current += 1;
    const row: FeedRow = { key: feedKeyRef.current, time: clockLabel(), icon, cls, who, what };
    setFeedRows((prev) => [row, ...prev].slice(0, MAX_FEED_ROWS));
  }

  function scheduleTimeout(fn: () => void, ms: number) {
    const id = setTimeout(fn, ms);
    timeoutsRef.current.push(id);
    return id;
  }

  function step() {
    setState((prevState) => {
      if (prevState.paused || prevState.over) return prevState;
      const st: SimState = { ...prevState, workers: prevState.workers.map((w) => ({ ...w })) };

      // resolve in-flight sends
      if (st.s > 0 && Math.random() < 0.8) {
        st.s -= 1;
        const who = randomName();
        const roll = Math.random();
        if (roll < 0.04) {
          st.f += 1;
          st.done += 1;
          pushFeed("✕", "c", who, "bounced · 550");
        } else if (roll < 0.1) {
          st.r += 1;
          pushFeed("↻", "w", who, "retry · 503");
          scheduleTimeout(() => {
            setState((s2) => {
              if (s2.over) return s2;
              const next = { ...s2 };
              next.r -= 1;
              next.d += 1;
              next.done += 1;
              next.calls += 1;
              next.ids += 1;
              return next;
            });
            pushFeed("✓", "g", who, "delivered · attempt 2");
          }, 900 + Math.random() * 700);
        } else {
          st.d += 1;
          st.done += 1;
          pushFeed("✓", "g", who, "delivered");
        }
      }

      // dispatch new sends
      const inflight = st.s;
      const remaining = TOTAL - st.done - st.s - st.r;
      if (remaining > 0 && inflight < 9) {
        const up = st.workers.filter((w) => w.up);
        const n = Math.min(remaining, 1 + Math.floor(Math.random() * 3), 9 - inflight);
        for (let i = 0; i < n; i++) {
          st.s += 1;
          st.calls += 1;
          st.ids += 1;
          if (up.length) {
            const chosen = up[Math.floor(Math.random() * up.length)];
            const w = st.workers.find((w2) => w2.id === chosen.id);
            if (w) w.n += 1;
          }
          if (Math.random() < 0.06) st.orph += 1;
        }
      }

      if (st.done >= TOTAL) {
        st.over = true;
        if (timerRef.current) {
          clearInterval(timerRef.current);
          timerRef.current = null;
        }
        pushFeed("■", "g", "campaign", "all sends attempted");
        const orphAtCompletion = st.orph;
        scheduleTimeout(() => {
          if (orphAtCompletion > 0) {
            setState((s2) => ({ ...s2, orph: 0 }));
            pushFeed("✓", "g", "sweeper", "all orphan events resolved");
          }
        }, 1200);
      }

      return st;
    });
  }

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  useEffect(() => {
    tick0Ref.current = Date.now();
    timerRef.current = setInterval(step, 260);
    const clockTimer = setInterval(() => setElapsedMs(Date.now() - tick0Ref.current), 500);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      clearInterval(clockTimer);
      timeoutsRef.current.forEach((id) => clearTimeout(id));
      timeoutsRef.current = [];
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [campaignId]);

  function togglePause() {
    setState((prev) => {
      const next = { ...prev, paused: !prev.paused };
      pushFeed(next.paused ? "⏸" : "▶", "w", "campaign", next.paused ? "paused by operator" : "resumed");
      return next;
    });
  }

  function killWorker() {
    const st = stateRef.current;
    const victim = st.workers.find((w) => w.up);
    if (!victim || st.over) return;

    setKillDisabled(true);

    const orphaned = Math.min(st.s, 3);

    setState((prev) => {
      const next = { ...prev, workers: prev.workers.map((w) => ({ ...w })) };
      const v = next.workers.find((w) => w.id === victim.id);
      if (v) v.up = false;
      next.s -= orphaned;
      next.calls += orphaned;
      return next;
    });

    setKillBanner({ detail: `${orphaned} lease${orphaned === 1 ? "" : "s"} orphaned.` });
    pushFeed("✕", "c", victim.id, "process killed — leases orphaned");

    scheduleTimeout(() => {
      if (stateRef.current.over) return;
      pushFeed("↻", "w", "reaper", `${orphaned} expired leases → requeued`);
    }, 900);

    scheduleTimeout(() => {
      if (stateRef.current.over) return;
      setState((prev) => ({ ...prev, hits: prev.hits + orphaned, s: prev.s + orphaned }));
      pushFeed("✓", "g", "worker_c", `${orphaned} jobs re-picked · idempotency hit, no resend`);
    }, 1800);

    scheduleTimeout(() => {
      if (stateRef.current.over) return;
      setState((prev) => {
        const next = { ...prev, workers: prev.workers.map((w) => ({ ...w })) };
        const v = next.workers.find((w) => w.id === victim.id);
        if (v) {
          v.up = true;
          v.n = 0;
        }
        return next;
      });
      pushFeed("●", "g", victim.id, "restarted and rejoined");
    }, 3400);
  }

  const pct = (v: number) => (TOTAL > 0 ? (v / TOTAL) * 100 : 0);
  const elapsedS = Math.floor(elapsedMs / 1000);
  const elapsedLabel =
    String(Math.floor(elapsedS / 60)).padStart(2, "0") + ":" + String(elapsedS % 60).padStart(2, "0");

  return (
    <Shell crumb="Live execution">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="m-0 mb-1.5 text-[clamp(1.5rem,3vw,2.1rem)] font-bold leading-[1.02] tracking-[-.035em] text-balance">
            Hackathon Speaker Outreach
          </h1>
          <p
            className="m-0"
            style={{ fontFamily: "var(--font-mono)", fontSize: ".74rem", color: "var(--muted)" }}
          >
            {campaignId} · launched 14:01:04 · <span className="num">{elapsedLabel}</span> elapsed
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-[9px]">
          {state.over ? (
            <span className="pill pill-ok">
              <span className="inline-block h-[5px] w-[5px] rounded-full bg-current" />
              Completed
            </span>
          ) : state.paused ? (
            <span className="pill pill-warn">
              <span className="inline-block h-[5px] w-[5px] rounded-full bg-current" />
              Paused
            </span>
          ) : (
            <span className="pill pill-run">
              <span
                className="inline-block h-[5px] w-[5px] rounded-full bg-current"
                style={{ animation: "blink 1.6s cubic-bezier(.16,1,.3,1) infinite" }}
              />
              Running
            </span>
          )}
          <button type="button" className="btn btn-ghost btn-sm" disabled={state.over} onClick={togglePause}>
            {state.paused ? "Resume" : "Pause"}
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            disabled={state.over || killDisabled}
            onClick={killWorker}
            style={{ borderColor: "rgba(228,73,31,.5)", color: "var(--color-accent)" }}
          >
            Kill worker
          </button>
        </div>
      </div>

      {killBanner && (
        <div className="mb-[18px]">
          <div
            style={{
              border: "1px solid rgba(228,73,31,.4)",
              background: "var(--accent-dim)",
              borderRadius: 3,
              padding: "13px 15px",
              display: "flex",
              gap: 12,
              alignItems: "center",
              flexWrap: "wrap",
            }}
          >
            <p style={{ margin: 0, fontSize: ".82rem", lineHeight: 1.5 }}>
              <b style={{ color: "var(--color-accent)" }}>Worker killed mid-flight.</b>{" "}
              {killBanner.detail} The reaper expires them, and the jobs are re-picked by another
              worker. Idempotency keys mean the re-run cannot duplicate a send.
            </p>
          </div>
        </div>
      )}

      <div className="card mb-[18px]">
        <div className="mb-3 flex items-center justify-between">
          <span
            className="num"
            style={{ fontSize: "1.9rem", fontWeight: 700, letterSpacing: "-.04em" }}
          >
            {state.done.toLocaleString()}
          </span>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: ".74rem", color: "var(--muted)" }}>
            of <b className="num" style={{ color: "var(--color-paper)" }}>{TOTAL}</b> attempted
          </span>
        </div>
        <div className="flex overflow-hidden" style={{ height: 9, background: "var(--line)" }}>
          <span
            style={{
              display: "block",
              height: "100%",
              width: `${pct(state.d)}%`,
              background: "var(--color-ok)",
              transition: "width .5s cubic-bezier(.16,1,.3,1)",
            }}
          />
          <span
            style={{
              display: "block",
              height: "100%",
              width: `${pct(state.s)}%`,
              background: "var(--color-accent)",
              transition: "width .5s cubic-bezier(.16,1,.3,1)",
            }}
          />
          <span
            style={{
              display: "block",
              height: "100%",
              width: `${pct(state.r)}%`,
              background: "var(--color-warn)",
              transition: "width .5s cubic-bezier(.16,1,.3,1)",
            }}
          />
          <span
            style={{
              display: "block",
              height: "100%",
              width: `${pct(state.f)}%`,
              background: "rgba(228,73,31,.42)",
              transition: "width .5s cubic-bezier(.16,1,.3,1)",
            }}
          />
        </div>
      </div>

      <div className="mb-[18px] grid grid-cols-2 gap-[clamp(12px,1.1vw,18px)] lg:grid-cols-4">
        <div className="card flex flex-col justify-center gap-2" style={{ borderLeft: "3px solid var(--color-ok)" }}>
          <span className="num text-[clamp(1.55rem,2.1vw,2.15rem)] font-bold leading-[1.04] tracking-[-.035em]">
            {state.d.toLocaleString()}
          </span>
          <span className="text-muted uppercase" style={{ fontFamily: "var(--font-mono)", fontSize: ".6rem", fontWeight: 500, letterSpacing: ".12em" }}>
            Delivered
          </span>
        </div>
        <div className="card flex flex-col justify-center gap-2" style={{ borderLeft: "3px solid var(--color-accent)" }}>
          <span className="num text-[clamp(1.55rem,2.1vw,2.15rem)] font-bold leading-[1.04] tracking-[-.035em]">
            {state.s}
          </span>
          <span className="text-muted uppercase" style={{ fontFamily: "var(--font-mono)", fontSize: ".6rem", fontWeight: 500, letterSpacing: ".12em" }}>
            Sending
          </span>
        </div>
        <div className="card flex flex-col justify-center gap-2" style={{ borderLeft: "3px solid var(--color-warn)" }}>
          <span className="num text-[clamp(1.55rem,2.1vw,2.15rem)] font-bold leading-[1.04] tracking-[-.035em]">
            {state.r}
          </span>
          <span className="text-muted uppercase" style={{ fontFamily: "var(--font-mono)", fontSize: ".6rem", fontWeight: 500, letterSpacing: ".12em" }}>
            Retrying
          </span>
        </div>
        <div className="card flex flex-col justify-center gap-2" style={{ borderLeft: "3px solid var(--line-2)" }}>
          <span className="num text-[clamp(1.55rem,2.1vw,2.15rem)] font-bold leading-[1.04] tracking-[-.035em]">
            {state.f}
          </span>
          <span className="text-muted uppercase" style={{ fontFamily: "var(--font-mono)", fontSize: ".6rem", fontWeight: 500, letterSpacing: ".12em" }}>
            Failed
          </span>
        </div>
      </div>

      <div className="grid items-start gap-[18px] lg:grid-cols-2">
        <div className="card">
          <SectionLabel>Activity</SectionLabel>
          <div style={{ maxHeight: 320, overflowY: "auto" }}>
            {feedRows.map((row) => (
              <div
                key={row.key}
                className="grid items-center gap-[10px]"
                style={{
                  gridTemplateColumns: "62px 16px 1fr auto",
                  fontFamily: "var(--font-mono)",
                  fontSize: ".7rem",
                  padding: "6px 0",
                  borderBottom: "1px solid var(--line)",
                  color: "var(--muted)",
                }}
              >
                <span>{row.time}</span>
                <span
                  style={{
                    color:
                      row.cls === "g"
                        ? "var(--color-ok)"
                        : row.cls === "w"
                          ? "var(--color-warn)"
                          : row.cls === "c"
                            ? "var(--color-crit)"
                            : undefined,
                  }}
                >
                  {row.icon}
                </span>
                <b style={{ color: "var(--color-paper)", fontWeight: 400 }}>{row.who}</b>
                <span>{row.what}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="flex flex-col gap-3">
          <div className="card">
            <SectionLabel>Integrity</SectionLabel>
            <table style={{ minWidth: 0, width: "100%", borderCollapse: "collapse" }}>
              <tbody>
                <tr style={{ borderBottom: "1px solid var(--line)" }}>
                  <td style={{ padding: "9px 0", color: "var(--muted)" }}>Provider calls</td>
                  <td className="num" style={{ padding: "9px 0", textAlign: "right", fontFamily: "var(--font-mono)" }}>
                    {state.calls}
                  </td>
                </tr>
                <tr style={{ borderBottom: "1px solid var(--line)" }}>
                  <td style={{ padding: "9px 0", color: "var(--muted)" }}>Unique message IDs</td>
                  <td className="num" style={{ padding: "9px 0", textAlign: "right", fontFamily: "var(--font-mono)" }}>
                    {state.ids}
                  </td>
                </tr>
                <tr style={{ borderBottom: "1px solid var(--line)" }}>
                  <td style={{ padding: "9px 0", color: "var(--muted)" }}>Duplicate sends</td>
                  <td
                    className="num"
                    style={{ padding: "9px 0", textAlign: "right", fontFamily: "var(--font-mono)", color: "var(--color-ok)" }}
                  >
                    {state.dupes}
                  </td>
                </tr>
                <tr style={{ borderBottom: "1px solid var(--line)" }}>
                  <td style={{ padding: "9px 0", color: "var(--muted)" }}>Idempotency hits</td>
                  <td className="num" style={{ padding: "9px 0", textAlign: "right", fontFamily: "var(--font-mono)" }}>
                    {state.hits}
                  </td>
                </tr>
                <tr>
                  <td style={{ padding: "9px 0", color: "var(--muted)" }}>Orphan webhooks</td>
                  <td className="num" style={{ padding: "9px 0", textAlign: "right", fontFamily: "var(--font-mono)" }}>
                    {state.orph}
                  </td>
                </tr>
              </tbody>
            </table>
            <p style={{ fontFamily: "var(--font-mono)", fontSize: ".62rem", color: "var(--faint)", marginTop: 10 }}>
              Duplicate sends must stay at zero through any number of crashes. That is the invariant
              the whole system exists to hold.
            </p>
          </div>

          <div className="card">
            <SectionLabel>Workers</SectionLabel>
            <div className="flex flex-col gap-2">
              {state.workers.map((w) => (
                <div key={w.id} className="flex items-center justify-between" style={{ fontFamily: "var(--font-mono)", fontSize: ".7rem" }}>
                  <span style={{ color: w.up ? "var(--color-paper)" : "var(--faint)" }}>
                    <span style={{ color: w.up ? "var(--color-ok)" : "var(--color-crit)" }}>
                      {w.up ? "●" : "✕"}
                    </span>{" "}
                    {w.id}
                  </span>
                  <span style={{ color: "var(--muted)" }}>{w.up ? `${w.n} jobs` : "down"}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="h-6" />
      {state.over && (
        <Link href={`/app/campaigns/${campaignId}/report`} className="btn btn-ghost no-underline">
          View completion report →
        </Link>
      )}
    </Shell>
  );
}
