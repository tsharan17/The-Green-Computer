import { useEffect, useState } from "react";

interface Health {
  version: string;
  demo_mode: boolean;
}

/** Footer: what is connected, so nobody mistakes a prediction for a live measurement. */
export default function StatusBar() {
  const [h, setH] = useState<Health | null>(null);
  useEffect(() => {
    fetch("/api/v1/health").then((r) => r.json()).then(setH).catch(() => setH(null));
  }, []);
  return (
    <footer className="statusbar">
      <span><i className={`dot ${h ? "on" : ""}`} /> {h ? `Service online · v${h.version}` : "Service unreachable"}</span>
      {h?.demo_mode && <span><i className="dot warn" /> Public demo mode</span>}
    </footer>
  );
}
