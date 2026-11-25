# Mobile layout and installable app (PWA)

Date: 2026-11-25
Reference: agenda_ai mobile app shell (install prompt capture, iOS instructions page, install card
with 30-day snooze, offline page, maskable icons, safe areas).

## Mobile layout

- Owners on phones (≤ 720 px) get a bottom tab bar (Documentos, Compartilhar with the request
  badge, Ler, Conta); the top menu is hidden there and "Sair" lives in Conta.
- The documents table becomes cards below 640 px (name, date · issuer, four actions, sort chips).
- Tap targets: table checkboxes have a 42 px hit area, sort headers 36 px, toggles and text links
  are padded; content respects `env(safe-area-inset-*)` (`viewport-fit=cover`).
- Audit (2026-11-25, Chromium emulating iPhone 13 and Pixel 7, 16 views each, owner and reader):
  no horizontal overflow on any view; screenshots reviewed for every page.

## Installable app

| Item | Implementation |
|---|---|
| Manifest | `id: "/"`, `start_url: /documentos/`, standalone, Marfim background/theme, `any` + `maskable` icons (192/512), shortcuts (link, compartilhamentos, ler) |
| Maskable icons | Generated once from the brand symbol into `frontend/assets/web/icon-maskable-*.png` (symbol inside the 80 % safe circle), copied by `npm run brand` |
| iOS | `apple-mobile-web-app-capable`, title, status bar style, `apple-touch-icon` from the kit |
| Android install | `beforeinstallprompt` captured at start-up (`src/lib/pwa.ts`); one-tap "Instalar" |
| iOS install | `/instalar/`: Safari → Compartilhar → Adicionar à Tela de Início; push needs the installed app (iOS 16.4+) |
| Install card | Phones, signed-in owners, dismissible, snoozed 30 days (`localStorage`) |
| Offline | `public/offline.html` (no data, no scripts). The service worker caches only this file and serves it when a navigation fails without network; API, documents and pages are never cached |

Verified: manifest fields and icons served; iOS/Android variants of `/instalar/`; with the server
unreachable, a controlled page navigates to the branded "Sem conexão" page.

## Not verified / not done

- Real devices (iPhone Safari, Android Chrome): install, standalone launch, push delivery.
- iOS launch images (`apple-touch-startup-image`) are not provided; iOS shows a plain screen
  while the app starts.
