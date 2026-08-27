"use client";

import Link from "next/link";
import { useState } from "react";
import Shell from "@/components/Shell";
import { ArrowRight, PageTitle } from "@/components/ui";
import {
  DEFAULT_SEED,
  EVENT_SLIDERS,
  FAILURE_SLIDERS,
  type ChaosSlider,
} from "@/lib/mock-ops";

function defaultsFor(sliders: ChaosSlider[]): Record<string, number> {
  return Object.fromEntries(sliders.map((s) => [s.id, s.defaultValue]));
}

function formatValue(slider: ChaosSlider, value: number): string {
  if (slider.format === "sec") return `${(value / 10).toFixed(1)}s`;
  return `${value}%`;
}

function SliderGroup({
  title,
  sliders,
  values,
  onChange,
}: {
  title: string;
  sliders: ChaosSlider[];
  values: Record<string, number>;
  onChange: (id: string, value: number) => void;
}) {
  return (
    <div className="card">
      <div className="sec">{title}</div>
      <div className="flex flex-col">
        {sliders.map((s) => (
          <div
            key={s.id}
            className="grid items-center gap-3 py-2.5"
            style={{ gridTemplateColumns: "1fr 56px", borderBottom: "1px solid var(--line)" }}
          >
            <label htmlFor={`slider-${s.id}`} className="text-[.8rem]">
              {s.label}
              <span
                className="block mt-0.5"
                style={{ fontFamily: "var(--font-mono)", fontSize: ".62rem", color: "var(--faint)" }}
              >
                {s.description}
              </span>
            </label>
            <output
              htmlFor={`slider-${s.id}`}
              className="num text-right"
              style={{ fontFamily: "var(--font-mono)", fontSize: ".72rem", color: "var(--color-accent)" }}
            >
              {formatValue(s, values[s.id])}
            </output>
            <input
              id={`slider-${s.id}`}
              type="range"
              min={s.min}
              max={s.max}
              value={values[s.id]}
              onChange={(e) => onChange(s.id, Number(e.target.value))}
              style={{ gridColumn: "1 / -1", width: "100%", accentColor: "var(--color-accent)" }}
              aria-valuetext={formatValue(s, values[s.id])}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

export default function ChaosPage() {
  const [failure, setFailure] = useState<Record<string, number>>(() => defaultsFor(FAILURE_SLIDERS));
  const [events, setEvents] = useState<Record<string, number>>(() => defaultsFor(EVENT_SLIDERS));
  const [seed, setSeed] = useState<string>(String(DEFAULT_SEED));

  const resetAll = () => {
    setFailure(defaultsFor(FAILURE_SLIDERS));
    setEvents(defaultsFor(EVENT_SLIDERS));
    setSeed(String(DEFAULT_SEED));
  };

  return (
    <Shell crumb="Chaos mode">
      <PageTitle
        title="Chaos mode"
        lede="Development only. Inject failures deliberately and watch the system converge anyway."
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2" style={{ alignItems: "start" }}>
        <SliderGroup
          title="Failure injection"
          sliders={FAILURE_SLIDERS}
          values={failure}
          onChange={(id, v) => setFailure((f) => ({ ...f, [id]: v }))}
        />
        <SliderGroup
          title="Event chaos"
          sliders={EVENT_SLIDERS}
          values={events}
          onChange={(id, v) => setEvents((f) => ({ ...f, [id]: v }))}
        />
      </div>

      <div className="h-6" />
      <div className="card">
        <div className="sec">Determinism</div>
        <div className="flex flex-wrap items-center justify-between gap-4">
          <p className="text-muted m-0 max-w-[66ch] text-[.82rem] leading-[1.55]">
            Outcomes are seeded per idempotency key, so the same seed reproduces the same run
            exactly — same bounces, same crashes, same races. Demos and regression tests are
            repeatable.
          </p>
          <div className="flex items-center gap-2.5">
            <label
              htmlFor="chaos-seed"
              style={{ fontFamily: "var(--font-mono)", fontSize: ".72rem", color: "var(--muted)" }}
            >
              seed
            </label>
            <input
              id="chaos-seed"
              className="input"
              style={{ width: 80, fontFamily: "var(--font-mono)", fontSize: ".78rem", padding: "6px 9px" }}
              value={seed}
              onChange={(e) => setSeed(e.target.value)}
              inputMode="numeric"
            />
          </div>
        </div>
      </div>

      <div className="h-6" />
      <div className="flex flex-wrap gap-2.5">
        <Link href="/app/campaigns/campaign_8231" className="btn no-underline">
          Run seeded campaign
          <ArrowRight />
        </Link>
        <button type="button" className="btn btn-ghost" onClick={resetAll}>
          Reset to defaults
        </button>
      </div>
    </Shell>
  );
}
