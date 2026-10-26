import { useEffect, useState } from "react";
import { workflow } from "../api";

const FIGS = [
  { name: "cooling-heatmap", title: "Thermal map: cooling option × ambient temperature",
    alt: "Heatmap of steady temperature for each cooling option across ambient temperatures, cells that throttle marked with a star" },
  { name: "mode-cooling-heatmap", title: "Power mode × cooling option",
    alt: "Heatmap of steady temperature for each power mode and cooling option at the project's ambient temperature" },
  { name: "cooling-surfaces", title: "3D: temperature over ambient and input rate, per cooling option",
    alt: "Three-dimensional surfaces of temperature over ambient temperature and input rate for each cooling option, with the throttle plane" },
] as const;

function Fig({ projectId, name, alt, version }: { projectId: number; name: string; alt: string; version: number }) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    setUrl(null);
    setError(null);
    workflow.figure(projectId, name).then((u) => live && setUrl(u)).catch((e) => live && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      live = false;
    };
  }, [projectId, name, version]);
  if (error) return <p className="note" role="status">This figure is not available for this setup: {error}.</p>;
  if (!url) return <div className="mpl-fig mpl-loading" aria-busy="true">Drawing the figure…</div>;
  return (
    <figure className="mpl">
      <img className="mpl-fig" src={url} alt={alt} />
      <a className="link mpl-save" href={url} download={`${name}.png`}>Save as PNG</a>
    </figure>
  );
}

/** Seaborn/matplotlib cooling figures: every cell is one engine evaluation of today's setup. */
export default function CoolingFigures({ projectId, version }: { projectId: number; version: number }) {
  const [open, setOpen] = useState<string>(FIGS[0].name);
  const f = FIGS.find((x) => x.name === open)!;
  return (
    <section className="panel" aria-labelledby="cf-h">
      <h2 id="cf-h">Cooling comparison maps</h2>
      <p className="muted">
        Each cell is one analytical engine evaluation of today's setup (steady state, lumped thermal model). A star marks a cell where the
        chip throttles to hold its limit. This is not a board-level or CFD thermal simulation.
      </p>
      <div className="seg" role="tablist" aria-label="Cooling figure">
        {FIGS.map((x) => (
          <button key={x.name} role="tab" aria-selected={open === x.name} className={open === x.name ? "on" : ""} onClick={() => setOpen(x.name)}>
            {x.title.split(":")[0]}
          </button>
        ))}
      </div>
      <h3>{f.title}</h3>
      <Fig projectId={projectId} name={f.name} alt={f.alt} version={version} />
    </section>
  );
}
