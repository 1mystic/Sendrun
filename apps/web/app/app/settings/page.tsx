"use client";

import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { PageTitle, Pill } from "@/components/ui";
import { ORG_SETTINGS, SENDING_SETTINGS, TEAM_MEMBERS } from "@/lib/mock-ops";
import {
  getCurrentOrgId,
  inviteMember,
  listMembers,
  updateOrganization,
  useMocks,
  type MemberOut,
} from "@/lib/api";

const TABS = [
  { id: "org", label: "Organization" },
  { id: "team", label: "Team" },
  { id: "sending", label: "Sending" },
  { id: "providers", label: "Providers" },
  { id: "danger", label: "Danger zone" },
] as const;

type TabId = (typeof TABS)[number]["id"];

function roleTone(role: string): "ok" | "warn" | "default" {
  if (role.toLowerCase() === "owner") return "ok";
  if (role.toLowerCase() === "admin") return "warn";
  return "default";
}

function Field({
  id, label, defaultValue, hint, type = "text", disabled = false,
}: {
  id: string;
  label: string;
  defaultValue: string | number;
  hint?: string;
  type?: string;
  disabled?: boolean;
}) {
  return (
    <label htmlFor={id} className="field-label" style={{ marginBottom: 16, display: "block" }}>
      {label}
      <input id={id} className="input mt-1.5" type={type} defaultValue={defaultValue} disabled={disabled} />
      {hint && (
        <span className="mt-1 block" style={{ fontFamily: "var(--font-mono)", fontSize: ".62rem", color: "var(--faint)", textTransform: "none", letterSpacing: 0 }}>
          {hint}
        </span>
      )}
    </label>
  );
}

