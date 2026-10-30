"""Execution backends: where a model can actually be run (as opposed to predicted).

Provider-neutral interface. The local ONNX Runtime CPU backend is the required one; CUDA and
TensorRT appear only when ONNX Runtime reports those providers AND the operator enables them;
the customer-device backend runs on a paired device through the device agent. On a shared server
(GC_HOSTED or GC_PUBLIC_DEMO) the local backends are off. Nothing here is ever required for the
analytical product to work.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

Status = Literal["available", "needs_credential", "unavailable", "disabled", "planned"]


def _flag(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in ("1", "true", "yes", "on")


@dataclass
class BackendInfo:
    id: str
    name: str
    location: Literal["local", "remote"]
    status: Status
    detail: str
    enable: str = ""
    measures: list[str] = field(default_factory=list)
    providers: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class ExecutionBackend(Protocol):
    id: str

    def info(self) -> BackendInfo: ...


def _ort() -> tuple[Any | None, str]:
    try:
        import onnxruntime as ort

        return ort, ort.__version__
    except Exception as e:  # noqa: BLE001 - missing or broken install
        return None, str(e)


def _server_runs_off(backend_id: str, name: str) -> BackendInfo | None:
    from app.security import SERVER_RUNS_OFF, shared_server

    if not shared_server():
        return None
    return BackendInfo(backend_id, name, "local", "disabled", SERVER_RUNS_OFF.format(feature="Running models"))


class LocalCpuBackend:
    id = "local-cpu"
    ort_providers = ["CPUExecutionProvider"]

    def info(self) -> BackendInfo:
        if off := _server_runs_off(self.id, "This server's CPU (ONNX Runtime)"):
            return off
        ort, ver = _ort()
        if ort is None:
            return BackendInfo(self.id, "This server's CPU (ONNX Runtime)", "local", "unavailable",
                               f"onnxruntime is not installed or failed to load: {ver}",
                               "pip install onnxruntime")  # fmt: skip
        return BackendInfo(
            self.id, "This server's CPU (ONNX Runtime)", "local", "available",
            f"ONNX Runtime {ver}. Runs uploaded ONNX models on synthetic inputs in an isolated process "
            "with a time limit and records latency and per-operator timings.",
            measures=["latency (mean, p50, p95, p99)", "throughput", "per-operator time (ORT profiler)",
                      "peak process memory"],
            providers=self.ort_providers,
        )  # fmt: skip


class LocalCudaBackend:
    id = "local-cuda"
    ort_providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    _need = "CUDAExecutionProvider"
    _name = "Local NVIDIA GPU (ONNX Runtime CUDA)"
    _flag_name = "GC_ENABLE_CUDA"

    def info(self) -> BackendInfo:
        if off := _server_runs_off(self.id, self._name):
            return off
        ort, ver = _ort()
        have = ort.get_available_providers() if ort is not None else []
        if self._need not in have:
            return BackendInfo(self.id, self._name, "local", "unavailable",
                               f"ONNX Runtime here does not provide {self._need} (installed: "
                               f"{', '.join(have) or 'none'}).",
                               "Install onnxruntime-gpu with a matching CUDA/cuDNN on a machine with an "
                               f"NVIDIA GPU, then set {self._flag_name}=1.")  # fmt: skip
        if not _flag(self._flag_name):
            return BackendInfo(self.id, self._name, "local", "disabled",
                               f"{self._need} is installed but turned off.",
                               f"Set {self._flag_name}=1 to allow runs on it.", providers=have)  # fmt: skip
        return BackendInfo(self.id, self._name, "local", "available", f"{self._need} via ONNX Runtime {ver}.",
                           measures=["latency", "throughput", "per-operator time"],
                           providers=self.ort_providers)  # fmt: skip


class LocalTensorRtBackend(LocalCudaBackend):
    id = "local-tensorrt"
    ort_providers = ["TensorrtExecutionProvider", "CUDAExecutionProvider", "CPUExecutionProvider"]
    _need = "TensorrtExecutionProvider"
    _name = "Local NVIDIA GPU (TensorRT via ONNX Runtime)"
    _flag_name = "GC_ENABLE_TENSORRT"


class RemoteDeviceBackend:
    id = "remote-device"

    def info(self) -> BackendInfo:
        return BackendInfo(self.id, "Your own device (agent)", "remote", "available",
                           "Pair the device agent (agent/gc_agent.py) under Verify → Run on a device; it runs "
                           "signed requests for approved ONNX files with ONNX Runtime (CPU) and returns "
                           "quality-checked timings.",
                           "See docs/remote-agent.md.",
                           measures=["latency", "throughput", "temperature (Linux thermal zones, when readable)"])  # fmt: skip


BACKENDS: list[ExecutionBackend] = [
    LocalCpuBackend(), LocalCudaBackend(), LocalTensorRtBackend(), RemoteDeviceBackend(),
]


def backend_infos() -> list[BackendInfo]:
    return [b.info() for b in BACKENDS]


def get_backend(backend_id: str) -> ExecutionBackend | None:
    return next((b for b in BACKENDS if b.id == backend_id), None)

