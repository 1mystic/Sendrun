"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

type Role = "owner" | "admin" | "editor" | "viewer";

type InviteRow = {
  id: number;
  email: string;
  role: Role;
};

let nextId = 3;

const INITIAL_ROWS: InviteRow[] = [
  { id: 0, email: "", role: "admin" },
  { id: 1, email: "", role: "editor" },
  { id: 2, email: "", role: "viewer" },
];

const RemoveIcon = () => (
  <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth={2}>
    <path d="M18 6 6 18M6 6l12 12" />
  </svg>
);

export default function InviteTeamPage() {
  const router = useRouter();
  const [rows, setRows] = useState<InviteRow[]>(INITIAL_ROWS);

  function addRow() {
    setRows((prev) => [...prev, { id: nextId++, email: "", role: "editor" }]);
  }

  function removeRow(id: number) {
    setRows((prev) => (prev.length <= 1 ? prev : prev.filter((r) => r.id !== id)));
  }

  function updateRow(id: number, patch: Partial<InviteRow>) {
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  }

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    router.push("/app");
  }

  function handleSkip() {
    router.push("/app");
  }

  return (
    <section>
      <div className="a-brand-lockup">
        <span className="a-mark" /> Sendrun
      </div>
      <h1>Invite your team</h1>
      <p className="lede">
        Sendrun works best with your whole team in one workspace. You can
        always invite more people later.
      </p>

      <form onSubmit={handleSubmit}>
        <div>
          {rows.map((row) => (
            <div className="a-invite-row" key={row.id}>
              <div>
                <label className="field-label" htmlFor={`inv-email-${row.id}`}>
                  Email
                </label>
                <input
                  className="input"
                  type="email"
                  id={`inv-email-${row.id}`}
                  name={`inv-email-${row.id}`}
                  placeholder="teammate@company.com"
                  value={row.email}
                  onChange={(e) => updateRow(row.id, { email: e.target.value })}
                />
              </div>
              <div>
                <label className="field-label" htmlFor={`inv-role-${row.id}`}>
                  Role
                </label>
                <select
                  className="input"
                  id={`inv-role-${row.id}`}
                  name={`inv-role-${row.id}`}
                  value={row.role}
                  onChange={(e) => updateRow(row.id, { role: e.target.value as Role })}
                >
                  <option value="owner">Owner</option>
                  <option value="admin">Admin</option>
                  <option value="editor">Editor</option>
                  <option value="viewer">Viewer</option>
                </select>
              </div>
              <button
                type="button"
                className="rm"
                aria-label="Remove this row"
                onClick={() => removeRow(row.id)}
                disabled={rows.length <= 1}
              >
                <RemoveIcon />
              </button>
            </div>
          ))}
        </div>

        <button type="button" className="btn btn-ghost btn-sm" onClick={addRow}>
          + Add another
        </button>

        <div style={{ height: 22 }} />
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <button className="btn" type="submit">
            Send invites
          </button>
          <button className="btn btn-ghost" type="button" onClick={handleSkip}>
            Skip for now
          </button>
        </div>
      </form>
    </section>
  );
}
