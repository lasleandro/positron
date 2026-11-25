import { useCallback, useEffect, useState } from "react";

/** Install-to-home-screen helpers (pattern from agenda_ai's mobile app shell). */

const SNOOZE_KEY = "podeabrir:install-snooze";
const SNOOZE_MS = 30 * 24 * 60 * 60 * 1000;

export function isStandalone(): boolean {
  return window.matchMedia?.("(display-mode: standalone)").matches
    || (navigator as Navigator & { standalone?: boolean }).standalone === true; // iOS home screen
}

export function isIos(): boolean {
  const ua = navigator.userAgent;
  // iPadOS reports itself as a Mac; touch points disambiguate.
  return /iPad|iPhone|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);
}

export function isPhone(): boolean {
  return window.matchMedia?.("(max-width: 720px)").matches ?? false;
}

export function isInstallSnoozed(): boolean {
  try {
    return Date.now() - Number(localStorage.getItem(SNOOZE_KEY) || 0) < SNOOZE_MS;
  } catch {
    return false;
  }
}

export function snoozeInstall(): void {
  try {
    localStorage.setItem(SNOOZE_KEY, String(Date.now()));
  } catch {
    // Private mode / storage disabled: the banner simply shows again next time.
  }
}

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

let deferredPrompt: BeforeInstallPromptEvent | null = null;
const listeners = new Set<() => void>();
const notify = () => listeners.forEach((listener) => listener());

// Captured at module load, before React mounts, so the one-shot event is never missed.
window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  deferredPrompt = event as BeforeInstallPromptEvent;
  notify();
});
window.addEventListener("appinstalled", () => {
  deferredPrompt = null;
  notify();
});

export type InstallStatus = "installed" | "available" | "manual";

/** "available": one-tap install (Android/Chromium); "manual": iOS or browser menu. */
export function useInstallPrompt() {
  const [, rerender] = useState(0);
  useEffect(() => {
    const listener = () => rerender((value) => value + 1);
    listeners.add(listener);
    return () => { listeners.delete(listener); };
  }, []);
  const status: InstallStatus = isStandalone() ? "installed" : deferredPrompt ? "available" : "manual";
  const promptInstall = useCallback(async () => {
    if (!deferredPrompt) return;
    await deferredPrompt.prompt();
    const { outcome } = await deferredPrompt.userChoice;
    deferredPrompt = null;
    if (outcome === "dismissed") snoozeInstall();
    notify();
  }, []);
  return { status, promptInstall };
}
