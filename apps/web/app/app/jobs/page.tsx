"use client";

import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { PageTitle, Pill } from "@/components/ui";
import { DEAD_LETTER_QUEUE } from "@/lib/mock-ops";
import { getCurrentOrgId, listDeadLetterTasks, listInFlightTasks, useMocks, type TaskOut } from "@/lib/api";

function MockJobsPage() {
  return (
    <Shell crumb="Job inspector">
      <PageTitle title="Job inspector" lede="Demo data. Connect a live organization to inspect real tasks." />
      <div className="card">
        <div className="sec">Dead letter queue · {DEAD_LETTER_QUEUE.length}</div>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-[.82rem]" style={{ minWidth: 560 }}>
            <thead>
              <tr>
                {["Job", "Recipient", "Attempts", "Last error"].map((h) => (
                  <th key={h} className="text-faint px-3.5 py-2.5 text-left font-normal uppercase" style={{ fontFamily: "var(--font-mono)", fontSize: ".58rem", letterSpacing: ".12em", borderBottom: "1px solid var(--line)" }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {DEAD_LETTER_QUEUE.map((job) => (
                <tr key={job.id} style={{ borderBottom: "1px solid var(--line)" }}>
                  <td className="px-3.5 py-3" style={{ fontFamily: "var(--font-mono)", fontSize: ".74rem" }}>{job.id}</td>
                  <td className="px-3.5 py-3" style={{ fontFamily: "var(--font-mono)", fontSize: ".74rem", color: "var(--muted)" }}>{job.recipient}</td>
                  <td className="num px-3.5 py-3">{job.attempts}</td>
                  <td className="px-3.5 py-3 text-muted text-[.78rem]">{job.lastError}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Shell>
  );
}

function statusTone(status: string): "ok" | "warn" | "crit" | "default" {
  if (status === "dead" || status === "failed") return "crit";
  if (status === "leased") return "warn";
  return "default";
}

function TaskTable({ title, tasks }: { title: string; tasks: TaskOut[] }) {
  return (
    <div className="card mb-4">
      <div className="sec">{title} · {tasks.length}</div>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-[.82rem]" style={{ minWidth: 640 }}>
          <thead>
            <tr>
              {["Task", "Type", "Status", "Attempt", "Campaign", "Last error"].map((h) => (
                <th key={h} className="text-faint px-3.5 py-2.5 text-left font-normal uppercase" style={{ fontFamily: "var(--font-mono)", fontSize: ".58rem", letterSpacing: ".12em", borderBottom: "1px solid var(--line)" }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {tasks.map((t) => (
              <tr key={t.id} style={{ borderBottom: "1px solid var(--line)" }}>
                <td className="px-3.5 py-3" style={{ fontFamily: "var(--font-mono)", fontSize: ".72rem" }}>{t.id.slice(0, 8)}</td>
                <td className="px-3.5 py-3">{t.task_type}</td>
                <td className="px-3.5 py-3"><Pill tone={statusTone(t.status)}>{t.status}</Pill></td>
                <td className="num px-3.5 py-3">{t.attempt}/{t.max_attempts}</td>
                <td className="px-3.5 py-3" style={{ fontFamily: "var(--font-mono)", fontSize: ".7rem", color: "var(--muted)" }}>
                  {t.campaign_id ? t.campaign_id.slice(0, 8) : "—"}
                </td>
                <td className="px-3.5 py-3 text-muted text-[.78rem]">{t.last_error ?? "—"}</td>
              </tr>
            ))}
            {tasks.length === 0 && (
              <tr><td colSpan={6} className="px-3.5 py-8 text-center text-faint">Nothing here.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function LiveJobsPage() {
  const [deadLetter, setDeadLetter] = useState<TaskOut[]>([]);
  const [inFlight, setInFlight] = useState<TaskOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      const orgId = getCurrentOrgId();
      if (!orgId) {
        setError("No organization selected — sign in again.");
        setLoading(false);
        return;
      }
      try {
        const [dead, flight] = await Promise.all([listDeadLetterTasks(orgId), listInFlightTasks(orgId)]);
        setDeadLetter(dead);
        setInFlight(flight);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load tasks");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  return (
    <Shell crumb="Job inspector">
      <PageTitle
        title="Job inspector"
        lede="Read-only view over the durable engine's task queue — dead-lettered and in-flight sends, scoped to this organization."
      />
      {error && <p style={{ color: "var(--color-crit)", fontSize: ".82rem" }}>{error}</p>}
      {loading && <p className="text-faint">Loading…</p>}
      {!loading && !error && (
        <>
          <TaskTable title="Dead letter queue" tasks={deadLetter} />
          <TaskTable title="In-flight / retrying" tasks={inFlight} />
          <p className="text-faint mt-2.5" style={{ fontFamily: "var(--font-mono)", fontSize: ".62rem" }}>
            This is a read-only inspector. Requeueing a dead task is not exposed here — the
            durable engine&rsquo;s own retry/backoff machinery already owns that decision.
            The durable engine&rsquo;s task table is Postgres-only — against a local SQLite
            database (the default for `uv run uvicorn` without DATABASE_URL set) both lists
            above are always empty by design, not a sign nothing is running.
          </p>
        </>
      )}
    </Shell>
  );
}

export default function JobsPage() {
  return useMocks ? <MockJobsPage /> : <LiveJobsPage />;
}
