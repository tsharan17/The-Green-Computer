import { useEffect, useState } from "react";
import { BASE } from "../api";
import PublicChrome from "../components/PublicChrome";

interface M { value: number; unit: string; low: number; high: number; provenance: string }
interface Out {
  device: string; power_mode: string; limit: string; fits_memory: boolean; weights_gb: number; cache_gb: number; usable_memory_gb: number;
  tokens_per_s: M; first_token_s: M; memory_gb: M; power_w: M; energy_per_token_j: M; notes: string[];
}
interface Dev { id: string; name: string; precisions: string[] }

const SIZES: [string, number][] = [["1 billion parameters", 1000], ["3 billion", 3000], ["7 billion", 7000], ["13 billion", 13000], ["70 billion", 70000]];
const n = (x: number) => (x >= 100 ? x.toFixed(0) : x >= 1 ? x.toFixed(1) : x.toPrecision(2));

/** A first estimate for language models. Plainly labelled as predicted and not yet validated. */
export default function LlmPage({ signedIn = false }: { signedIn?: boolean }) {
  const [devs, setDevs] = useState<Dev[]>([]);
  const [device, setDevice] = useState("");
  const [size, setSize] = useState(7000);
  const [precision, setPrecision] = useState("int8");
  const [prompt, setPrompt] = useState(256);
  const [context, setContext] = useState(2048);
  const [out, setOut] = useState<Out | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${BASE}/estimate/llm/devices`, { credentials: "same-origin" }).then((r) => r.json()).then((d: Dev[]) => {
      setDevs(d);
      setDevice((v) => v || d.find((x) => x.id === "jetson-orin-nx")?.id || d[0]?.id || "");
    }).catch(() => setError("Could not load the device list."));
  }, []);

  const dev = devs.find((d) => d.id === device);
  const precisions = (dev?.precisions ?? []).filter((p) => ["fp32", "fp16", "int8"].includes(p));

  async function run(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setOut(null);
    const r = await fetch(`${BASE}/estimate/llm`, {
      method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-GC-CSRF": "1" },
      body: JSON.stringify({ device_id: device, params_m: size, precision: precisions.includes(precision) ? precision : precisions[0], prompt_tokens: prompt, context_tokens: context }),
    });
    const body = await r.json();
    if (r.ok) setOut(body);
    else setError(typeof body.detail === "string" ? body.detail : "Check the values and try again.");
  }

  const rows: [string, M][] = out ? [["Output speed", out.tokens_per_s], ["Time to first token", out.first_token_s], ["Memory needed", out.memory_gb], ["Power", out.power_w], ["Energy per token", out.energy_per_token_j]] : [];
  return (
    <PublicChrome signedIn={signedIn}>
      <article className="pub-section pub-prose" aria-labelledby="llm-h1">
        <h1 id="llm-h1">Language model estimate</h1>
        <p className="pub-lead">A first estimate of output speed and memory for a language model on a device. <strong>Predicted, and not yet checked against a real run</strong>, so treat it as a starting point and test on the real device.</p>
        <form className="inline-form" onSubmit={run}>
          <label className="field">Device
            <select value={device} onChange={(e) => setDevice(e.target.value)}>{devs.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select>
          </label>
          <label className="field">Model size
            <select value={size} onChange={(e) => setSize(Number(e.target.value))}>{SIZES.map(([l, v]) => <option key={v} value={v}>{l}</option>)}</select>
          </label>
          <label className="field">Precision
            <select value={precisions.includes(precision) ? precision : precisions[0] ?? ""} onChange={(e) => setPrecision(e.target.value)}>{precisions.map((p) => <option key={p} value={p}>{p.toUpperCase()}</option>)}</select>
          </label>
          <label className="field">Prompt tokens<input type="number" min={1} max={1000000} value={prompt} onChange={(e) => setPrompt(Number(e.target.value))} required /></label>
          <label className="field">Context tokens<input type="number" min={1} max={2000000} value={context} onChange={(e) => setContext(Number(e.target.value))} required /></label>
          <button className="primary" disabled={!device || !precisions.length}>Estimate</button>
        </form>
        {error && <p className="note-warn" role="alert">{error}</p>}
        {out && (
          <div aria-live="polite">
            <h2>{out.device}, {out.power_mode}</h2>
            <p>{out.fits_memory ? `Fits in memory: ${out.usable_memory_gb} GB usable.` : `Does not fit: only ${out.usable_memory_gb} GB usable.`} Speed is limited by {out.limit}. Weights {out.weights_gb} GB, context cache {out.cache_gb} GB.</p>
            <div className="table-wrap">
              <table className="tbl">
                <thead><tr><th scope="col">Figure</th><th scope="col">Predicted</th><th scope="col">Range</th></tr></thead>
                <tbody>{rows.map(([l, m]) => <tr key={l}><th scope="row">{l}</th><td className="num">{n(m.value)} {m.unit}</td><td className="num">{n(m.low)} to {n(m.high)}</td></tr>)}</tbody>
              </table>
            </div>
            <ul>{out.notes.map((t) => <li key={t}>{t}</li>)}</ul>
          </div>
        )}
      </article>
    </PublicChrome>
  );
}
