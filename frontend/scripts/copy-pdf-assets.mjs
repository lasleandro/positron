// Copies the PDF.js runtime assets (fonts, cmaps, ICC profiles, wasm decoders)
// into public/pdfjs so they are served from our own origin (CSP: 'self' only).
import { cp, mkdir, rm } from "node:fs/promises";

const source = new URL("../node_modules/pdfjs-dist/", import.meta.url);
const target = new URL("../public/pdfjs/", import.meta.url);
await rm(target, { recursive: true, force: true });
await mkdir(target, { recursive: true });
for (const path of ["LICENSE", "cmaps", "iccs", "standard_fonts", "wasm"]) {
  const destination = new URL(path, target);
  await mkdir(new URL(".", destination), { recursive: true });
  await cp(new URL(path, source), destination, { recursive: true });
}
