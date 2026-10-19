import { useCallback, useEffect, useState } from "react";
import { download, plans } from "../api";
import { when } from "../pages/WorkspacePage";
import type { ExportCatalogItem, ExportItem, SavedPlan } from "../types";

const LABEL_CLASS: Record<string, string> = {
  generated_validated: "badge-measured",
  generated: "badge-analytical",
  template: "badge-assumed",
};

function size(n: number) {
  return n < 1024 ? `${n} B` : n < 1024 ** 2 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1024 ** 2).toFixed(2)} MB`;
}

export default function ExportPanel({ projectId, canWrite }: { projectId: number; canWrite: boolean }) {
  const [catalog, setCatalog] = useState<ExportCatalogItem[] | null>(null);
  const [saved, setSaved] = useState<SavedPlan[]>([]);
  const [planId, setPlanId] = useState<number | null>(null);
  const [history, setHistory] = useState<ExportItem[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const load = useCallback(async () => {
    const [c, p, h] = await Promise.all([plans.exportCatalog(projectId), plans.list(projectId).catch(() => []), plans.exports(projectId)]);
    setCatalog(c);
    setSaved(p);
    setHistory(h);
    setPlanId((cur) => cur ?? p[0]?.id ?? null);
  }, [projectId]);
  useEffect(() => {
    load().catch((e) => setMsg({ ok: false, text: e instanceof Error ? e.message : String(e) }));
  }, [load]);

  async function make(item: ExportCatalogItem) {
    setBusy(item.kind);
    setMsg(null);
    try {
      const row = await plans.createExport(projectId, item.kind, item.needs_plan || planId ? planId : null);
      await download(`/projects/${projectId}/exports/${row.id}/download`, row.filename);
      const v = row.validation as { worst_cosine?: number; not_measured?: string };
      setMsg({ ok: true, text: `${row.filename}: ${row.label_text}.${v.worst_cosine !== undefined ? ` Worst output cosine ${v.worst_cosine.toFixed(4)}. ${v.not_measured}` : ""}` });
      setHistory(await plans.exports(projectId));
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  }

  if (!catalog) return <div className="panel skeleton" aria-busy="true"><div className="sk-line w75" /></div>;
  return (
    <div className="exports">
      <section className="panel">
        <h2>Export</h2>
        <p className="hint">
          Every file says what it is: <span className="badge badge-measured">generated and validated</span> was produced here and checked by
          running it; <span className="badge badge-analytical">generated</span> comes from your stored analysis;{" "}
          <span className="badge badge-assumed">template</span> is instructions or scripts for you to adapt and run. No changed PCB, RTL or chip
          file is ever produced.
        </p>
        <label className="field inline">
          Design plan
          <select value={planId ?? ""} onChange={(e) => setPlanId(e.target.value ? Number(e.target.value) : null)}>
            <option value="">None (latest analysis only)</option>
            {saved.map((p) => <option key={p.id} value={p.id}>{p.name} v{p.version}</option>)}
          </select>
        </label>
        {msg && <p className={msg.ok ? "note-ok" : "error"} role={msg.ok ? "status" : "alert"}>{msg.text}</p>}
        <ul className="export-list">
          {catalog.map((c) => {
            const blocked = !c.available ? c.reason : c.needs_plan && !planId ? "Choose a saved design plan above (build one under Recommendations)." : null;
            return (
              <li key={c.kind}>
                <div>
                  <strong>{c.name}</strong> <span className={`badge ${LABEL_CLASS[c.label]}`}>{c.label_text}</span>
                  {blocked && <small className="block muted">{blocked}</small>}
                </div>
                <button disabled={!!blocked || !!busy || !canWrite} onClick={() => make(c)}>
                  {busy === c.kind ? (c.kind === "int8_model" ? "Quantising and validating…" : "Preparing…") : "Download"}
                </button>
              </li>
            );
          })}
        </ul>
      </section>
      <section className="panel">
        <h2>Export history</h2>
        {history.length === 0 ? (
          <p className="empty">Nothing exported yet.</p>
        ) : (
          <div className="table-wrap">
            <table className="tbl">
              <thead><tr><th>File</th><th>Kind</th><th className="num">Size</th><th>When</th><th>SHA-256</th><th><span className="sr-only">Download</span></th></tr></thead>
              <tbody>
                {history.map((h) => (
                  <tr key={h.id}>
                    <td>{h.filename}</td>
                    <td><span className={`badge ${LABEL_CLASS[h.label]}`}>{h.label_text}</span></td>
                    <td className="num">{size(h.size_bytes)}</td>
                    <td className="muted">{when(h.created_at)}</td>
                    <td className="muted mono-hash" title={h.sha256}>{h.sha256.slice(0, 12)}</td>
                    <td><button className="link" onClick={() => download(`/projects/${projectId}/exports/${h.id}/download`, h.filename)}>Download</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
