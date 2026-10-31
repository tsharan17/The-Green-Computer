import { useEffect, useState } from "react";
import { tryApi } from "../api";
import { Chip, MetricTable, configLabel, fmt } from "../components/common";
import { ErrorNote } from "../components/Help";
import PublicChrome from "../components/PublicChrome";
import { CONFIDENCE_WORDS, EFFORT_WORDS } from "../lib/plain";
import type { Alternative, Feasibility, TryAnalysis, TryExample, VerdictSide } from "../types";

const OK: Feasibility[] = ["verified_feasible", "predicted_feasible"];
const RANK: Record<Feasibility, number> = {
  verified_feasible: 0, predicted_feasible: 0, uncertain: 1, infeasible: 2, verified_infeasible: 2,
};

function SideRow({ label, s }: { label: string; s: VerdictSide }) {
  return (
    <tr>
      <th scope="row">{label}</th>
      <td><Chip state={s.state} /></td>
      <td>{fmt(s.latency_ms)} ms</td>
      <td>{fmt(s.capacity_fps)} /s</td>
      <td>{fmt(s.power_w)} W</td>
      <td>{fmt(s.temperature_c)} °C</td>
      <td>{fmt(s.energy_mj)} mJ</td>
    </tr>
  );
}

function otherHardware(alts: Alternative[]): Alternative[] {
  return alts
    .filter((a) => a.kind === "device")
    .sort((a, b) => RANK[a.feasibility] - RANK[b.feasibility] || a.energy_mj - b.energy_mj)
    .slice(0, 6);
}

function Analysis({ a }: { a: TryAnalysis }) {
  const r = a.result;
  const v = r.verdict;
  const w = a.spec.workload;
  const c = a.spec.constraints;
  const hw = otherHardware(r.alternatives);
  return (
    <article className="try-analysis" aria-labelledby="try-title">
      <h2 id="try-title">{a.case.title}</h2>
      <p className="muted">{a.case.blurb}</p>
      <p className="try-setup">
        <strong>{a.model.name}</strong> on <strong>{a.device.name}</strong>, {w.fps} inputs a second at {w.ambient_c} °C
        {c.max_latency_ms ? `, answer within ${c.max_latency_ms} ms` : ""}
        {c.max_power_w ? `, under ${c.max_power_w} W` : ""}.
      </p>

      {v && (
        <section className="panel" aria-labelledby="try-verdict">
          <h3 id="try-verdict">The answer</h3>
          <p className="try-summary">{v.summary}</p>
          <div className="table-wrap">
            <table className="tbl">
              <thead>
                <tr><th scope="col">Setup</th><th scope="col">Outcome</th><th scope="col">Latency</th><th scope="col">Keeps up with</th>
                  <th scope="col">Power</th><th scope="col">Temperature</th><th scope="col">Energy per input</th></tr>
              </thead>
              <tbody>
                <SideRow label="As it is today" s={v.baseline} />
                {v.improved && <SideRow label="With the recommended changes" s={v.improved} />}
              </tbody>
            </table>
          </div>
          {v.improved && <p className="hint">Recommended setup: {configLabel(v.improved.config)}</p>}
          {r.limiting_factor && <p><strong>What limits it:</strong> {r.limiting_factor}</p>}
        </section>
      )}

      {r.advice.length > 0 && (
        <section className="panel" aria-labelledby="try-advice">
          <h3 id="try-advice">Changes worth making</h3>
          <ol className="try-advice">
            {r.advice.slice(0, 5).map((x) => (
              <li key={x.id}>
                <strong>{x.title}</strong> <span className="try-gain">{x.gain}</span>
                <div className="muted">{x.action}</div>
                <div className="hint">{CONFIDENCE_WORDS[x.confidence].label} · {EFFORT_WORDS[x.effort]}{x.in_recommended ? " · part of the recommended plan" : ""}</div>
              </li>
            ))}
          </ol>
        </section>
      )}

      {hw.length > 0 && (
        <section className="panel" aria-labelledby="try-hw">
          <h3 id="try-hw">The same job on other hardware</h3>
          <div className="table-wrap">
            <table className="tbl">
              <thead>
                <tr><th scope="col">Device</th><th scope="col">Outcome</th><th scope="col">Latency</th><th scope="col">Power</th><th scope="col">Energy per input</th></tr>
              </thead>
              <tbody>
                {hw.map((x) => (
                  <tr key={x.id}>
                    <th scope="row">{x.name}</th>
                    <td><Chip state={x.feasibility} /></td>
                    <td>{fmt(x.latency_ms)} ms</td>
                    <td>{fmt(x.power_w)} W</td>
                    <td>{fmt(x.energy_mj)} mJ</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="hint">Each device at its own best setting for this job. {hw.filter((x) => OK.includes(x.feasibility)).length} of {hw.length} shown meet every requirement.</p>
        </section>
      )}

      <section className="panel" aria-labelledby="try-metrics">
        <h3 id="try-metrics">Every figure for today's setup, with its range</h3>
        <div className="table-wrap"><MetricTable r={r.baseline} /></div>
        <p className="hint">{a.note} <a href="#/how">How we estimate</a>.</p>
      </section>
    </article>
  );
}

export default function TryPage({ caseId, signedIn = false }: { caseId: string | null; signedIn?: boolean }) {
  const [cases, setCases] = useState<TryExample[]>([]);
  const [data, setData] = useState<TryAnalysis | null>(null);
  const [error, setError] = useState<unknown>(null);
  const active = caseId ?? cases[0]?.id ?? null;

  useEffect(() => {
    tryApi.examples().then(setCases).catch(setError);
  }, []);
  useEffect(() => {
    if (!active) return;
    setData(null);
    setError(null);
    tryApi.example(active).then(setData).catch(setError);
  }, [active]);

  return (
    <PublicChrome signedIn={signedIn}>
      <section className="pub-section" aria-labelledby="try-h1">
        <h1 id="try-h1">Try an example</h1>
        <p className="pub-lead">
          Full analyses of six example setups, computed by the same engine you get with an account. Read only:
          {signedIn ? " open your workspace" : " create a free account"} to analyse your own model and hardware.
        </p>
        <nav className="try-cases" aria-label="Examples">
          {cases.map((x) => (
            <a key={x.id} href={`#/try/${x.id}`} aria-current={x.id === active ? "page" : undefined}>{x.title}</a>
          ))}
        </nav>
        <ErrorNote error={error} />
        {data ? <Analysis a={data} /> : !error && (
          <div className="skeleton" aria-busy="true" aria-label="Analysing the example">
            <div className="sk-line w60" /><div className="sk-line w90" /><div className="sk-line w90" />
          </div>
        )}
        <div className="pub-cta">
          <a className="btn-link primary" href={signedIn ? "#/" : "#/signup"}>{signedIn ? "Open your workspace" : "Analyse your own setup, free"}</a>
        </div>
      </section>
    </PublicChrome>
  );
}
