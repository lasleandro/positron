// Copies the brand kit (frontend/assets, the single source of truth) into public/ at the
// fixed paths browsers, the web manifest, emails and link previews expect.
import { copyFile, mkdir } from "node:fs/promises";

const from = (path) => new URL(`../assets/${path}`, import.meta.url);
const to = (path) => new URL(`../public/${path}`, import.meta.url);

const FILES = {
  "web/favicon.svg": "favicon.svg",
  "web/favicon.ico": "favicon.ico",
  "web/apple-touch-icon.png": "apple-touch-icon.png",
  "web/icon-192.png": "icon-192.png",
  "web/icon-512.png": "icon-512.png",
  "web/icon-maskable-192.png": "icon-maskable-192.png",
  "web/icon-maskable-512.png": "icon-maskable-512.png",
  "social/compartilhamento-1200x630.png": "social/compartilhamento-1200x630.png",
  "png/simbolo/pode-abrir-simbolo-branco-128.png": "brand/badge-128.png",
  "png/assinatura/pode-abrir-assinatura-grafite-480.png": "brand/assinatura-grafite-480.png",
};

await mkdir(to("social/"), { recursive: true });
await mkdir(to("brand/"), { recursive: true });
for (const [source, target] of Object.entries(FILES)) await copyFile(from(source), to(target));
