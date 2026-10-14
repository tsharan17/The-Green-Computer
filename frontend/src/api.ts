import type {
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
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
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
  evaluate: (id: number) => req<EvaluationResult>(`/projects/${id}/evaluate`, { method: "POST" }),
  optimise: (id: number) => req<OptimisationResult>(`/projects/${id}/optimise`, { method: "POST" }),
};
