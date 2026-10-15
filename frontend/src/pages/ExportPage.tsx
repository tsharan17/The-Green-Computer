import { useEffect, useState } from "react";
import { api } from "../api";
import type { RecipeOut } from "../types";

function download(name: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export default function ExportPage({ projectId }: { projectId: number }) {
  const [recipe, setRecipe] = useState<RecipeOut | null>(null);
  const [html, setHtml] = useState<string | null>(null);
  const [file, setFile] = useState<string>("README.md");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [r, h] = await Promise.all([api.recipe(projectId), api.reportText(projectId, "html")]);
        setRecipe(r);
        setHtml(h);
        setErr(null);
      } catch (e) {
        setErr(String(e));
      }
    })();
  }, [projectId]);

  if (err) return <div className="panel"><p className="error">{err}</p></div>;
  if (!recipe || !html) return <div className="panel"><p>Preparing your files…</p></div>;
  const names = Object.keys(recipe.files);
  const cur = recipe.files[file] ?? recipe.files[names[0]];

  return (
    <div className="export-page">
      <section className="panel">
        <div className="row">
          <h2>Your report</h2>
          <div className="cta-row">
            <button onClick={async () => download("green-computer-report.md", await api.reportText(projectId, "md"), "text/markdown")}>
              Download (Markdown)
            </button>
            <button onClick={() => download("green-computer-report.html", html, "text/html")}>Download (web page)</button>
            <button onClick={() => { const w = window.open(); if (w) { w.document.write(html); w.document.close(); w.print(); } }}>
              Print / save as PDF
            </button>
          </div>
        </div>
        <p className="hint">A shareable summary of the question, the verdict, the fixes and recommendations, how sure we are, and the limits.</p>
        <iframe className="report-frame" title="Report preview" srcDoc={html} sandbox="" />
      </section>

      <section className="panel">
        <div className="row">
          <h2>Your recipe: ready-to-use files</h2>
          <a className="button" href={`/api/v1/projects/${projectId}/recipe.zip`}>
            Download all (.zip)
          </a>
        </div>
        {recipe.warnings.map((w) => (
          <p key={w} className="note">{w}</p>
        ))}
        <div className="recipe">
          <ul className="file-list">
            {names.map((n) => (
              <li key={n}>
                <button className={n === file ? "on" : ""} onClick={() => setFile(n)}>
                  <strong>{n}</strong>
                  <span>{recipe.files[n].description}</span>
                </button>
              </li>
            ))}
          </ul>
          <div className="file-view">
            <div className="row">
              <strong>{file}</strong>
              <button onClick={() => navigator.clipboard?.writeText(cur.content)}>Copy</button>
            </div>
            <pre>{cur.content}</pre>
          </div>
        </div>
      </section>
    </div>
  );
}
