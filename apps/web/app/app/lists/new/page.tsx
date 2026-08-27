"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Shell from "@/components/Shell";
import { ArrowRight, PageTitle, SectionLabel } from "@/components/ui";
import { createGroup, getCurrentOrgId } from "@/lib/api";

export default function NewListPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  async function handleCreate() {
    const orgId = getCurrentOrgId();
    if (!orgId || !name.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const group = await createGroup(orgId, name.trim());
      router.push(`/app/lists/import/${group.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create list");
      setCreating(false);
    }
  }

  return (
    <Shell crumb="New list">
      <PageTitle title="New mailing list" lede="Name it, then import contacts straight away." />

      <div className="card" style={{ maxWidth: 480 }}>
        <SectionLabel>List name</SectionLabel>
        <label className="mb-4 block">
          <span className="field-label">Name</span>
          <input
            className="input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Hackathon speakers"
            autoFocus
          />
        </label>
        {error && <p style={{ color: "var(--color-crit)", fontSize: ".8rem", marginBottom: 12 }}>{error}</p>}
        <button type="button" className="btn" disabled={creating || !name.trim()} onClick={handleCreate}>
          {creating ? "Creating…" : <>Create &amp; import contacts<ArrowRight /></>}
        </button>
      </div>
    </Shell>
  );
}
