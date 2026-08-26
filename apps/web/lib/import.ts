/**
 * Pure helpers for the mailing-list import wizard
 * (apps/web/app/app/lists/import/[groupId]/page.tsx). No React, no DOM —
 * kept testable in principle even though this project has no frontend test
 * runner yet.
 */

export interface ParsedTable {
  headers: string[];
  rows: string[][];
}

export interface ColumnMapping {
  emailColumn: string;
  nameColumn: string | null;
}

/**
 * Delimiter is guessed once from the whole sample, not per line, so that a
 * single stray comma inside one row can't flip the format for the rest of
 * the paste. Priority order: comma, tab, 2+ spaces, single space — comma is
 * the most common export format, and single-space is tried last because it
 * misfires on multi-word names ("John Smith") whenever a stricter delimiter
 * would have worked.
 */
export function detectDelimiter(sample: string): RegExp {
  const lines = sample.split(/\r?\n/).filter((l) => l.trim().length > 0);
  if (lines.some((l) => l.includes(","))) return /,/;
  if (lines.some((l) => l.includes("\t"))) return /\t/;
  if (lines.some((l) => /\s{2,}/.test(l))) return /\s{2,}/;
  return /\s+/;
}

/** A header row has no `@` in any cell; a data row's first line typically does. */
export function looksLikeHeaderRow(firstLine: string): boolean {
  return !firstLine.includes("@");
}

export function parsePastedText(text: string): ParsedTable {
  const lines = text.split(/\r?\n/).filter((l) => l.trim().length > 0);
  if (lines.length === 0) return { headers: [], rows: [] };

  const delimiter = detectDelimiter(text);
  const split = (line: string) => line.split(delimiter).map((cell) => cell.trim());

  const hasHeader = looksLikeHeaderRow(lines[0]);
  const dataLines = hasHeader ? lines.slice(1) : lines;
  const rows = dataLines.map(split);

  const columnCount = Math.max(
    hasHeader ? split(lines[0]).length : 0,
    ...rows.map((r) => r.length),
    1,
  );

  const headers = hasHeader
    ? padTo(split(lines[0]), columnCount, (i) => `Column ${i + 1}`)
    : Array.from({ length: columnCount }, (_, i) => `Column ${i + 1}`);

  return { headers, rows: rows.map((r) => padTo(r, columnCount, () => "")) };
}

function padTo(arr: string[], len: number, fill: (i: number) => string): string[] {
  const out = arr.slice(0, len);
  while (out.length < len) out.push(fill(out.length));
  return out;
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function isLikelyValidEmail(value: string): boolean {
  return EMAIL_RE.test(value.trim());
}

/**
 * Converts a parsed table into the `{ values: Record<string,string> }[]`
 * shape the import API expects — every column, keyed by header, for every
 * row. The email/name mapping is sent alongside as separate fields
 * (`email_column`/`name_column`) rather than filtered out here: unmapped
 * columns pass through unchanged and become free-form `{{variable}}` fields
 * on the backend, not something the user has to opt into per column.
 */
export function buildImportRows(table: ParsedTable): Array<{ values: Record<string, string> }> {
  return table.rows.map((row) => {
    const values: Record<string, string> = {};
    table.headers.forEach((header, i) => {
      values[header] = row[i] ?? "";
    });
    return { values };
  });
}

export interface RowValidation {
  rowIndex: number;
  email: string;
  valid: boolean;
}

export function validateRows(
  table: ParsedTable,
  mapping: ColumnMapping,
): RowValidation[] {
  const emailIdx = table.headers.indexOf(mapping.emailColumn);
  return table.rows.map((row, i) => {
    const email = emailIdx >= 0 ? (row[emailIdx] ?? "") : "";
    return { rowIndex: i, email, valid: isLikelyValidEmail(email) };
  });
}
