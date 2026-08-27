"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { ArrowRight, SectionLabel } from "@/components/ui";
import { CONTACTS, DEFAULT_TEMPLATE, RECIPIENT_GROUPS, renderTemplate } from "@/lib/mock";
import {
  createTemplate,
  getCurrentOrgId,
  listContactsLive,
  listGroups,
  listTemplates,
  setCampaignDraft,
  updateTemplate,
  useMocks,
  type ContactOut,
  type GroupOut,
  type TemplateOut,
} from "@/lib/api";
import Stepper from "../Stepper";

export default function ComposePage() {
  return (
    <Suspense fallback={<Shell crumb="New campaign"><p className="text-faint">Loading…</p></Shell>}>
      <ComposePageInner />
    </Suspense>
  );
}

function ComposePageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null);
  const [groups, setGroups] = useState<GroupOut[]>([]);
  const [loadingGroups, setLoadingGroups] = useState(!useMocks);
  const [templates, setTemplates] = useState<TemplateOut[]>([]);
  const [sourceTemplateId, setSourceTemplateId] = useState<string | null>(null);
  const [templateName, setTemplateName] = useState("Untitled campaign");
  const [subject, setSubject] = useState(DEFAULT_TEMPLATE.subject);
  const [body, setBody] = useState(DEFAULT_TEMPLATE.body);
  const [whoId, setWhoId] = useState(CONTACTS[0].id);
  const [liveContacts, setLiveContacts] = useState<ContactOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (useMocks) return;

    async function load() {
      const orgId = getCurrentOrgId();
      if (!orgId) {
        setLoadingGroups(false);
        return;
      }
      try {
        const [gs, ts] = await Promise.all([listGroups(orgId), listTemplates(orgId)]);
        setGroups(gs);
        if (gs.length === 1) setSelectedGroupId(gs[0].id);
        setTemplates(ts);

        const preselect = searchParams.get("template");
        const source = preselect ? ts.find((t) => t.id === preselect) : undefined;
        if (source) applyTemplate(source);
      } finally {
        setLoadingGroups(false);
      }
    }
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (useMocks || !selectedGroupId) return;
    const orgId = getCurrentOrgId();
    if (!orgId) return;
    listContactsLive(orgId).then((contacts) => {
      setLiveContacts(contacts);
      if (contacts[0]) setWhoId(contacts[0].id);
    });
  }, [selectedGroupId]);

  function applyTemplate(t: TemplateOut) {
    setSourceTemplateId(t.id);
    setTemplateName(t.name);
    setSubject(t.latest.subject);
    setBody(t.latest.html_body);
  }

  function handleTemplatePick(id: string) {
    if (!id) {
      setSourceTemplateId(null);
      setTemplateName("Untitled campaign");
      setSubject("");
      setBody("");
      return;
    }
    const t = templates.find((tpl) => tpl.id === id);
    if (t) applyTemplate(t);
  }

  const recipientCount = useMocks
    ? RECIPIENT_GROUPS.reduce((sum, g) => sum + g.count, 0)
    : (groups.find((g) => g.id === selectedGroupId)?.contact_count ?? 0);

  // Live mode personalizes against a real contact's `fields` — the same
  // {{var}} substitution the backend applies at render time (see
  // packages/shared/render.py) — rather than the mock's fixed first_name/
  // event_name/specialization set, since a real contact's fields are
  // whatever an import mapped, not a fixed schema.
  function substituteLive(text: string, contact: ContactOut): string {
    const withName = text.replace(/\{\{first_name\}\}/g, contact.name?.split(" ")[0] ?? "there");
    return withName.replace(/\{\{(\w+)\}\}/g, (match, key: string) =>
      contact.fields[key] !== undefined ? contact.fields[key] : "⟨missing⟩",
    );
  }

  const liveWho = liveContacts.find((c) => c.id === whoId) ?? liveContacts[0];
  const mockWho = CONTACTS.find((c) => c.id === whoId) ?? CONTACTS[0];
  const renderedSubject = useMocks ? renderTemplate(subject, mockWho) : liveWho ? substituteLive(subject, liveWho) : subject;
  const renderedBody = useMocks ? renderTemplate(body, mockWho) : liveWho ? substituteLive(body, liveWho) : body;

  async function handleRunPreflight() {
    if (useMocks) {
      router.push("/app/campaigns/new/preflight");
      return;
    }
    const orgId = getCurrentOrgId();
    if (!orgId) {
      setError("No organization selected — sign in again.");
      return;
    }
    if (!selectedGroupId) {
      setError("Pick a mailing list before running preflight.");
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      const variableMatches = [...subject.matchAll(/\{\{(\w+)\}\}/g), ...body.matchAll(/\{\{(\w+)\}\}/g)];
      const variables = [...new Set(variableMatches.map((m) => m[1]))];
      const body_ = { name: templateName, subject, html_body: body, variables };
      // Editing a picked template creates a new VERSION of it (never an
      // in-place overwrite — see services/api/routers/templates.py's module
      // docstring), so a past campaign that already launched with an earlier
      // version is unaffected. Starting from scratch still creates a new
      // template row.
      const template = sourceTemplateId
        ? await updateTemplate(orgId, sourceTemplateId, body_)
        : await createTemplate(orgId, body_);
      setCampaignDraft({
        name: templateName,
        templateId: template.id,
        recipients: { group_id: selectedGroupId, exclude_suppressed: true },
      });
      router.push("/app/campaigns/new/preflight");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save template");
    } finally {
      setSubmitting(false);
    }
  }

  function renderWithMissingMarker(text: string) {
    const parts = text.split("⟨missing⟩");
    return parts.flatMap((part, i) =>
      i === 0
        ? [part]
        : [
            <mark
              key={i}
              style={{
                background: "rgba(228,73,31,.2)",
                color: "var(--color-accent)",
                padding: "0 3px",
              }}
            >
              ⟨missing⟩
            </mark>,
            part,
          ],
    );
  }

  return (
    <Shell crumb="New campaign">
      <h1 className="m-0 mb-1.5 text-[clamp(1.5rem,3vw,2.1rem)] font-bold leading-[1.02] tracking-[-.035em] text-balance">
        New campaign
      </h1>
      <p className="text-muted m-0 mb-6 max-w-[62ch] text-[.88rem] leading-[1.6]">
        Pick recipients, write once, personalize per person.
      </p>

      <Stepper current={1} />

      <div className="grid items-start gap-[22px] lg:grid-cols-2">
        <div className="flex flex-col gap-3">
          <div className="card">
            <SectionLabel>Recipients</SectionLabel>
            {useMocks ? (
              <div className="flex flex-wrap gap-[7px]" style={{ marginBottom: 16 }}>
                {RECIPIENT_GROUPS.map((g) => (
                  <span
                    key={g.id}
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: ".66rem",
                      fontWeight: 700,
                      padding: "6px 11px",
                      borderRadius: 3,
                      border: "1px solid var(--color-accent)",
                      color: "var(--color-accent)",
                      background: "var(--accent-dim)",
                    }}
                  >
                    {g.label}
                  </span>
                ))}
              </div>
            ) : loadingGroups ? (
              <p className="text-muted" style={{ fontSize: ".82rem", marginBottom: 16 }}>
                Loading mailing lists…
              </p>
            ) : groups.length === 0 ? (
              <div
                className="card"
                style={{
                  borderColor: "rgba(217,164,65,.35)",
                  background: "rgba(217,164,65,.06)",
                  marginBottom: 16,
                }}
              >
                <p style={{ margin: "0 0 10px", fontSize: ".82rem", lineHeight: 1.55, color: "var(--muted)" }}>
                  <b style={{ color: "var(--color-paper)" }}>No mailing lists yet.</b> Create one and
                  import recipients before you can run preflight or launch a campaign.
                </p>
                <Link href="/app/lists/new" className="btn btn-sm no-underline">
                  Create a mailing list
                  <ArrowRight />
                </Link>
              </div>
            ) : (
              <label className="mb-4 block">
                <span className="field-label">Mailing list</span>
                <select
                  className="input"
                  value={selectedGroupId ?? ""}
                  onChange={(e) => setSelectedGroupId(e.target.value || null)}
                >
                  <option value="" disabled>
                    Select a mailing list
                  </option>
                  {groups.map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.name} ({g.contact_count})
                    </option>
                  ))}
                </select>
              </label>
            )}
            <div
              className="flex items-center justify-between"
              style={{ borderTop: "1px solid var(--line)", paddingTop: 12 }}
            >
              <span style={{ fontFamily: "var(--font-mono)", fontSize: ".72rem", color: "var(--muted)" }}>
                Resolved recipients
              </span>
              <span
                className="num"
                style={{ fontFamily: "var(--font-mono)", fontSize: "1.1rem", fontWeight: 600 }}
              >
                {recipientCount.toLocaleString()}
              </span>
            </div>
          </div>

          <div className="card">
            <SectionLabel>Message</SectionLabel>
            {!useMocks && templates.length > 0 && (
              <label className="mb-4 block">
                <span className="field-label">Start from a template</span>
                <select
                  className="input"
                  value={sourceTemplateId ?? ""}
                  onChange={(e) => handleTemplatePick(e.target.value)}
                >
                  <option value="">Blank — write from scratch</option>
                  {templates.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name} (v{t.current_version})
                    </option>
                  ))}
                </select>
              </label>
            )}
            {!useMocks && (
              <label className="mb-4 block">
                <span className="field-label">Campaign / template name</span>
                <input
                  className="input"
                  value={templateName}
                  onChange={(e) => setTemplateName(e.target.value)}
                />
              </label>
            )}
            <label className="mb-4 block">
              <span className="field-label">Subject</span>
              <input
                className="input"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
              />
            </label>
            <label className="mb-4 block">
              <span className="field-label">Body</span>
              <textarea
                className="input"
                rows={9}
                value={body}
                onChange={(e) => setBody(e.target.value)}
                style={{ fontFamily: "var(--font-mono)", fontSize: ".78rem", lineHeight: 1.7, resize: "vertical" }}
              />
            </label>
            <div className="flex flex-wrap items-center gap-[9px]">
              <span style={{ fontFamily: "var(--font-mono)", fontSize: ".62rem", color: "var(--faint)" }}>
                Variables:
              </span>
              {["{{first_name}}", "{{event_name}}", "{{specialization}}"].map((v) => (
                <span
                  key={v}
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: ".72rem",
                    background: "var(--accent-dim)",
                    color: "var(--color-accent)",
                    padding: "1px 5px",
                    borderRadius: 2,
                  }}
                >
                  {v}
                </span>
              ))}
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-3">
          <div className="card">
            <div className="mb-3.5 flex items-center justify-between">
              <div className="sec" style={{ margin: 0 }}>
                Preview as recipient
              </div>
              <select
                className="input"
                value={whoId}
                onChange={(e) => setWhoId(e.target.value)}
                style={{ width: "auto", fontSize: ".76rem", padding: "6px 9px" }}
              >
                {(useMocks ? CONTACTS : liveContacts).map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name || c.email}
                  </option>
                ))}
              </select>
            </div>
            {!useMocks && liveContacts.length === 0 ? (
              <p className="text-muted" style={{ fontSize: ".82rem" }}>
                Pick a mailing list with recipients to preview as one of them.
              </p>
            ) : (
              <div
                style={{
                  background: "var(--color-paper)",
                  color: "var(--color-ink)",
                  borderRadius: 3,
                  padding: 22,
                  fontSize: ".84rem",
                  lineHeight: 1.66,
                }}
              >
                <div
                  style={{
                    borderBottom: "1px solid rgba(20,17,15,.12)",
                    paddingBottom: 12,
                    marginBottom: 14,
                  }}
                >
                  <div style={{ fontFamily: "var(--font-mono)", fontSize: ".66rem", color: "rgba(20,17,15,.55)" }}>
                    To: {useMocks ? mockWho.email : liveWho?.email}
                  </div>
                  <h5 style={{ margin: "6px 0 0", fontSize: "1rem", letterSpacing: "-.02em", fontWeight: 600 }}>
                    {renderWithMissingMarker(renderedSubject)}
                  </h5>
                </div>
                {useMocks ? (
                  <div style={{ whiteSpace: "pre-wrap" }}>{renderWithMissingMarker(renderedBody)}</div>
                ) : (
                  // The template body is HTML authored by this org (same trust
                  // boundary as the editor textarea above it), not third-party
                  // input — rendering it as markup here is what makes the
                  // preview match what a recipient's inbox actually shows,
                  // instead of leaking raw <p> tags as literal text.
                  <div dangerouslySetInnerHTML={{ __html: renderedBody }} />
                )}
              </div>
            )}
          </div>

          {useMocks && (
            <div
              className="card"
              style={{ borderColor: "rgba(217,164,65,.35)", background: "rgba(217,164,65,.06)" }}
            >
              <div className="flex items-start gap-[9px]">
                <span style={{ color: "var(--color-warn)" }}>⚠</span>
                <p style={{ margin: 0, fontSize: ".8rem", lineHeight: 1.55, color: "var(--muted)" }}>
                  <b style={{ color: "var(--color-paper)" }}>7 of 127 recipients</b> have no value for{" "}
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: ".72rem",
                      background: "var(--accent-dim)",
                      color: "var(--color-accent)",
                      padding: "1px 5px",
                      borderRadius: 2,
                    }}
                  >
                    {"{{specialization}}"}
                  </span>
                  . Preflight will show you exactly who.
                </p>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="h-6" />
      {error && (
        <p style={{ color: "var(--color-crit)", fontSize: ".82rem", marginBottom: 12 }}>{error}</p>
      )}
      <div className="flex flex-wrap items-center gap-[9px]">
        {useMocks ? (
          <Link href="/app/campaigns/new/preflight" className="btn no-underline">
            Run preflight
            <ArrowRight />
          </Link>
        ) : (
          <button
            type="button"
            className="btn"
            disabled={submitting || !selectedGroupId}
            onClick={handleRunPreflight}
          >
            {submitting ? "Saving…" : <>Run preflight<ArrowRight /></>}
          </button>
        )}
        <button type="button" className="btn btn-ghost">
          Save draft
        </button>
      </div>
    </Shell>
  );
}
