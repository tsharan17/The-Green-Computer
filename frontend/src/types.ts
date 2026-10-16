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
  resolution_scale: number;
  clock_trim: number;
  sparsity: number;
}

export interface SolverInfo {
  converged: boolean;
  iterations: number;
  throttled: boolean;
  clock_factor: number;
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
  solver: SolverInfo;
  time_to_throttle_s: number | null;
  thermal_trace: [number, number][];
  engine_version: string;
}

export interface Recommendation {
  title: string;
  changes: string[];
  summary: string;
  state: Feasibility;
  caveats: string[];
}

export interface Point {
  config: Config;
  state: Feasibility;
  energy_mj: number;
  latency_ms: number;
  accuracy: number;
  power_w: number;
  memory_gb: number;
  temperature_c: number;
  pareto: boolean;
  best: boolean;
}

export interface CoDesign {
  baseline: EvaluationResult;
  software_only: EvaluationResult | null;
  hardware_only: EvaluationResult | null;
  combined: EvaluationResult | null;
  interaction_factor: number | null;
  interpretation: string;
}

export type Tier = "model" | "software" | "configure" | "select" | "design";

export interface VerdictSide {
  state: Feasibility;
  ok: boolean;
  headline: string;
  problems: string[];
  power_w: number;
  latency_ms: number;
  temperature_c: number;
  capacity_fps: number;
  energy_mj: number;
  config: Config;
}

export interface Verdict {
  baseline: VerdictSide;
  improved: VerdictSide | null;
  savings: { power_percent: number; energy_percent: number; cost_per_year: number; carbon_kg_per_year: number } | null;
  fps_required: number;
  summary: string;
}

export interface RepairPlan {
  changes: string[];
  effort_score: number;
  feasibility: Feasibility;
  fixes: string[];
  config: Config;
  energy_saving_percent: number;
  note: string;
}

export interface Repair {
  needed: boolean;
  plans: RepairPlan[];
  binding_constraints: string[];
  message: string;
}

export interface Alternative {
  kind: "device" | "model";
  id: string;
  name: string;
  feasibility: Feasibility;
  config: Config;
  power_w: number;
  energy_mj: number;
  latency_ms: number;
  temperature_c: number;
  capacity_fps: number;
  energy_saving_percent: number | null;
  accuracy_retention: number | null;
  lighter: boolean | null;
  compared_with: string;
  problem: string | null;
  note: string;
}

export interface WhatIf {
  id: string;
  title: string;
  change: string;
  parameter: string;
  factor: number;
  latency_change_percent: number;
  energy_change_percent: number;
  power_change_percent: number;
  temperature_change_c: number;
  elasticity_latency: number;
  elasticity_energy: number;
  makes_baseline_feasible: boolean;
  verify_with: string;
}

export interface Advice {
  id: string;
  tier: Tier;
  title: string;
  action: string;
  gain: string;
  why: string;
  effect: Record<string, number | null>;
  tradeoffs: string[];
  confidence: "high" | "medium" | "low";
  confidence_reason: string;
  effort: "low" | "medium" | "high";
  validate_steps: string[];
  in_recommended: boolean;
  fixes: string[];
}

export interface OptimisationResult {
  baseline: EvaluationResult;
  best: EvaluationResult | null;
  top: EvaluationResult[];
  recommendation: Recommendation | null;
  codesign: CoDesign;
  points: Point[];
  evaluated: number;
  counts: Record<string, number>;
  search_seconds: number;
  message: string;
  verdict: Verdict | null;
  repair: Repair | null;
  advice: Advice[];
  alternatives: Alternative[];
  whatifs: WhatIf[];
  limiting_factor: string | null;
}

export interface Measurement {
  id: number;
  device_id: string;
  model_id: string;
  precision: "fp32" | "fp16" | "int8";
  batch: number;
  source: string;
  hardware_label: string;
  latency_ms_mean: number | null;
  throughput_fps: number | null;
  power_w_avg: number | null;
  temperature_c_max: number | null;
  accuracy_retention: number | null;
  notes: string;
}

export interface VerifyRow {
  measurement: Measurement;
  predicted_ms: number;
  predicted_cal_ms: number | null;
  error_before: number | null;
  error_after: number | null;
  inside_band: boolean | null;
}

