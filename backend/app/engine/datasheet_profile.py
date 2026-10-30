"""Hardware drafts from datasheets: the offline scan proposes values, a person confirms.

Nothing extracted is trusted. Every value is tied to the page it came from, implausible values are
dropped, anything not stated stays missing (never guessed), and the draft cannot be used in an
analysis until the user confirms it. Power and thermal constants a datasheet rarely gives are
derived from the power modes and are labelled "assumed".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.schemas.hardware import CoolingOption, HardwareProfile, PowerMode
from app.schemas.metrics import Provenance

RANGES = {
    "peak_tflops": (0.01, 5000.0),
    "mem_bw_gbs": (1.0, 8000.0),
    "mem_gb": (0.1, 2048.0),
    "cap_w": (0.5, 2000.0),
    "tdp_w": (0.5, 2000.0),
    "t_throttle_c": (40.0, 150.0),
}
REQUIRED = ("name", "peak_tflops", "mem_bw_gbs", "mem_gb")


class DatasheetError(ValueError):
    """The datasheet flow could not produce or confirm a profile."""


@dataclass
class Extraction:
    candidate: dict[str, Any]
    evidence: list[dict[str, Any]]
    missing: list[str]
    notes: str = ""
    dropped: list[str] = field(default_factory=list)


def _num(v: Any, lo: float, hi: float) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if lo <= x <= hi else None


def clean_extraction(raw: dict[str, Any], urls: set[str]) -> Extraction:
    """Validate what the model returned; keep only plausible, sourced values."""
    cand: dict[str, Any] = {}
    dropped: list[str] = []
    raw_sources = raw.get("sources")
    sources: dict[str, Any] = raw_sources if isinstance(raw_sources, dict) else {}

    def src(name: str) -> str | None:
        u = sources.get(name)
        return u if isinstance(u, str) and u in urls else None

    for k in ("name", "vendor"):
        if isinstance(raw.get(k), str) and raw[k].strip():
            cand[k] = raw[k].strip()[:120]
    if raw.get("kind") in ("edge_soc", "datacenter_gpu"):
        cand["kind"] = raw["kind"]
    peaks = {}
    raw_p = raw.get("peak_tflops")
    p: dict[str, Any] = raw_p if isinstance(raw_p, dict) else {}
    for prec in ("fp32", "fp16", "int8"):
        x = _num(p.get(prec), *RANGES["peak_tflops"])
        if x is not None:
            peaks[prec] = x
        elif p.get(prec) is not None:
            dropped.append(f"peak_tflops.{prec}")
    if peaks:
        cand["peak_tflops"] = peaks
    for k in ("mem_bw_gbs", "mem_gb", "tdp_w", "t_throttle_c"):
        x = _num(raw.get(k), *RANGES[k])
        if x is not None:
            cand[k] = x
        elif raw.get(k) is not None:
            dropped.append(k)
    modes = []
    for m in raw.get("power_modes") or []:
        if isinstance(m, dict) and isinstance(m.get("name"), str):
            cap = _num(m.get("cap_w"), *RANGES["cap_w"])
            if cap is not None:
                modes.append({"name": m["name"].strip()[:40], "cap_w": cap})
    if modes:
        cand["power_modes"] = modes

    evidence = []
    for k, v in cand.items():
        u = src(k) or (src("peak_tflops") if k == "peak_tflops" else None)
        evidence.append({"field": k, "value": v, "source_url": u})
    missing = [k for k in REQUIRED if k not in cand]
    return Extraction(
        candidate=cand,
        evidence=evidence,
        missing=missing,
        notes=str(raw.get("notes") or "")[:500],
        dropped=dropped,
    )


_TERA = {"G": 1e-3, "T": 1.0, "P": 1e3}
_PREC = {"int8": "int8", "fp16": "fp16", "bf16": "fp16", "fp32": "fp32", "tf32": "fp32"}
_BYTES_GB = {"gb": 1.0, "gib": 1.0, "mb": 1 / 1024, "mib": 1 / 1024, "kb": 1 / 1024**2, "kib": 1 / 1024**2}


def extraction_from_scan(name: str, cands: list[dict[str, Any]], filename: str) -> Extraction:
    """Turn the offline scan's candidates (datasheet_scan.candidates) into a draft.

    The first plausible value per field is proposed, with the page and line it came from. Unqualified
    TOPS are taken as INT8 and unqualified TFLOPS as FP32; the person confirming sees the line and
    corrects either. Program memory (Flash, eMMC) is not taken as working memory.
    """
    raw: dict[str, Any] = {"name": name, "peak_tflops": {}}
    where: dict[str, dict[str, Any]] = {}

    def take(key: str, value: Any, c: dict[str, Any]) -> None:
        if key not in where:
            where[key] = c
            raw[key] = value

    for c in cands:
        f, v, unit, q = c["field"], float(c["value"]), str(c["unit"]), (c.get("qualifier") or "")
        if f == "peak_compute":
            u = unit.upper()
            if q == "int4":
                continue
            prec = _PREC.get(q) or ("fp32" if "FL" in u else "int8")
            if prec not in raw["peak_tflops"]:
                raw["peak_tflops"][prec] = v * _TERA.get(u[0], 1.0)
                where.setdefault("peak_tflops", c)
        elif f == "mem_bw_gbs":
            take("mem_bw_gbs", v * (1000.0 if unit.lower().startswith("tb") else 1.0), c)
        elif f == "memory":
            size, kind = (unit.split(" ", 1) + [""])[:2]
            if kind.lower() not in ("flash", "emmc") and size.lower() in _BYTES_GB:
                take("mem_gb", v * _BYTES_GB[size.lower()], c)
        elif f == "power_w":
            take("tdp_w", v / 1000.0 if unit == "mW" else v, c)
        elif f == "temperature_c" and q.startswith(("junction", "tj", "throttl", "shutdown")):
            take("t_throttle_c", v, c)
    ex = clean_extraction(raw, set())
    for e in ex.evidence:
        hit = where.get(e["field"])
        if hit is not None:
            e.update(source_url=None, source=f"{filename}, page {hit['page']}", line=hit["line"])
    ex.notes = ("Values were found by pattern in the PDF text. Check each against the datasheet "
                "before confirming.")  # fmt: skip
    return ex


def build_profile(
    candidate: dict[str, Any],
    overrides: dict[str, Any] | None = None,
    device_id: str = "custom-hw",
) -> HardwareProfile:
    """Turn a confirmed candidate (plus the user's corrections) into a usable profile.

    Missing power/thermal constants are derived from the power modes and labelled assumed.
    """
    c = {**candidate, **(overrides or {})}
    missing = [k for k in REQUIRED if not c.get(k)]
    if missing:
        raise DatasheetError(f"required values are missing: {', '.join(missing)}")
    peaks = {k: float(v) for k, v in c["peak_tflops"].items() if v and float(v) > 0}
    if not peaks:
        raise DatasheetError("at least one of fp32/fp16/int8 peak throughput is required")

    raw_modes = c.get("power_modes") or []
    if not raw_modes:
        cap = c.get("tdp_w")
        if not cap:
            raise DatasheetError("give at least one power mode or a TDP in watts")
        raw_modes = [{"name": "Default", "cap_w": cap}]
    raw_modes = sorted(raw_modes, key=lambda m: m["cap_w"])
    pmax = float(raw_modes[-1]["cap_w"])
    gamma = 2.5
    modes = []
    for i, m in enumerate(raw_modes):
        ratio = float(m["cap_w"]) / pmax
        # Assumed: clocks scale so that dynamic power ~ f^gamma tracks the mode's cap.
        modes.append(
            PowerMode(
                id=re.sub(r"\W+", "_", str(m["name"])).strip("_") or f"mode{i}",
                name=str(m["name"]),
                cap_w=float(m["cap_w"]),
                freq_scale=max(0.15, min(1.0, ratio ** (1 / gamma))),
                mem_scale=max(0.4, min(1.0, 0.5 + 0.5 * ratio)),
            )
        )
    t_thr = float(c.get("t_throttle_c") or 90.0)
    # Assumed cooling: sized so a passive design reaches about 70% of the headroom at full power.
    r_passive = 0.7 * (t_thr - 25.0) / pmax
    cooling = [
        CoolingOption(id="passive", name="Passive heatsink (assumed)", r_th_k_per_w=r_passive,
                      fan_w=0.0, c_th_j_per_k=max(40.0, 8.0 * pmax)),
        CoolingOption(id="active", name="Heatsink with fan (assumed)", r_th_k_per_w=0.6 * r_passive,
                      fan_w=min(3.0, 0.05 * pmax), c_th_j_per_k=max(40.0, 8.0 * pmax)),
    ]  # fmt: skip
    src = Provenance.EXTRACTED_UNVERIFIED
    return HardwareProfile(
        id=device_id,
        name=str(c["name"]),
        vendor=str(c.get("vendor") or "unknown"),
        kind=c.get("kind") or "edge_soc",
        role="imported from a datasheet (not measured)",
        peak_tflops=peaks,
        mem_bw_gbs=float(c["mem_bw_gbs"]),
        mem_gb=float(c["mem_gb"]),
        idle_w=0.12 * pmax,
        dyn_w_max=0.55 * pmax,
        mem_w_max=0.20 * pmax,
        leak_w_25c=0.06 * pmax,
        gamma=gamma,
        t_throttle_c=t_thr,
        t_shutdown_c=t_thr + 15.0,
        power_modes=modes,
        cooling_options=cooling,
        default_cooling="passive",
        sources={
            "peak_tflops": src,
            "mem_bw_gbs": src,
            "mem_gb": src,
            "power_modes": src if candidate.get("power_modes") else Provenance.ASSUMED,
            "power_model": Provenance.ASSUMED,
            "thermal": Provenance.ASSUMED,
        },
        notes=(
            "Imported from a datasheet and confirmed by the user. Throughput, bandwidth and "
            "memory are extracted values; the power model and cooling are assumptions derived "
            "from the power modes. Not measured."
        ),
        verified=False,
        alternative_candidate=True,
    )
