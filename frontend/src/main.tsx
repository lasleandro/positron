import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { PAIRING_CODE, STORAGE } from "./lib/crypto";
import "./lib/pwa"; // captures the Android install prompt before React mounts
import "./styles.css";

// The office QR opens /autorizar/#CODE.FINGERPRINT. Keep the code for the Approve
// page (it survives a detour through login) and strip it from the address bar.
const fragment = location.hash.slice(1);
if (location.pathname.startsWith("/autorizar") && PAIRING_CODE.test(fragment)) {
  sessionStorage.setItem(STORAGE.pairing, fragment);
  history.replaceState(history.state, "", location.pathname + location.search);
}

// Opening an emailed link (invite, reset) or a QR in a tab already on that page only changes
// the fragment; reload so the page reads the new token through the normal start-up path.
window.addEventListener("hashchange", () => {
  const value = location.hash.slice(1);
  if (/^[A-Za-z0-9_-]{43}$/.test(value) || PAIRING_CODE.test(value)) location.reload();
});

// Installable app + push. The worker caches nothing (see public/sw.js).
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