export interface VerifySummary {
  device_id: string;
  precision: string;
  n: number;
  mape_before: number | null;
  mape_after: number | null;
  coverage: number | null;
  calibration_version: number | null;
  calibration_active: boolean;
  note: string;
}

export interface VerifyOut {
  rows: VerifyRow[];
  summaries: VerifySummary[];
}

export interface CalibrationHistoryItem {
  device_id: string;
  precision: string;
  version: number;
  accepted: boolean;
  created_at: string;
  latency: { n: number; error_before: number | null; error_after: number | null; accepted: boolean; reason: string };
  power: { n: number; accepted: boolean; reason: string };
}

export interface BenchmarkStatus {
  jobs_configured: boolean;
  detail: string;
  replay_available: boolean;
  cli_found?: boolean;
  import_formats: string[];
}

export interface Workload {
  fps: number;
  ambient_c: number;
  hours_per_day: number;
  price_per_kwh: number;
  grid_gco2_per_kwh: number;
  streaming: boolean;
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
  baseline: Config | null;
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
  input_desc: string;
  params_m: number;
  gflops: number;
  n_layers: number;
  accuracy_metric: string;
  baseline_accuracy: number;
  fidelity: "library" | "graph" | "manual";
  resolution_scalable: boolean;
  notes: string;
}

export interface UploadOut {
  profile: ModelProfile;
  warnings: string[];
}

export interface HardwareProfile {
  id: string;
  name: string;
  vendor?: string;
  kind: string;
  role: string;
  mem_gb?: number;
  idle_w: number;
  mem_bw_gbs?: number;
  weights_mem_gb?: number | null;
  notes?: string;
  sources?: Record<string, string>;
  extras?: Record<string, number | string>;
  cooling_options: { id: string; name: string }[];
  power_modes: { id: string; name: string; cap_w: number }[];
  peak_tflops: Record<string, number>;
  default_cooling: string;
}

export interface AgentStatus {
  configured: boolean;
  base_url: string;
  detail: string | null;
  models?: Record<string, string | null>;
  available_models?: number;
}

export type AgentEvent =
  | { type: "status"; text: string }
  | { type: "tool_call"; name: string; arguments: Record<string, unknown> }
  | { type: "tool_result"; name: string; ok: boolean; summary: string }
  | { type: "guardrail"; action: "rewrite" | "redacted"; figures: string[] }
  | { type: "message"; text: string; guardrail_ok: boolean }
  | { type: "error"; text: string }
  | { type: "done" };

export interface BenchmarkJob {
  id: number;
  job_name: string;
  job_id: string;
  device_id: string;
  model_id: string;
  precision: string;
  batches: number[];
  state: string;
  ingested: boolean;
  measurement_ids: number[];
  error: string | null;
  created_at: string;
}

export interface HardwareDraft {
  id: number;
  query: string;
  status: "draft" | "confirmed" | "rejected";
  candidate: {
    name?: string;
    vendor?: string;
    peak_tflops?: Record<string, number>;
    mem_bw_gbs?: number;
    mem_gb?: number;
    power_modes?: { name: string; cap_w: number }[];
    tdp_w?: number;
    t_throttle_c?: number;
  };
  evidence: { field: string; value: unknown; source_url: string | null }[];
  missing: string[];
  device_id: string | null;
  needs_confirmation: boolean;
  notes?: string;
  dropped_implausible?: string[];
}

export interface RecipeOut {
  files: Record<string, { description: string; content: string }>;
  warnings: string[];
}

export interface LayerRow {
  index: number;
  name: string;
  op: string;
  time_ms: number;
  share: number;
  bound: "compute" | "memory";
  flops_share: number;
  weights_kb: number;
  quant_risk: number;
}

export interface LayerProfile {
  has_graph: boolean;
  graph_source?: string;
  note: string;
  total_ms: number;
  overhead_ms?: number;
  n_layers?: number;
  layers: LayerRow[];
  top?: LayerRow[];
  by_op: { op: string; time_ms: number; count: number; share: number }[];
  fragile?: LayerRow[];
  hints?: string[];
}

export type HardwareStyle = "generic" | "mcu" | "fpga" | "accelerator";

export interface ReportParse {
  tool: string;
  fields?: Record<string, number>;
  found?: Record<string, unknown>;
  note?: string;
  power_w_avg?: number;
  power_w_active?: number;
  power_w_idle?: number;
  power_w_peak?: number;
  samples?: number;
}
