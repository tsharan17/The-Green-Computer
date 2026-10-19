import Logo from "../components/Logo";
import { useEffect, useState } from "react";
import { auth } from "../api";
import { navigate } from "../router";
import type { AuthConfig, Me } from "../types";

type Mode = "signin" | "signup" | "forgot" | "reset";

const COPY: Record<Mode, { title: string; lead: string; action: string }> = {
  signin: { title: "Sign in", lead: "Pick up your projects where you left them.", action: "Sign in" },
  signup: {
    title: "Create your account",
    lead: "Your projects, uploads and measurements stay private to your workspace.",
    action: "Create account",
  },
  forgot: { title: "Reset your password", lead: "We will send a link that works for one hour.", action: "Send reset link" },
  reset: { title: "Choose a new password", lead: "Every device signed in to this account will be signed out.", action: "Save new password" },
};

export default function AuthPage({ mode, token, onSignedIn }: { mode: Mode; token?: string; onSignedIn: (me: Me) => void }) {
  const [cfg, setCfg] = useState<AuthConfig | null>(null);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<{ message: string; link?: string; note?: string } | null>(null);

  useEffect(() => {
    auth.config().then(setCfg).catch(() => setCfg(null));
  }, []);
  useEffect(() => {
    setError(null);
    setDone(null);
    setPassword("");
  }, [mode]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "signin") onSignedIn(await auth.signin(email, password));
      else if (mode === "signup") onSignedIn(await auth.signup(email, password, name));
      else if (mode === "forgot") {
        const r = await auth.forgot(email);
        setDone({ message: r.message, link: r.dev_reset_url, note: r.dev_note });
      } else {
        await auth.reset(token || "", password);
        setDone({ message: "Password changed. Sign in with the new password." });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const c = COPY[mode];
  const minLen = cfg?.password_min_length ?? 10;
  return (
    <div className="auth">
      <section className="auth-intro" aria-label="About The Green Computer">
        <div className="brandmark">
          <Logo />
          <strong>The Green Computer</strong>
        </div>
        <h1>See how an AI model will run on your hardware before you build it.</h1>
        <p>
          Describe or upload the model and the board, set what must be true, and get predicted latency, memory, power,
          heat and energy, operator by operator, with the changes that meet your requirements on the least energy.
        </p>
        <ul className="auth-points">
          <li>Every number carries its source and its range: predicted, calibrated or measured.</li>
          <li>Runs fully on your own machine. GPU and AI-assistant integrations are optional.</li>
          <li>Recommendations you can select, re-analyse and export as a versioned design plan.</li>
        </ul>
      </section>

      <section className="auth-card" aria-labelledby="auth-title">
        <h2 id="auth-title">{c.title}</h2>
        <p className="muted">{c.lead}</p>
        {done ? (
          <div className="auth-done" role="status">
            <p>{done.message}</p>
            {done.link && (
              <div className="note-info">
                <p>{done.note}</p>
                <a href={done.link.replace(/^https?:\/\/[^/]+\//, "/")}>Open the reset link</a>
              </div>
            )}
            <button className="primary" onClick={() => navigate("/signin")}>Back to sign in</button>
          </div>
        ) : (
          <form onSubmit={submit} noValidate>
            {mode === "signup" && (
              <label className="field">
                Your name (optional)
                <input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" maxLength={120} />
              </label>
            )}
            {mode !== "reset" && (
              <label className="field">
                Email
                <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" autoFocus />
              </label>
            )}
            {mode !== "forgot" && (
              <label className="field">
                {mode === "reset" ? "New password" : "Password"}
                <input
                  type="password"
                  required
                  minLength={mode === "signin" ? undefined : minLen}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete={mode === "signin" ? "current-password" : "new-password"}
                  aria-describedby={mode !== "signin" ? "pw-hint" : undefined}
                />
                {mode !== "signin" && (
                  <span id="pw-hint" className="hint">At least {minLen} characters. A short sentence works well.</span>
                )}
              </label>
            )}
            {error && <p className="error" role="alert">{error}</p>}
            <button className="primary wide" disabled={busy} type="submit">
              {busy ? "Working…" : c.action}
            </button>
          </form>
        )}
        <div className="auth-links">
          {mode === "signin" && (
            <>
              {cfg?.signup_allowed !== false && <a href="#/signup">Create an account</a>}
              <a href="#/forgot">Forgot your password?</a>
            </>
          )}
          {mode !== "signin" && <a href="#/signin">I already have an account</a>}
        </div>
        {cfg && cfg.environment !== "production" && cfg.email_delivery === "console" && mode === "forgot" && !done && (
          <p className="hint">This server has no mail delivery configured, so reset links are written to the server log.</p>
        )}
      </section>
    </div>
  );
}
