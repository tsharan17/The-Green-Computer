import type {
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
  evaluate: (id: number) => req<EvaluationResult>(`/projects/${id}/evaluate`, { method: "POST" }),
  optimise: (id: number) => req<OptimisationResult>(`/projects/${id}/optimise`, { method: "POST" }),
};
