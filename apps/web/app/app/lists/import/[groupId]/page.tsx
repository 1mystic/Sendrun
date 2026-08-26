"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMemo, useRef, useState } from "react";
import Papa from "papaparse";
import * as XLSX from "xlsx";
import Shell from "@/components/Shell";
import { PageTitle, SectionLabel } from "@/components/ui";
import {
  getCurrentOrgId,
  importContactsToGroup,
  type BulkImportResult,
} from "@/lib/api";
import {
  buildImportRows,
  parsePastedText,
  validateRows,
  type ParsedTable,
} from "@/lib/import";
import ImportStepper from "../ImportStepper";

type SourceTab = "paste" | "file";

function parseSheet(headerRow: unknown[], dataRows: unknown[][]): ParsedTable {
  const headers = headerRow.map((h, i) => (h == null || String(h).trim() === "" ? `Column ${i + 1}` : String(h)));
  const rows = dataRows.map((row) =>
    headers.map((_, i) => (row[i] == null ? "" : String(row[i]))),
  );
  return { headers, rows };
}

export default function ImportWizardPage() {
  const params = useParams<{ groupId: string }>();
  const groupId = params.groupId;
  const router = useRouter();

  const [step, setStep] = useState(1);
  const [tab, setTab] = useState<SourceTab>("paste");
  const [pasteText, setPasteText] = useState("");
  const [table, setTable] = useState<ParsedTable | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [emailColumn, setEmailColumn] = useState<string>("");
  const [nameColumn, setNameColumn] = useState<string>("");

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [result, setResult] = useState<BulkImportResult | null>(null);

  function handlePasteChange(text: string) {
    setPasteText(text);
    setParseError(null);
    if (text.trim() === "") {
      setTable(null);
      return;
    }
    const parsed = parsePastedText(text);
    setTable(parsed);
  }

  function handleFile(file: File) {
    setParseError(null);
    const ext = file.name.split(".").pop()?.toLowerCase();
    if (ext === "csv") {
      Papa.parse(file, {
        complete: (res) => {
          const rows = res.data as string[][];
          if (rows.length === 0) {
            setParseError("File appears empty.");
            return;
          }
          setTable(parseSheet(rows[0], rows.slice(1)));
        },
        error: (err) => setParseError(err.message),
      });
      return;
    }
    if (ext === "xlsx" || ext === "xls") {
      file.arrayBuffer().then((buf) => {
        try {
          const wb = XLSX.read(buf, { type: "array" });
          const sheet = wb.Sheets[wb.SheetNames[0]];
          const rows = XLSX.utils.sheet_to_json<unknown[]>(sheet, { header: 1 });
          if (rows.length === 0) {
            setParseError("File appears empty.");
            return;
          }
          setTable(parseSheet(rows[0] as unknown[], rows.slice(1) as unknown[][]));
        } catch (err) {
          setParseError(err instanceof Error ? err.message : "Could not parse file");
        }
      });
      return;
    }
    setParseError("Unsupported file type — use .csv or .xlsx.");
  }

  const mapping = useMemo(() => ({ emailColumn, nameColumn: nameColumn || null }), [emailColumn, nameColumn]);

  const validation = useMemo(() => {
    if (!table || !emailColumn) return [];
    return validateRows(table, mapping);
  }, [table, emailColumn, mapping]);

  const validCount = validation.filter((v) => v.valid).length;
  const invalidCount = validation.length - validCount;

  async function handleImport() {
    if (!table) return;
    const orgId = getCurrentOrgId();
    if (!orgId) {
      setSubmitError("No organization selected — sign in again.");
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    try {
      const rows = buildImportRows(table);
      const res = await importContactsToGroup(orgId, groupId, {
        email_column: emailColumn,
        name_column: nameColumn || null,
        rows,
      });
      setResult(res);
      setStep(4);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Shell
      crumb="Import contacts"
      actions={<Link href={`/app/lists/${groupId}`} className="btn btn-ghost btn-sm no-underline">← Back to list</Link>}
    >
      <PageTitle title="Import contacts" lede="Paste rows or upload a file, map columns, then confirm." />

      <ImportStepper current={step} />

      {step === 1 && (
        <div className="card">
          <SectionLabel>Get data in</SectionLabel>
          <div className="mb-4 flex gap-[7px]">
            {(["paste", "file"] as const).map((t) => {
              const active = tab === t;
              return (
                <button
                  key={t}
                  type="button"
                  aria-pressed={active}
                  onClick={() => setTab(t)}
                  style={{
                    display: "inline-flex", alignItems: "center", gap: 6, fontFamily: "var(--font-mono)",
                    fontSize: ".66rem", fontWeight: active ? 700 : 500, padding: "6px 11px", borderRadius: 3,
                    border: `1px solid ${active ? "var(--color-accent)" : "var(--line-2)"}`,
                    color: active ? "var(--color-accent)" : "var(--muted)",
                    background: active ? "var(--accent-dim)" : "transparent", transition: "all .18s",
                    textTransform: "uppercase",
                  }}
                >
                  {t === "paste" ? "Paste text" : "Upload file"}
                </button>
              );
            })}
          </div>

          {tab === "paste" ? (
            <label className="block">
              <span className="field-label">Paste rows (CSV, tab, or space separated)</span>
              <textarea
                className="input"
                rows={10}
                value={pasteText}
                onChange={(e) => handlePasteChange(e.target.value)}
                placeholder={"email,name\nrahul@example.com,Rahul Menon\nananya@example.com,Ananya Iyer"}
                style={{ fontFamily: "var(--font-mono)", fontSize: ".78rem", lineHeight: 1.7, resize: "vertical" }}
              />
            </label>
          ) : (
            <div>
              <span className="field-label">Upload .csv or .xlsx</span>
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv,.xlsx,.xls"
                className="input"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) handleFile(file);
                }}
                style={{ padding: 8 }}
              />
            </div>
          )}

          {parseError && <p style={{ color: "var(--color-crit)", fontSize: ".8rem", marginTop: 10 }}>{parseError}</p>}

          {table && table.rows.length > 0 && (
            <p className="text-muted" style={{ fontFamily: "var(--font-mono)", fontSize: ".68rem", marginTop: 12 }}>
              Detected {table.headers.length} column{table.headers.length === 1 ? "" : "s"}, {table.rows.length} row{table.rows.length === 1 ? "" : "s"}.
            </p>
          )}

          <div className="h-4" />
          <button
            type="button"
            className="btn"
            disabled={!table || table.rows.length === 0}
            onClick={() => {
              setEmailColumn(table?.headers.find((h) => /email/i.test(h)) ?? "");
              setNameColumn(table?.headers.find((h) => /name/i.test(h)) ?? "");
              setStep(2);
            }}
          >
            Next: map columns →
          </button>
        </div>
      )}

      {step === 2 && table && (
        <div className="card">
          <SectionLabel>Map columns</SectionLabel>
          <div className="overflow-x-auto" style={{ border: "1px solid var(--line)", borderRadius: 3, marginBottom: 18 }}>
            <table className="w-full border-collapse text-[.82rem]" style={{ minWidth: 480 }}>
              <thead>
                <tr>
                  <th className="text-faint px-3.5 py-2.5 text-left font-normal uppercase" style={{ fontFamily: "var(--font-mono)", fontSize: ".58rem", letterSpacing: ".12em", borderBottom: "1px solid var(--line)", background: "var(--color-ink-2)" }}>
                    Column
                  </th>
                  <th className="text-faint px-3.5 py-2.5 text-left font-normal uppercase" style={{ fontFamily: "var(--font-mono)", fontSize: ".58rem", letterSpacing: ".12em", borderBottom: "1px solid var(--line)", background: "var(--color-ink-2)" }}>
                    Maps to
                  </th>
                </tr>
              </thead>
              <tbody>
                {table.headers.map((header) => (
                  <tr key={header} style={{ borderBottom: "1px solid var(--line)" }}>
                    <td className="px-3.5 py-3 font-semibold">{header}</td>
                    <td className="px-3.5 py-3">
                      <select
                        className="input"
                        style={{ width: "auto", fontSize: ".76rem", padding: "6px 9px" }}
                        value={emailColumn === header ? "email" : nameColumn === header ? "name" : "unmapped"}
                        onChange={(e) => {
                          const v = e.target.value;
                          if (v === "email") {
                            setEmailColumn(header);
                            if (nameColumn === header) setNameColumn("");
                          } else if (v === "name") {
                            setNameColumn(header);
                            if (emailColumn === header) setEmailColumn("");
                          } else {
                            if (emailColumn === header) setEmailColumn("");
                            if (nameColumn === header) setNameColumn("");
                          }
                        }}
                      >
                        <option value="unmapped">Unmapped (kept as field)</option>
                        <option value="email">Email</option>
                        <option value="name">Name</option>
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <SectionLabel>Preview — first 5 rows</SectionLabel>
          <div className="overflow-x-auto" style={{ border: "1px solid var(--line)", borderRadius: 3 }}>
            <table className="w-full border-collapse text-[.78rem]" style={{ minWidth: 480 }}>
              <thead>
                <tr>
                  {table.headers.map((h) => (
                    <th key={h} className="text-faint px-3 py-2 text-left font-normal uppercase" style={{ fontFamily: "var(--font-mono)", fontSize: ".56rem", letterSpacing: ".1em", borderBottom: "1px solid var(--line)", background: "var(--color-ink-2)" }}>
                      {h}
                      {emailColumn === h && <span style={{ color: "var(--color-accent)" }}> · email</span>}
                      {nameColumn === h && <span style={{ color: "var(--color-ok)" }}> · name</span>}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {table.rows.slice(0, 5).map((row, i) => (
                  <tr key={i} style={{ borderBottom: "1px solid var(--line)" }}>
                    {row.map((cell, j) => (
                      <td key={j} className="px-3 py-2" style={{ fontFamily: "var(--font-mono)", color: "var(--muted)" }}>{cell}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="h-4" />
          {!emailColumn && (
            <p style={{ color: "var(--color-warn)", fontSize: ".8rem", marginBottom: 12 }}>
              Map exactly one column to Email before continuing.
            </p>
          )}
          <div className="flex flex-wrap gap-[9px]">
            <button type="button" className="btn" disabled={!emailColumn} onClick={() => setStep(3)}>
              Next: preview →
            </button>
            <button type="button" className="btn btn-ghost" onClick={() => setStep(1)}>
              ← Back
            </button>
          </div>
        </div>
      )}

      {step === 3 && table && (
        <div className="card">
          <SectionLabel>Preview + confirm</SectionLabel>
          <div className="mb-5 grid gap-[clamp(12px,1.1vw,18px)] md:grid-cols-3">
            <div className="card" style={{ padding: "clamp(14px,1.2vw,20px)" }}>
              <div className="num" style={{ fontSize: "1.8rem", fontWeight: 700, letterSpacing: "-.03em" }}>
                {table.rows.length}
              </div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: ".6rem", color: "var(--faint)", textTransform: "uppercase", marginTop: 4 }}>
                Total rows
              </div>
            </div>
            <div className="card" style={{ padding: "clamp(14px,1.2vw,20px)" }}>
              <div className="num" style={{ fontSize: "1.8rem", fontWeight: 700, letterSpacing: "-.03em", color: "var(--color-ok)" }}>
                {validCount}
              </div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: ".6rem", color: "var(--faint)", textTransform: "uppercase", marginTop: 4 }}>
                Valid emails
              </div>
            </div>
            <div className="card" style={{ padding: "clamp(14px,1.2vw,20px)" }}>
              <div className="num" style={{ fontSize: "1.8rem", fontWeight: 700, letterSpacing: "-.03em", color: invalidCount > 0 ? "var(--color-warn)" : "var(--faint)" }}>
                {invalidCount}
              </div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: ".6rem", color: "var(--faint)", textTransform: "uppercase", marginTop: 4 }}>
                Look invalid
              </div>
            </div>
          </div>

          {invalidCount > 0 && (
            <div className="card mb-4" style={{ borderColor: "rgba(217,164,65,.35)", background: "rgba(217,164,65,.06)" }}>
              <p style={{ margin: 0, fontSize: ".8rem", lineHeight: 1.55, color: "var(--muted)" }}>
                <span style={{ color: "var(--color-warn)" }}>⚠</span>{" "}
                <b style={{ color: "var(--color-paper)" }}>{invalidCount} row{invalidCount === 1 ? "" : "s"}</b> have
                an email that doesn&rsquo;t look valid. This is a quick client-side check — the backend does the
                real validation, and those rows will be reported as skipped if they fail there.
              </p>
            </div>
          )}

          {submitError && <p style={{ color: "var(--color-crit)", fontSize: ".82rem", marginBottom: 12 }}>{submitError}</p>}

          <div className="flex flex-wrap gap-[9px]">
            <button type="button" className="btn" disabled={submitting} onClick={handleImport}>
              {submitting ? "Importing…" : `Import ${table.rows.length} contact${table.rows.length === 1 ? "" : "s"}`}
            </button>
            <button type="button" className="btn btn-ghost" onClick={() => setStep(2)}>
              ← Back
            </button>
          </div>
        </div>
      )}

      {step === 4 && result && (
        <div className="card">
          <SectionLabel>Result</SectionLabel>
          <div className="mb-5 grid gap-[clamp(12px,1.1vw,18px)] md:grid-cols-3">
            <div className="card" style={{ padding: "clamp(14px,1.2vw,20px)" }}>
              <div className="num" style={{ fontSize: "1.8rem", fontWeight: 700, letterSpacing: "-.03em", color: "var(--color-ok)" }}>
                {result.created}
              </div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: ".6rem", color: "var(--faint)", textTransform: "uppercase", marginTop: 4 }}>
                Created
              </div>
            </div>
            <div className="card" style={{ padding: "clamp(14px,1.2vw,20px)" }}>
              <div className="num" style={{ fontSize: "1.8rem", fontWeight: 700, letterSpacing: "-.03em" }}>
                {result.updated}
              </div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: ".6rem", color: "var(--faint)", textTransform: "uppercase", marginTop: 4 }}>
                Updated
              </div>
            </div>
            <div className="card" style={{ padding: "clamp(14px,1.2vw,20px)" }}>
              <div className="num" style={{ fontSize: "1.8rem", fontWeight: 700, letterSpacing: "-.03em", color: result.skipped.length > 0 ? "var(--color-warn)" : "var(--faint)" }}>
                {result.skipped.length}
              </div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: ".6rem", color: "var(--faint)", textTransform: "uppercase", marginTop: 4 }}>
                Skipped
              </div>
            </div>
          </div>

          {result.skipped.length > 0 && (
            <>
              <SectionLabel>Skipped rows</SectionLabel>
              <div className="overflow-x-auto" style={{ border: "1px solid var(--line)", borderRadius: 3, marginBottom: 18 }}>
                <table className="w-full border-collapse text-[.8rem]" style={{ minWidth: 400 }}>
                  <thead>
                    <tr>
                      <th className="text-faint px-3.5 py-2 text-left font-normal uppercase" style={{ fontFamily: "var(--font-mono)", fontSize: ".58rem", letterSpacing: ".12em", borderBottom: "1px solid var(--line)", background: "var(--color-ink-2)" }}>
                        Row
                      </th>
                      <th className="text-faint px-3.5 py-2 text-left font-normal uppercase" style={{ fontFamily: "var(--font-mono)", fontSize: ".58rem", letterSpacing: ".12em", borderBottom: "1px solid var(--line)", background: "var(--color-ink-2)" }}>
                        Reason
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.skipped.map((s) => (
                      <tr key={s.row_index} style={{ borderBottom: "1px solid var(--line)" }}>
                        <td className="num px-3.5 py-2">{s.row_index}</td>
                        <td className="px-3.5 py-2" style={{ color: "var(--color-warn)" }}>{s.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          <p className="text-muted" style={{ fontSize: ".84rem", marginBottom: 16 }}>
            List now has {result.group_contact_count.toLocaleString()} contact{result.group_contact_count === 1 ? "" : "s"}.
          </p>

          <button type="button" className="btn" onClick={() => router.push(`/app/lists/${groupId}`)}>
            View list →
          </button>
        </div>
      )}
    </Shell>
  );
}
