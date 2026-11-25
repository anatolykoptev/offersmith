// Headless runner for OpenResume's PDF parser (github.com/xitanggg/open-resume, AGPL-3.0, fetched by install.sh, never vendored).
// Usage: tsx --tsconfig open-resume/tsconfig.json run.ts file.pdf     Prints one JSON object on stdout.
// It calls OpenResume's own pipeline unmodified: readPdf -> groupTextItemsIntoLines -> groupLinesIntoSections -> extractResumeFromSections.
// SHIM: under Node, read-pdf.ts gets an object (not a path) from its pdf.worker.entry import, so pdf.js cannot set up its fake worker.
// Pre-seeding globalThis.pdfjsWorker (pdf.js checks it first) fixes that without editing any OpenResume source.
// SECURITY: pdfjs-dist 3.7.107 (the version OpenResume pins) is affected by GHSA-wgrm-67xf-hhpq / CVE-2024-4367: a crafted PDF font runs
// JavaScript through `new Function` when pdf.js' eval path is on. pdf.js only takes that path if `new Function("")` works, so the runner is
// started with node --disallow-code-generation-from-strings (ats_check/openresume.py sets it) and refuses to read a PDF without it.
try {
  new Function("");
  console.error("run.ts: refusing to parse a PDF with code generation from strings enabled; run node with --disallow-code-generation-from-strings");
  process.exit(4);
} catch {}

import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const req = createRequire(join(HERE, "package.json"));
(globalThis as any).pdfjsWorker = req("pdfjs-dist/build/pdf.worker.js");

// SECOND LAYER and page bookkeeping, without editing any OpenResume source: pdf.js exports getDocument through a non-configurable getter, so
// the module's entry in the require cache is swapped for a copy whose getDocument (1) passes isEvalSupported: false, the advisory's own
// workaround, and (2) records the text items of every page, so the PDF is parsed once and the page ends are known.
const real = req("pdfjs-dist");
const getDocumentParams: any[] = [];
const pages: { items: number; lastHasEOL: boolean }[] = [];
const patched: any = {};
for (const k of Object.keys(real).filter((k) => k !== "getDocument")) Object.defineProperty(patched, k, { enumerable: true, get: () => real[k] });
Object.defineProperty(patched, "getDocument", {
  enumerable: true,
  value: (src: any) => {
    const params = { ...(typeof src === "string" ? { url: src } : src), isEvalSupported: false };
    getDocumentParams.push({ isEvalSupported: params.isEvalSupported });
    const task = real.getDocument(params);
    const promise = task.promise.then((doc: any) => {
      const getPage = doc.getPage.bind(doc);
      doc.getPage = async (n: number) => {
        const page = await getPage(n);
        const getTextContent = page.getTextContent.bind(page);
        page.getTextContent = async (...a: any[]) => {
          const tc = await getTextContent(...a);
          const kept = tc.items.filter((i: any) => !(!i.hasEOL && i.str.trim() === ""));   // the filter readPdf applies
          pages[n - 1] = { items: kept.length, lastHasEOL: kept.length ? !!kept[kept.length - 1].hasEOL : true };
          return tc;
        };
        return page;
      };
      return doc;
    });
    return { promise, destroy: () => task.destroy() };
  },
});
req.cache[req.resolve("pdfjs-dist")]!.exports = patched;

const { readPdf } = await import("lib/parse-resume-from-pdf/read-pdf");
const { groupTextItemsIntoLines } = await import("lib/parse-resume-from-pdf/group-text-items-into-lines");
const { groupLinesIntoSections } = await import("lib/parse-resume-from-pdf/group-lines-into-sections");
const { extractResumeFromSections } = await import("lib/parse-resume-from-pdf/extract-resume-from-sections");
const { BULLET_POINTS } = await import("lib/parse-resume-from-pdf/extract-resume-from-sections/lib/bullet-points");

const file = process.argv[2];
const items: any[] = await readPdf(file);
items.forEach((it, i) => { it.rawIdx = i; });   // groupTextItemsIntoLines copies items with a spread, so rawIdx survives into the lines
const lines = groupTextItemsIntoLines(items);
const sections = groupLinesIntoSections(lines);
const resume = extractResumeFromSections(sections);

const r1 = (n: number) => Math.round(n * 10) / 10;
console.log(JSON.stringify({
  bulletPoints: BULLET_POINTS,
  getDocumentParams,
  resume,
  pages,
  raw: items.map((i) => [i.text, r1(i.x), r1(i.y), r1(i.width), r1(i.height), String(i.fontName), i.hasEOL ? 1 : 0]),
  lines: lines.map((l: any[]) => ({
    start: l.length ? l[0].rawIdx : null,
    items: l.map((i) => [i.text, r1(i.x), r1(i.y), r1(i.width), String(i.fontName)]),
  })),
}));
