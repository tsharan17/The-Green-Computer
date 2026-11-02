import { useEffect, useState } from "react";

/** The browser's install offer (Chromium's `beforeinstallprompt`; not in the DOM typings). */
interface InstallPrompt extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

let offer: InstallPrompt | null = null;
const listeners = new Set<() => void>();
const changed = () => listeners.forEach((f) => f());

/** Registers the shell-only service worker in production builds and keeps the install offer, which
 * the browser fires once, possibly before any button has mounted. */
export function setUpInstall(): void {
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    offer = e as InstallPrompt;
    changed();
  });
  window.addEventListener("appinstalled", () => {
    offer = null;
    changed();
  });
  if (import.meta.env.PROD && "serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/sw.js").catch(() => undefined);
    });
  }
}

/** "Install the app", shown only where the browser offers installation and the app is not installed. */
export default function InstallButton({ className = "" }: { className?: string }) {
  const [, render] = useState(0);
  useEffect(() => {
    const f = () => render((n) => n + 1);
    listeners.add(f);
    return () => {
      listeners.delete(f);
    };
  }, []);
  if (!offer) return null;
  return (
    <button type="button" className={`install-btn ${className}`} onClick={async () => {
      const o = offer;
      if (!o) return;
      await o.prompt();
      await o.userChoice;
      offer = null; // a prompt can be shown once; the browser fires a new event if it may offer again
      changed();
    }}>
      Install the app
    </button>
  );
}
