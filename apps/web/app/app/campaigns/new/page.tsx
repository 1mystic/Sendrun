"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import Shell from "@/components/Shell";
import { SectionLabel } from "@/components/ui";
import { CONTACTS, DEFAULT_TEMPLATE, RECIPIENT_GROUPS, renderTemplate } from "@/lib/mock";
import { createTemplate, getCurrentOrgId, setCampaignDraft, useMocks } from "@/lib/api";
import Stepper from "../Stepper";

export default function ComposePage() {
  const router = useRouter();
  const [selectedGroups, setSelectedGroups] = useState<Set<string>>(
    () => new Set(["speaker"]),
  );
  const [subject, setSubject] = useState(DEFAULT_TEMPLATE.subject);
  const [body, setBody] = useState(DEFAULT_TEMPLATE.body);
  const [whoId, setWhoId] = useState(CONTACTS[0].id);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const recipientCount = useMemo(
    () =>
      RECIPIENT_GROUPS.filter((g) => selectedGroups.has(g.id)).reduce(
        (sum, g) => sum + g.count,
        0,
      ),
    [selectedGroups],
  );

  const who = CONTACTS.find((c) => c.id === whoId) ?? CONTACTS[0];
  const renderedSubject = renderTemplate(subject, who);
  const renderedBody = renderTemplate(body, who);

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
    setError(null);
    setSubmitting(true);
    try {
      const variableMatches = [...subject.matchAll(/\{\{(\w+)\}\}/g), ...body.matchAll(/\{\{(\w+)\}\}/g)];
      const variables = [...new Set(variableMatches.map((m) => m[1]))];
      const template = await createTemplate(orgId, {
        name: "Untitled campaign",
        subject,
        html_body: body,
        variables,
      });
      setCampaignDraft({
        name: "Untitled campaign",
        templateId: template.id,
        recipients: { tags: [...selectedGroups], exclude_suppressed: true },
      });
      router.push("/app/campaigns/new/preflight");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save template");
    } finally {
      setSubmitting(false);
    }
  }

  function toggleGroup(id: string) {
    setSelectedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
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
            <label className="mb-4 block">
              <span className="field-label">Select by</span>
              <div className="flex flex-wrap gap-[7px]">
                {RECIPIENT_GROUPS.map((g) => {
                  const active = selectedGroups.has(g.id);
                  return (
                    <button
                      key={g.id}
                      type="button"
                      aria-pressed={active}
                      onClick={() => toggleGroup(g.id)}
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 6,
                        fontFamily: "var(--font-mono)",
                        fontSize: ".66rem",
                        fontWeight: active ? 700 : 500,
                        padding: "6px 11px",
                        borderRadius: 3,
                        border: `1px solid ${active ? "var(--color-accent)" : "var(--line-2)"}`,
                        color: active ? "var(--color-accent)" : "var(--muted)",
                        background: active ? "var(--accent-dim)" : "transparent",
                        transition: "all .18s",
                      }}
                    >
                      {g.label}
                    </button>
                  );
                })}
              </div>
            </label>
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
                {CONTACTS.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
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
                  To: {who.email}
                </div>
                <h5 style={{ margin: "6px 0 0", fontSize: "1rem", letterSpacing: "-.02em", fontWeight: 600 }}>
                  {renderWithMissingMarker(renderedSubject)}
                </h5>
              </div>
              <div style={{ whiteSpace: "pre-wrap" }}>{renderWithMissingMarker(renderedBody)}</div>
            </div>
          </div>

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
        </div>
      </div>

      <div className="h-6" />
      {error && (
        <p style={{ color: "var(--color-crit)", fontSize: ".82rem", marginBottom: 12 }}>{error}</p>
      )}
      <div className="flex flex-wrap items-center gap-[9px]">
        {useMocks ? (
          <Link href="/app/campaigns/new/preflight" className="btn no-underline">
            Run preflight →
          </Link>
        ) : (
          <button type="button" className="btn" disabled={submitting} onClick={handleRunPreflight}>
            {submitting ? "Saving…" : "Run preflight →"}
          </button>
        )}
        <button type="button" className="btn btn-ghost">
          Save draft
        </button>
      </div>
    </Shell>
  );
}