export default function SettingsPage() {
  const [tab, setTab] = useState<TabId>("org");
  const [members, setMembers] = useState<MemberOut[]>(useMocks ? TEAM_MEMBERS.map((m) => ({
    user_id: m.id, name: m.name, email: m.email, role: m.role.toLowerCase(),
  })) : []);
  const [loadingMembers, setLoadingMembers] = useState(!useMocks);
  const [orgName, setOrgName] = useState(ORG_SETTINGS.name);
  const [savingOrg, setSavingOrg] = useState(false);
  const [orgSaved, setOrgSaved] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviting, setInviting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      if (useMocks) return;
      const orgId = getCurrentOrgId();
      if (!orgId) {
        setError("No organization selected — sign in again.");
        setLoadingMembers(false);
        return;
      }
      try {
        setMembers(await listMembers(orgId));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load team");
      } finally {
        setLoadingMembers(false);
      }
    }
    load();
  }, []);

  async function handleSaveOrgName() {
    const orgId = getCurrentOrgId();
    if (!orgId || useMocks) return;
    setSavingOrg(true);
    setOrgSaved(false);
    try {
      await updateOrganization(orgId, orgName);
      setOrgSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save organization name");
    } finally {
      setSavingOrg(false);
    }
  }

  async function handleInvite() {
    const orgId = getCurrentOrgId();
    if (!orgId || useMocks || !inviteEmail) return;
    setInviting(true);
    try {
      await inviteMember(orgId, inviteEmail, "editor");
      setInviteEmail("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not send invite");
    } finally {
      setInviting(false);
    }
  }

  return (
    <Shell crumb="Settings">
      <PageTitle title="Settings" lede="Organization, team, sending configuration, and providers." />

      {error && <p style={{ color: "var(--color-crit)", fontSize: ".82rem", marginBottom: 12 }}>{error}</p>}

      <div className="mb-6 flex flex-wrap gap-[7px]">
        {TABS.map((t) => {
          const active = t.id === tab;
          return (
            <button
              key={t.id}
              type="button"
              aria-pressed={active}
              onClick={() => setTab(t.id)}
              style={{
                display: "inline-flex", alignItems: "center", gap: 6, fontFamily: "var(--font-mono)",
                fontSize: ".66rem", fontWeight: active ? 700 : 500, padding: "6px 11px", borderRadius: 3,
                border: `1px solid ${active ? "var(--color-accent)" : "var(--line-2)"}`,
                color: active ? "var(--color-accent)" : "var(--muted)",
                background: active ? "var(--accent-dim)" : "transparent", transition: "all .18s",
              }}
            >
              {t.label}
            </button>
          );
        })}
      </div>

      {tab === "org" && (
        <div className="card" style={{ maxWidth: 480 }}>
          <div className="sec">Organization</div>
          {useMocks ? (
            <>
              <Field id="org-name" label="Name" defaultValue={ORG_SETTINGS.name} />
              <Field id="org-slug" label="Slug" defaultValue={ORG_SETTINGS.slug} hint="Used in URLs and API references." />
              <Field id="org-tz" label="Timezone" defaultValue={ORG_SETTINGS.timezone} />
              <button type="button" className="btn mt-2" disabled>Save changes</button>
            </>
          ) : (
            <>
              <label htmlFor="org-name" className="field-label" style={{ marginBottom: 16, display: "block" }}>
                Name
                <input id="org-name" className="input mt-1.5" value={orgName} onChange={(e) => setOrgName(e.target.value)} />
              </label>
              <button type="button" className="btn mt-2" disabled={savingOrg} onClick={handleSaveOrgName}>
                {savingOrg ? "Saving…" : orgSaved ? "Saved" : "Save changes"}
              </button>
              <p className="text-faint mt-3" style={{ fontFamily: "var(--font-mono)", fontSize: ".62rem", lineHeight: 1.6 }}>
                Slug and timezone are not yet configurable — only the display name has a live backend field.
              </p>
            </>
          )}
        </div>
      )}

      {tab === "team" && (
        <div className="card">
          <div className="row-between mb-4 flex items-center justify-between">
            <div className="sec m-0">Team members</div>
            {!useMocks && (
              <div className="flex items-center gap-2">
                <input
                  className="input"
                  placeholder="email@example.com"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  style={{ width: 220, padding: "6px 9px", fontSize: ".76rem" }}
                />
                <button type="button" className="btn btn-sm" disabled={inviting || !inviteEmail} onClick={handleInvite}>
                  {inviting ? "Inviting…" : "Invite"}
                </button>
              </div>
            )}
            {useMocks && <button type="button" className="btn btn-sm" disabled>Invite</button>}
          </div>
          {loadingMembers && <p className="text-faint">Loading team…</p>}
          {!loadingMembers && (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-[.82rem]" style={{ minWidth: 520 }}>
                <thead>
                  <tr>
                    {["Name", "Email", "Role"].map((h) => (
                      <th key={h} className="text-faint px-3.5 py-2.5 text-left font-normal uppercase" style={{ fontFamily: "var(--font-mono)", fontSize: ".58rem", letterSpacing: ".12em", borderBottom: "1px solid var(--line)" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {members.map((m) => (
                    <tr key={m.user_id} style={{ borderBottom: "1px solid var(--line)" }}>
                      <td className="px-3.5 py-3 font-semibold">{m.name}</td>
                      <td className="px-3.5 py-3" style={{ fontFamily: "var(--font-mono)", fontSize: ".74rem", color: "var(--muted)" }}>{m.email}</td>
                      <td className="px-3.5 py-3"><Pill tone={roleTone(m.role)}>{m.role}</Pill></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {tab === "sending" && (
        <div className="card" style={{ maxWidth: 480 }}>
          <div className="sec">Sending configuration</div>
          <Field id="from-name" label="From name" defaultValue={SENDING_SETTINGS.fromName} disabled={!useMocks} />
          <Field id="from-address" label="From address" defaultValue={SENDING_SETTINGS.fromAddress} type="email" disabled={!useMocks} />
          <Field id="reply-to" label="Reply-to" defaultValue={SENDING_SETTINGS.replyTo} type="email" disabled={!useMocks} />
          <Field id="daily-cap" label="Daily send cap" defaultValue={SENDING_SETTINGS.dailyCap} type="number" hint="Hard limit across all campaigns per 24h window." disabled={!useMocks} />
          <Field id="rate-limit" label="Rate limit" defaultValue={SENDING_SETTINGS.ratePerSecond} type="number" hint="Sends per second to the provider." disabled={!useMocks} />
          <button type="button" className="btn mt-2" disabled>Save changes</button>
          {!useMocks && (
            <p className="text-faint mt-3" style={{ fontFamily: "var(--font-mono)", fontSize: ".62rem", lineHeight: 1.6 }}>
              Not yet configurable — send rate is set per-campaign at launch; there is no
              org-level sending settings endpoint yet.
            </p>
          )}
        </div>
      )}

      {tab === "providers" && (
        <div className="flex flex-col gap-4" style={{ maxWidth: 560 }}>
          <div className="card">
            <div className="sec">Email provider</div>
            <label htmlFor="email-provider" className="field-label">
              Active provider
              <select id="email-provider" className="input mt-1.5" defaultValue="fake" disabled>
                <option value="fake">fake (development)</option>
                <option value="sendgrid">SendGrid</option>
                <option value="ses">Amazon SES</option>
                <option value="postmark">Postmark</option>
              </select>
            </label>
            <div className="mt-2 flex items-center gap-2">
              <Pill tone="run">Active: fake</Pill>
            </div>
            <p className="text-faint mt-3" style={{ fontFamily: "var(--font-mono)", fontSize: ".62rem", lineHeight: 1.6 }}>
              Set by EMAIL_PROVIDER in the backend environment — not switchable from this UI.
              Real provider keys drop into .env with zero code change.
            </p>
          </div>
          <div className="card">
            <div className="sec">LLM provider</div>
            <label htmlFor="llm-provider" className="field-label">
              Active provider
              <select id="llm-provider" className="input mt-1.5" defaultValue="fake" disabled>
                <option value="fake">fake (development)</option>
                <option value="anthropic">Anthropic</option>
                <option value="openai">OpenAI</option>
              </select>
            </label>
            <div className="mt-2 flex items-center gap-2">
              <Pill tone="run">Active: fake</Pill>
            </div>
            <p className="text-faint mt-3" style={{ fontFamily: "var(--font-mono)", fontSize: ".62rem", lineHeight: 1.6 }}>
              Set by LLM_PROVIDER in the backend environment — not switchable from this UI.
            </p>
          </div>
        </div>
      )}

      {tab === "danger" && (
        <div className="card" style={{ maxWidth: 560, borderColor: "rgba(228,73,31,.4)", background: "var(--accent-dim)" }}>
          <div className="sec" style={{ color: "var(--color-crit)" }}>Danger zone</div>
          <p className="text-muted mb-4 text-[.82rem] leading-[1.6]">
            Deleting this organization removes all campaigns, contacts, templates, and send
            history. This cannot be undone.
          </p>
          <button type="button" className="btn" style={{ background: "var(--color-crit)", borderColor: "var(--color-crit)" }} disabled>
            Delete organization
          </button>
          {!useMocks && (
            <p className="text-faint mt-3" style={{ fontFamily: "var(--font-mono)", fontSize: ".62rem", lineHeight: 1.6 }}>
              Not yet implemented on the backend — no delete_organization endpoint exists.
            </p>
          )}
        </div>
      )}
    </Shell>
  );
}
