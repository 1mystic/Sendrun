"use client";

import { useEffect, useRef, useState } from "react";
import { Pill } from "@/components/ui";

type FeedRow = {
  time: string;
  icon: string;
  iconClass: "g" | "w" | "c";
  text: string;
};

const INITIAL_FEED: FeedRow[] = [
  { time: "14:03:19", icon: "✓", iconClass: "g", text: "Lease acquired · worker_a" },
  { time: "14:03:21", icon: "⚠", iconClass: "w", text: "worker_a died mid-send" },
  { time: "14:03:49", icon: "↻", iconClass: "c", text: "Reaper expired lease" },
  { time: "14:03:50", icon: "✓", iconClass: "g", text: "Re-picked by worker_c" },
];

const SETTLE_ROW: FeedRow = {
  time: "14:03:52",
  icon: "✓",
  iconClass: "g",
  text: "Idempotency hit — 0 duplicates",
};

const SEGMENTS = [
  { key: "d", w: 66 },
  { key: "s", w: 9 },
  { key: "r", w: 3 },
  { key: "f", w: 1 },
] as const;

/** Hero live campaign panel: fills the bar and appends a settling event on load. */
export default function LivePanel() {
  const [filled, setFilled] = useState(false);
  const [feed, setFeed] = useState(INITIAL_FEED);
  const [settled, setSettled] = useState(false);
  const reduceMotionRef = useRef(false);

  useEffect(() => {
    reduceMotionRef.current =
      typeof window !== "undefined" &&
      window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (reduceMotionRef.current) {
      setFilled(true);
      setSettled(true);
      return;
    }

    const fillTimer = setTimeout(() => setFilled(true), 300);
    const feedTimer = setTimeout(() => setSettled(true), 1400);
    return () => {
      clearTimeout(fillTimer);
      clearTimeout(feedTimer);
    };
  }, []);

  const rows = settled ? [...feed, SETTLE_ROW] : feed;
  void setFeed;

  return (
    <div className="card relative">
      <div className="m-lp-top">
        <div>
          <div className="m-lp-title">Hackathon Speaker Outreach</div>
          <div className="m-lp-sub">campaign_8231 &middot; 122 jobs</div>
        </div>
        <Pill tone="run" pulse>
          Running
        </Pill>
      </div>
      <div className="m-bar">
        {SEGMENTS.map((seg) => (
          <i
            key={seg.key}
            className={seg.key}
            style={{ width: filled ? `${seg.w}%` : "0%" }}
          />
        ))}
      </div>
      <div className="m-lp-stats">
        <div className="m-lp-stat d">
          <u className="num">81</u>
          <span>Delivered</span>
        </div>
        <div className="m-lp-stat s">
          <u className="num">11</u>
          <span>Sending</span>
        </div>
        <div className="m-lp-stat r">
          <u className="num">4</u>
          <span>Retrying</span>
        </div>
        <div className="m-lp-stat">
          <u className="num">0</u>
          <span>Duplicated</span>
        </div>
      </div>
      <div className="m-lp-feed-wrap">
        <div className="m-feed">
          {rows.map((row, i) => (
            <div
              key={`${row.time}-${i}`}
              className="m-frow"
              style={
                row === SETTLE_ROW
                  ? { animation: "m-fadein .5s cubic-bezier(.16,1,.3,1)" }
                  : undefined
              }
            >
              <span>{row.time}</span>
              <span className={row.iconClass}>{row.icon}</span>
              <b>{row.text}</b>
              <span />
            </div>
          ))}
        </div>
      </div>
      <style>{`@keyframes m-fadein { from { opacity: 0; } to { opacity: 1; } }`}</style>
    </div>
  );
}
