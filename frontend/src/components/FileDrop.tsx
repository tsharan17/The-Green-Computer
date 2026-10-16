import { useRef, useState } from "react";
import { api } from "../api";
import type { HardwareProfile, ModelProfile, ProjectSpec } from "../types";

export interface DropHandlers {
  addModel: (m: ModelProfile) => void;
  applyProject: (spec: ProjectSpec, hardwareCreated: boolean) => void;
  hardwareReady: (d: HardwareProfile) => void;
  prefill: (fields: Record<string, string>, source: string) => void;
  draftsChanged: () => void;
}

interface Item {
  id: number;
  name: string;
  status: "working" | "ok" | "error";
  role: string;
  message: string;
}

const ROLES = [
  ["Software", "AI model (.onnx), project file (greencomputer.yaml)"],
  ["Hardware", "hardware description (.yaml/.json), datasheet (.pdf)"],
  ["Measurements", "Vivado / ST Edge AI / Vela reports (.rpt .txt), power logs (.csv)"],
];

let nextId = 1;

export default function FileDrop({ handlers, disabled }: { handlers: DropHandlers; disabled?: boolean }) {
  const [items, setItems] = useState<Item[]>([]);
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const patch = (id: number, p: Partial<Item>) => setItems((xs) => xs.map((x) => (x.id === id ? { ...x, ...p } : x)));

  async function handle(file: File) {
    const id = nextId++;
    setItems((xs) => [{ id, name: file.name, status: "working", role: "Reading…", message: "" }, ...xs]);
    const lower = file.name.toLowerCase();
    try {
      if (lower.endsWith(".onnx")) {
        let out;
        let note = "";
        try {
          out = await api.uploadModel(file, {});
        } catch (e) {
          if (!/dynamic dim/i.test(String(e))) throw e;
          out = await api.uploadModel(file, { dynamicDim: 224 });
          note = " Dynamic dimensions were set to 224 (change it under Software if that is wrong).";
        }
        handlers.addModel(out.profile);
        const p = out.profile;
        patch(id, {
          status: "ok", role: "Software · AI model",
          message: `${p.n_layers} layers, ${p.params_m.toFixed(2)} M parameters, ${p.gflops.toFixed(2)} GFLOPs. Selected.${note}`,
        });
        return;
      }
      const r = await api.inspectFile(file);
      switch (r.kind) {
        case "project": {
          handlers.applyProject(r.spec as ProjectSpec, !!r.hardware_created);
          patch(id, { status: "ok", role: "Software + hardware · project file", message: `Loaded "${(r.spec as ProjectSpec).name}". ${(r.warnings as string[] | undefined)?.join(" ") ?? ""}` });
          break;
        }
        case "hardware_spec": {
          const d = await api.customCreate(r.spec as Record<string, unknown>);
          handlers.hardwareReady(d);
          patch(id, { status: "ok", role: "Hardware · description", message: `Created "${d.name}" and selected it. Values you did not give are assumptions (see Hardware).` });
          break;
        }
        case "hardware_profile": {
          const d = await api.registerProfile(r.profile as unknown as HardwareProfile);
          handlers.hardwareReady(d);
          patch(id, { status: "ok", role: "Hardware · full profile", message: `Registered "${d.name}" and selected it.` });
          break;
        }
        case "datasheet": {
          handlers.draftsChanged();
          patch(id, { status: "ok", role: "Hardware · datasheet", message: "Specs read. Review and confirm the values under Hardware before they are used." });
          break;
        }
        case "report": {
          const f = Object.fromEntries(Object.entries((r.fields as Record<string, number>) ?? {}).map(([k, v]) => [k, String(v)]));
          handlers.prefill(f, String(r.tool));
          patch(id, { status: "ok", role: `Hardware · ${String(r.tool).replace("_", " ")} report`, message: `Read ${Object.keys(f).length || "the"} values into "Describe your own hardware". ${String(r.note ?? "")}` });
          break;
        }
        case "power": {
          const f: Record<string, string> = {};
          const active = r.power_w_active as number;
          const idle = r.power_w_idle as number;
          f.__power_active_w = String(active);
          f.__power_idle_w = String(idle);
          handlers.prefill(f, "power_csv");
          patch(id, { status: "ok", role: "Measurement · power log", message: `${r.samples} samples: active ${active.toFixed(4)} W, idle ${idle.toFixed(5)} W, peak ${(r.power_w_peak as number).toFixed(4)} W. Offered to "Describe your own hardware".` });
          break;
        }
        default:
          patch(id, { status: "error", role: "Unknown", message: "Not recognised." });
      }
    } catch (e) {
      patch(id, { status: "error", role: "Could not use this file", message: String(e instanceof Error ? e.message : e).replace(/^\d+:\s*/, "") });
    }
  }

  function take(files: FileList | File[] | null) {
    if (!files) return;
    Array.from(files).forEach((f) => void handle(f));
  }

  return (
    <section className={`dropzone ${over ? "over" : ""}`} aria-label="Upload your files"
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); if (!disabled) take(e.dataTransfer.files); }}>
      <div className="drop-main">
        <div className="drop-icon" aria-hidden>⇪</div>
        <div>
          <h2>Drop your files here</h2>
          <p className="muted">We work out what each one is and fill in the setup for you.</p>
        </div>
        <button className="primary" disabled={disabled} onClick={() => input.current?.click()}>Choose files</button>
        <input ref={input} type="file" multiple hidden accept=".onnx,.yaml,.yml,.json,.pdf,.csv,.rpt,.txt,.log" onChange={(e) => { take(e.target.files); e.target.value = ""; }} />
      </div>
      <ul className="drop-roles">
        {ROLES.map(([t, d]) => (
          <li key={t}><b>{t}</b><span>{d}</span></li>
        ))}
      </ul>
      {items.length > 0 && (
        <ul className="drop-list" aria-live="polite">
          {items.map((i) => (
            <li key={i.id} className={`drop-item ${i.status}`}>
              <i aria-hidden>{i.status === "working" ? "…" : i.status === "ok" ? "✓" : "!"}</i>
              <div>
                <strong>{i.name}</strong> <span className="muted">· {i.role}</span>
                {i.message && <p>{i.message}</p>}
              </div>
              <button className="link" onClick={() => setItems((xs) => xs.filter((x) => x.id !== i.id))} aria-label={`Dismiss ${i.name}`}>×</button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
