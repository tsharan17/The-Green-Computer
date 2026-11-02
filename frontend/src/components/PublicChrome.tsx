import { type ReactNode, useEffect, useState } from "react";
import { auth } from "../api";
import { LegalLinks } from "../pages/LegalPage";
import type { AuthConfig } from "../types";
import InstallButton from "./Install";
import Logo from "./Logo";

let cached: Promise<AuthConfig | null> | null = null;

/** The public site settings (operator, contact), fetched once per page load. */
export function useSiteInfo(): AuthConfig | null {
  const [cfg, setCfg] = useState<AuthConfig | null>(null);
  useEffect(() => {
    cached ??= auth.config().catch(() => null);
    let live = true;
    cached.then((c) => live && setCfg(c));
    return () => {
      live = false;
    };
  }, []);
  return cfg;
}

export function feedbackHref(cfg: AuthConfig | null): string | null {
  return cfg?.contact_email ? `mailto:${cfg.contact_email}?subject=${encodeURIComponent("The Green Computer feedback")}` : null;
}

/** Jumps to the main content. With hash routing a plain `href="#id"` would change the route, so focus
 * moves without touching the URL. */
export function SkipLink({ target }: { target: string }) {
  return (
    <a className="skip" href={`#${target}`} onClick={(e) => {
      e.preventDefault();
      const el = document.getElementById(target);
      el?.focus();
      el?.scrollIntoView();
    }}>Skip to content</a>
  );
}

/** Header, main and footer for the pages anyone can open without an account. */
export default function PublicChrome({ children, signedIn = false }: { children: ReactNode; signedIn?: boolean }) {
  const cfg = useSiteInfo();
  return (
    <div className="pub">
      <SkipLink target="pub-main" />
      <header className="pub-head">
        <a className="pub-brand" href="#/">
          <Logo size={28} />
          <strong>The Green Computer</strong>
        </a>
        <nav className="pub-nav" aria-label="Site">
          <a href="#/try">Try an example</a>
          <a href="#/how">How we estimate</a>
          <InstallButton />
          {signedIn ? (
            <a className="btn-link primary" href="#/">Open your workspace</a>
          ) : (
            <>
              <a href="#/signin">Sign in</a>
              <a className="btn-link primary" href="#/signup">Create a free account</a>
            </>
          )}
        </nav>
      </header>
      <main id="pub-main" className="pub-main" tabIndex={-1}>{children}</main>
      <footer className="pub-foot">
        <p>
          The Green Computer is operated by {cfg?.operator ?? "T Sharan"}.
          {cfg?.contact_email && <> Contact: <a href={`mailto:${cfg.contact_email}`}>{cfg.contact_email}</a>.</>}
        </p>
        <LegalLinks />
      </footer>
    </div>
  );
}
