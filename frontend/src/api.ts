import type {
  HardwareDraft,
  RecipeOut,
  AgentEvent,
  AgentStatus,
  BenchmarkJob,
  BenchmarkStatus,
  CalibrationHistoryItem,
  Measurement,
  VerifyOut,
  EvaluationResult,
  HardwareProfile,
  ModelProfile,
  OptimisationResult,
  ProjectOut,
  ProjectSpec,
  UploadOut,
} from "./types";

const BASE = "/api/v1";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(BASE + path, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    // fetch only throws when the server cannot be reached at all.
    throw new Error(
      "Cannot reach the Green Computer server. It is probably not running (or was stopped). " +
        "Start it with scripts/dev.ps1, or run: cd backend && .venv/Scripts/python -m uvicorn app.main:app --port 8000, then reload this page.",
    );
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep statusText */
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  models: () => req<ModelProfile[]>("/models/library"),
  devices: () => req<HardwareProfile[]>("/hardware/library"),
  projects: () => req<ProjectOut[]>("/projects"),
  save: (id: number, spec: ProjectSpec) =>
    req<ProjectOut>(`/projects/${id}`, { method: "PUT", body: JSON.stringify(spec) }),
  create: (spec: ProjectSpec) =>
    req<ProjectOut>("/projects", { method: "POST", body: JSON.stringify(spec) }),
  uploadModel: async (file: File, opts: { dynamicDim?: number; baselineAccuracy?: number }) => {
    const q = new URLSearchParams({ filename: file.name, name: file.name.replace(/\.[^.]+$/, "") });
    if (opts.dynamicDim) q.set("dynamic_dim_default", String(opts.dynamicDim));
    if (opts.baselineAccuracy) q.set("baseline_accuracy", String(opts.baselineAccuracy));
    return req<UploadOut>(`/models/upload?${q}`, {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: await file.arrayBuffer(),
    });
  },
  manualModel: (body: { name: string; params_m: number; gflops: number; n_layers: number }) =>
    req<ModelProfile>("/models/manual", { method: "POST", body: JSON.stringify(body) }),
  verify: (deviceId?: string) => req<VerifyOut>(`/verify${deviceId ? `?device_id=${deviceId}` : ""}`),
  calibration: () =>
    req<{ active: Record<string, unknown>; history: CalibrationHistoryItem[] }>("/calibration"),
  benchmarkStatus: () => req<BenchmarkStatus>("/benchmarks/status"),
  addMeasurement: (body: Record<string, unknown>) =>
    req<{ created: number; measurements: Measurement[] }>("/measurements", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  importMeasurements: (format: string, text: string, params: Record<string, string>) =>
    req<{ created: number; skipped_duplicates: number }>(
      `/measurements/import?${new URLSearchParams({ format, ...params })}`,
      { method: "POST", headers: { "Content-Type": "text/plain" }, body: text },
    ),
  agentStatus: () => req<AgentStatus>("/agent/status"),
  benchmarks: () => req<BenchmarkJob[]>("/benchmarks"),
  refreshBenchmark: (id: number) => req<BenchmarkJob>(`/benchmarks/${id}`),
  submitBenchmark: (body: { device_id: string; model_id: string; precision: string; batches: number[] }) =>
    req<BenchmarkJob>("/benchmarks", { method: "POST", body: JSON.stringify(body) }),
  recipe: (id: number) => req<RecipeOut>(`/projects/${id}/recipe`),
  reportText: async (id: number, format: "md" | "html") => {
    const r = await fetch(`${BASE}/projects/${id}/report?format=${format}`);
    if (!r.ok) throw new Error(`${r.status}: ${(await r.json().catch(() => ({ detail: r.statusText }))).detail}`);
    return r.text();
  },
  drafts: () => req<HardwareDraft[]>("/hardware/drafts"),
  importHardware: (name: string) =>
    req<HardwareDraft>("/hardware/import", { method: "POST", body: JSON.stringify({ name }) }),
  manualHardware: (body: Record<string, unknown>) =>
    req<HardwareDraft>("/hardware/manual", { method: "POST", body: JSON.stringify(body) }),
  confirmDraft: (id: number, overrides: Record<string, unknown>) =>
    req<HardwareProfile>(`/hardware/drafts/${id}/confirm`, { method: "POST", body: JSON.stringify({ overrides }) }),
  rejectDraft: (id: number) => req<HardwareDraft>(`/hardware/drafts/${id}/reject`, { method: "POST" }),
  evaluate: (id: number) => req<EvaluationResult>(`/projects/${id}/evaluate`, { method: "POST" }),
  optimise: (id: number) => req<OptimisationResult>(`/projects/${id}/optimise`, { method: "POST" }),
};

/** POST a chat turn and read the server-sent events as they arrive. */
export async function agentChat(
  body: { project_id: number; message: string; history: { role: string; content: string }[] },
  onEvent: (e: AgentEvent) => void,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(BASE + "/agent/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new Error("Cannot reach the Green Computer server. Is it running? Start it with scripts/dev.ps1.");
  }
  if (!res.ok || !res.body) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* keep statusText */
    }
    throw new Error(detail);
  }
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i: number;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, i);
      buf = buf.slice(i + 2);
      for (const line of chunk.split("\n")) {
        if (line.startsWith("data: ")) onEvent(JSON.parse(line.slice(6)) as AgentEvent);
      }
    }
  }
}
