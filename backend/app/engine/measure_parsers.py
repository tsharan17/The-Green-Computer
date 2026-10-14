"""Parsers for the measurement formats engineers already have. Pure text in, numbers out.

Nothing here invents a value: a field the input does not contain stays None.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.schemas.measurement import MeasurementIn

_NUM = re.compile(r"-?\d+(?:\.\d+)?")


class MeasurementParseError(ValueError):
    """The text is not in the expected measurement format."""


@dataclass(frozen=True)
class PowerTrace:
    power_w_avg: float | None
    power_w_peak: float | None
    temperature_c_max: float | None
    samples: int


def parse_bench_json(text: str) -> list[MeasurementIn]:
    """Output of bench/run_benchmark.py (schema green-computer.bench/1) or a bare list."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise MeasurementParseError(f"not valid JSON: {e}") from e
    records = data.get("records") if isinstance(data, dict) else data
    if not isinstance(records, list) or not records:
        raise MeasurementParseError("expected a 'records' list of measurements")
    out = []
    for i, r in enumerate(records):
        try:
            out.append(MeasurementIn.model_validate(r))
        except ValueError as e:
            raise MeasurementParseError(f"record {i}: {e}") from e
    return out


def parse_nvidia_smi_csv(text: str) -> PowerTrace:
    """`nvidia-smi --query-gpu=power.draw,temperature.gpu,utilization.gpu --format=csv` output.

    Header optional; units such as "123.4 W" are tolerated. When utilisation is present, power is
    averaged over busy samples (>= 50%) so idle time before and after the run does not dilute it.
    """
    rows: list[tuple[float, float, float | None]] = []
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2:
            continue
        nums = [_NUM.search(p) for p in parts[:3]]
        if nums[0] is None or nums[1] is None:
            continue  # header or junk
        util = float(nums[2].group()) if len(nums) > 2 and nums[2] else None
        rows.append((float(nums[0].group()), float(nums[1].group()), util))
    if not rows:
        raise MeasurementParseError("no power/temperature rows found in nvidia-smi output")
    busy = [r for r in rows if r[2] is not None and r[2] >= 50.0] or rows
    return PowerTrace(
        power_w_avg=sum(r[0] for r in busy) / len(busy),
        power_w_peak=max(r[0] for r in busy),
        temperature_c_max=max(r[1] for r in rows),
        samples=len(busy),
    )


def parse_tegrastats(text: str) -> PowerTrace:
    """Jetson `tegrastats` lines. Power boundary is VDD_IN (whole module), in mW."""
    powers: list[float] = []
    temps: list[float] = []
    for line in text.splitlines():
        p = re.search(r"VDD_IN\s+(\d+)mW", line)
        if p:
            powers.append(int(p.group(1)) / 1000.0)
        temps.extend(float(t) for t in re.findall(r"@(-?\d+(?:\.\d+)?)C", line))
    if not powers:
        raise MeasurementParseError(
            "no VDD_IN power readings found; is this tegrastats output from a Jetson?"
        )
    return PowerTrace(
        power_w_avg=sum(powers) / len(powers),
        power_w_peak=max(powers),
        temperature_c_max=max(temps) if temps else None,
        samples=len(powers),
    )
