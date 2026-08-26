"use client";

import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { PageTitle, Pill } from "@/components/ui";
import { TEMPLATES } from "@/lib/mock-ops";
import {
  archiveTemplate,
  createTemplate,
  getCurrentOrgId,
  listTemplates,
  updateTemplate,
  useMocks,
  type TemplateOut,
} from "@/lib/api";

interface EditorState {
  id: string | null; // null = creating new
  name: string;
  subject: string;
  html_body: string;
  variables: string;
}

function blankEditor(): EditorState {
  return { id: null, name: "", subject: "", html_body: "", variables: "" };
}

function toEditor(t: TemplateOut): EditorState {
  return {
    id: t.id,
    name: t.name,
    subject: t.latest.subject,
    html_body: t.latest.html_body,
    variables: t.latest.variables.join(", "),
  };
}

export default function TemplatesPage() {
  const [templates, setTemplates] = useState<TemplateOut[]>([]);
  const [loading, setLoading] = useState(!useMocks);
  const [error, setError] = useState<string | null>(null);
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [saving, setSaving] = useState(false);

  async function reload() {
    const orgId = getCurrentOrgId();
    if (!orgId) return;
    setLoading(true);
    try {
      setTemplates(await listTemplates(orgId));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load templates");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    async function load() {
      if (useMocks) return;
      await reload();
    }
    load();
  }, []);

  async function handleSave() {
    if (!editor) return;
    const orgId = getCurrentOrgId();
    if (!orgId) {
      setError("No organization selected — sign in again.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const variables = editor.variables
        .split(",")
        .map((v) => v.trim())
        .filter(Boolean);
      const body = { name: editor.name, subject: editor.subject, html_body: editor.html_body, variables };
      if (editor.id) {
        await updateTemplate(orgId, editor.id, body);
      } else {
        await createTemplate(orgId, body);
      }
      setEditor(null);
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save template");
    } finally {
      setSaving(false);
    }
  }

  async function handleArchive(templateId: string) {
    const orgId = getCurrentOrgId();
    if (!orgId) return;
    try {
      await archiveTemplate(orgId, templateId);
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not archive template");
    }
  }

  if (useMocks) {
    return (
      <Shell
        crumb="Templates"
        actions={
          <button type="button" className="btn" disabled>
            New template
          </button>
        }
      >
        <PageTitle
          title="Templates"
          lede="Reusable message templates. Every send records the version used."
        />
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {TEMPLATES.map((t) => (
            <div key={t.id} className="card flex flex-col gap-3">
              <div className="flex items-start justify-between gap-3">
                <div className="text-[1rem] font-semibold tracking-[-.02em]">{t.name}</div>
                <Pill>v{t.version}</Pill>
              </div>
              <div
                className="text-muted"
                style={{ fontFamily: "var(--font-mono)", fontSize: ".72rem", lineHeight: 1.5 }}
              >
                {t.subjectPreview}
              </div>
              <div className="flex flex-wrap gap-1.5">
                {t.variables.map((v) => (
                  <span
                    key={v}
                    style={{
                      fontFamily: "var(--font-mono)", fontSize: ".68rem", background: "var(--accent-dim)",
                      color: "var(--color-accent)", padding: "1px 6px", borderRadius: 2,
                    }}
                  >
                    {`{{${v}}}`}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
        <p className="text-faint mt-6" style={{ fontFamily: "var(--font-mono)", fontSize: ".62rem" }}>
          Demo data. Connect a live organization to manage real templates.
        </p>
      </Shell>
    );
  }

  return (
    <Shell
      crumb="Templates"
      actions={
        <button type="button" className="btn" onClick={() => setEditor(blankEditor())}>
          New template
        </button>
      }
    >
      <PageTitle
        title="Templates"
        lede="Reusable message templates. Every send records the version used."
      />

      {error && (
        <p style={{ color: "var(--color-crit)", fontSize: ".82rem", marginBottom: 12 }}>{error}</p>
      )}

      {editor && (
        <div className="card mb-6" style={{ maxWidth: 640 }}>
          <div className="sec">{editor.id ? "Edit template" : "New template"}</div>
          <label className="mb-4 block">
            <span className="field-label">Name</span>
            <input
              className="input"
              value={editor.name}
              onChange={(e) => setEditor({ ...editor, name: e.target.value })}
            />
          </label>
          <label className="mb-4 block">
            <span className="field-label">Subject</span>
            <input
              className="input"
              value={editor.subject}
              onChange={(e) => setEditor({ ...editor, subject: e.target.value })}
            />
          </label>
          <label className="mb-4 block">
            <span className="field-label">Body (HTML)</span>
            <textarea
              className="input"
              rows={8}
              value={editor.html_body}
              onChange={(e) => setEditor({ ...editor, html_body: e.target.value })}
              style={{ fontFamily: "var(--font-mono)", fontSize: ".78rem", lineHeight: 1.7, resize: "vertical" }}
            />
          </label>
          <label className="mb-4 block">
            <span className="field-label">Variables (comma-separated)</span>
            <input
              className="input"
              placeholder="first_name, event_name"
              value={editor.variables}
              onChange={(e) => setEditor({ ...editor, variables: e.target.value })}
              style={{ fontFamily: "var(--font-mono)", fontSize: ".78rem" }}
            />
          </label>
          <div className="flex gap-2">
            <button type="button" className="btn" disabled={saving} onClick={handleSave}>
              {saving ? "Saving…" : editor.id ? "Save new version" : "Create template"}
            </button>
            <button type="button" className="btn btn-ghost" onClick={() => setEditor(null)}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {loading && <p className="text-faint">Loading templates…</p>}

      {!loading && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {templates.map((t) => (
            <div key={t.id} className="card flex flex-col gap-3">
              <div className="flex items-start justify-between gap-3">
                <div className="text-[1rem] font-semibold tracking-[-.02em]">{t.name}</div>
                <Pill>v{t.current_version}</Pill>
              </div>
              <div
                className="text-muted"
                style={{ fontFamily: "var(--font-mono)", fontSize: ".72rem", lineHeight: 1.5 }}
              >
                {t.latest.subject}
              </div>
              <div className="flex flex-wrap gap-1.5">
                {t.latest.variables.map((v) => (
                  <span
                    key={v}
                    style={{
                      fontFamily: "var(--font-mono)", fontSize: ".68rem", background: "var(--accent-dim)",
                      color: "var(--color-accent)", padding: "1px 6px", borderRadius: 2,
                    }}
                  >
                    {`{{${v}}}`}
                  </span>
                ))}
              </div>
              <div
                className="mt-1 flex items-center justify-between border-t pt-3"
                style={{ borderColor: "var(--line)" }}
              >
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => setEditor(toEditor(t))}
                >
                  Edit
                </button>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => handleArchive(t.id)}
                >
                  Archive
                </button>
              </div>
            </div>
          ))}
          {templates.length === 0 && (
            <p className="text-faint">No templates yet. Create one to get started.</p>
          )}
        </div>
      )}

      <p className="text-faint mt-6" style={{ fontFamily: "var(--font-mono)", fontSize: ".62rem" }}>
        Templates are versioned. Each send records the exact version that was used, so past
        campaigns always reflect what recipients actually saw. Archiving hides a template from
        this list without deleting the versions past campaigns already sent.
      </p>
    </Shell>
  );
}
