"use client";

import Link from "next/link";
import { notFound, useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { PageTitle, Pill } from "@/components/ui";
import { deleteGroup, getCurrentOrgId, getGroup, useMocks, type GroupDetailOut } from "@/lib/api";

export default function ListDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const router = useRouter();

  const [group, setGroup] = useState<GroupDetailOut | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  const orgId = getCurrentOrgId();

  async function reload() {
    if (!orgId) {
      setGroup(null);
      return;
    }
    try {
      setGroup(await getGroup(orgId, id));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load list");
      setGroup(null);
    }
  }

  useEffect(() => {
    async function load() {
      await reload();
    }
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function handleDelete() {
    if (!orgId) return;
    setDeleting(true);
    try {
      await deleteGroup(orgId, id);
      router.push("/app/lists");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete list");
      setDeleting(false);
    }
  }

  if (group === undefined) {
    return (
      <Shell crumb="List" actions={<Link href="/app/lists" className="btn btn-ghost btn-sm no-underline">← All lists</Link>}>
        <p className="text-faint">Loading…</p>
      </Shell>
    );
  }

  if (group === null) {
    if (!useMocks && !error) notFound();
    return (
      <Shell crumb="List" actions={<Link href="/app/lists" className="btn btn-ghost btn-sm no-underline">← All lists</Link>}>
        <p style={{ color: "var(--color-crit)" }}>{error ?? "List not found."}</p>
      </Shell>
    );
  }

  return (
    <Shell
      crumb={group.name}
      actions={
        <>
          <Link href={`/app/lists/import/${group.id}`} className="btn btn-sm no-underline">
            Import more
          </Link>
          <Link href="/app/lists" className="btn btn-ghost btn-sm no-underline">
            ← All lists
          </Link>
        </>
      }
    >
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <PageTitle
          title={group.name}
          lede={`${group.contact_count.toLocaleString()} contact${group.contact_count === 1 ? "" : "s"} in this list.`}
        />
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          style={{ color: "var(--color-crit)", borderColor: "rgba(228,73,31,.45)" }}
          disabled={deleting}
          onClick={handleDelete}
        >
          {deleting ? "Deleting…" : "Delete list"}
        </button>
      </div>

      {error && <p style={{ color: "var(--color-crit)", fontSize: ".82rem", marginBottom: 12 }}>{error}</p>}

      {group.contacts.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: "clamp(32px, 4vw, 48px)" }}>
          <p className="text-muted mb-4 text-[.86rem]">No contacts in this list yet.</p>
          <Link href={`/app/lists/import/${group.id}`} className="btn no-underline">
            Import contacts
          </Link>
        </div>
      ) : (
        <div className="overflow-x-auto" style={{ border: "1px solid var(--line)", borderRadius: 3 }}>
          <table className="w-full border-collapse text-[.82rem]" style={{ minWidth: 640 }}>
            <thead>
              <tr>
                {["Name", "Email", "Tags", "Status"].map((h) => (
                  <th
                    key={h}
                    className="text-faint px-3.5 py-2.5 text-left font-normal uppercase"
                    style={{
                      fontFamily: "var(--font-mono)", fontSize: ".58rem", letterSpacing: ".12em",
                      borderBottom: "1px solid var(--line)", background: "var(--color-ink-2)",
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {group.contacts.map((c) => (
                <tr key={c.id} style={{ borderBottom: "1px solid var(--line)" }}>
                  <td className="px-3.5 py-3 font-semibold">{c.name || "(no name)"}</td>
                  <td className="px-3.5 py-3" style={{ fontFamily: "var(--font-mono)", fontSize: ".74rem", color: "var(--muted)" }}>
                    {c.email}
                  </td>
                  <td className="px-3.5 py-3">
                    <div className="flex flex-wrap gap-1.5">
                      {c.tags.map((t) => <Pill key={t}>{t}</Pill>)}
                    </div>
                  </td>
                  <td className="px-3.5 py-3">
                    {c.suppressed ? <Pill tone="crit">Suppressed</Pill> : <Pill tone="ok">Active</Pill>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Shell>
  );
}
