export type Provenance =
  | "measured"
  | "calibrated"
  | "analytical"
  | "surrogate"
  | "simulated"
  | "vendor_spec"
  | "assumed"
  | "extracted_unverified"
  | "synthetic_example";

export type Feasibility =
  | "verified_feasible"
  | "predicted_feasible"
  | "uncertain"
  | "infeasible"
  | "verified_infeasible";

export interface Metric {
  value: number;
  unit: string;
  low: number;
  high: number;
  provenance: Provenance;
}

export interface Config {
  precision: "fp32" | "fp16" | "int8";
  batch: number;
  power_mode_id: string;
  cooling_id: string;
}

export interface ConstraintCheck {
  name: string;
  sense: "<=" | ">=";
  limit: number;
  unit: string;
  pessimistic: number;
  optimistic: number;
  status: "pass" | "fail" | "uncertain";
  note: string;
}

export interface EvaluationResult {
  config: Config;
  metrics: Record<string, Metric>;
  bottleneck: "compute" | "memory" | "overhead" | "heat";
  throttle_risk: "low" | "medium" | "high";
  feasibility: Feasibility;
  checks: ConstraintCheck[];
  notes: string[];
  engine_version: string;
}

export interface Recommendation {
  title: string;
  changes: string[];
  summary: string;
  state: Feasibility;
  caveats: string[];
}

export interface OptimisationResult {
  baseline: EvaluationResult;
  best: EvaluationResult | null;
  top: EvaluationResult[];
  recommendation: Recommendation | null;
  evaluated: number;
  counts: Record<string, number>;
  message: string;
}

export interface Workload {
  fps: number;
  ambient_c: number;
  hours_per_day: number;
  price_per_kwh: number;
  grid_gco2_per_kwh: number;
}

export interface Constraints {
  max_power_w: number;
  min_accuracy: number;
  accuracy_mode: "relative" | "absolute";
  max_latency_ms: number | null;
  max_memory_gb: number | null;
  forbid_throttling: boolean;
}

export interface ProjectSpec {
  name: string;
  model_id: string;
  device_id: string;
  cooling_id: string | null;
  workload: Workload;
  constraints: Constraints;
}

export interface ProjectOut {
  id: number;
  spec: ProjectSpec;
}

export interface ModelProfile {
  id: string;
  name: string;
  task: string;
  accuracy_metric: string;
  baseline_accuracy: number;
}

export interface HardwareProfile {
  id: string;
  name: string;
  kind: string;
  role: string;
  cooling_options: { id: string; name: string }[];
  default_cooling: string;
}
