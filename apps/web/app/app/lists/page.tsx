"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { PageTitle } from "@/components/ui";
import { getCurrentOrgId, listGroups, useMocks, type GroupOut } from "@/lib/api";

export default function ListsPage() {
  const [groups, setGroups] = useState<GroupOut[]>([]);
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
        setGroups(await listGroups(orgId));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load mailing lists");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  return (
    <Shell
      crumb="Mailing lists"
      actions={
        <Link href="/app/lists/new" className="btn no-underline">
          New list
        </Link>
      }
    >
      <PageTitle
        title="Mailing lists"
        lede="Named contact groups you build by pasting data or uploading a file, then send to as a unit."
      />

      {error && <p style={{ color: "var(--color-crit)", fontSize: ".82rem", marginBottom: 12 }}>{error}</p>}

      {loading && !useMocks && <p className="text-faint">Loading mailing lists…</p>}

      {!loading && groups.length === 0 && !error && (
        <div className="card" style={{ textAlign: "center", padding: "clamp(32px, 4vw, 48px)" }}>
          <p className="text-muted mb-4 text-[.86rem]">No mailing lists yet.</p>
          <Link href="/app/lists/new" className="btn no-underline">
            Create your first list
          </Link>
        </div>
      )}

      {groups.length > 0 && (
        <div className="grid gap-[clamp(12px,1.1vw,18px)]" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))" }}>
          {groups.map((g) => (
            <Link
              key={g.id}
              href={`/app/lists/${g.id}`}
              className="card card-interactive no-underline"
              style={{ display: "block", color: "var(--color-paper)" }}
            >
              <div className="sec" style={{ margin: "0 0 10px" }}>List</div>
              <h3 style={{ margin: "0 0 8px", fontSize: "1.05rem", fontWeight: 600, letterSpacing: "-.02em" }}>
                {g.name}
              </h3>
              <div className="num" style={{ fontFamily: "var(--font-mono)", fontSize: ".78rem", color: "var(--muted)" }}>
                {g.contact_count.toLocaleString()} contact{g.contact_count === 1 ? "" : "s"}
              </div>
            </Link>
          ))}
        </div>
      )}
    </Shell>
  );
}
