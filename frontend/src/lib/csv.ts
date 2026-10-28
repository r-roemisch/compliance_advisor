/** CSV the way German Excel opens it without a wizard: BOM, semicolons, every cell quoted. */
export function toCsv(header: string[], rows: string[][]): string {
  const cell = (v: string | undefined | null) => `"${(v ?? "").replace(/"/g, '""')}"`;
  const lines = [header.map(cell).join(";")].concat(rows.map((r) => r.map(cell).join(";")));
  return "\ufeff" + lines.join("\r\n");
}
