import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const source = "C:/Users/sesur/Downloads/sistema de alarma.xlsx";
const outDir = ".codex_tmp/quote_previews";
await fs.mkdir(outDir, { recursive: true });
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(source));
const sheets = await workbook.inspect({ kind: "sheet", include: "id,name", maxChars: 10000 });
console.log("SHEETS\n" + sheets.ndjson);
const overview = await workbook.inspect({
  kind: "workbook,sheet,table", maxChars: 30000,
  tableMaxRows: 25, tableMaxCols: 16, tableMaxCellChars: 120,
});
console.log("OVERVIEW\n" + overview.ndjson);
const formulas = await workbook.inspect({
  kind: "formula", maxChars: 30000, options: { maxResults: 300 },
});
console.log("FORMULAS\n" + formulas.ndjson);
for (let i = 0; i < workbook.worksheets.items.length; i++) {
  const sheet = workbook.worksheets.getItemAt(i);
  const preview = await workbook.render({ sheetName: sheet.name, autoCrop: "all", scale: 1, format: "png" });
  const safe = sheet.name.replace(/[^a-z0-9_-]+/gi, "_");
  await fs.writeFile(`${outDir}/${i + 1}_${safe}.png`, new Uint8Array(await preview.arrayBuffer()));
}
const errors = await workbook.inspect({
  kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 }, maxChars: 10000,
});
console.log("ERRORS\n" + errors.ndjson);
