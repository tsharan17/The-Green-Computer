"""Which files the platform reads, per hardware category, and what each one gives the analysis.

The single source of truth for upload guidance in the UI and for routing uploads. A format is
`supported` only when a real parser exists in this codebase; everything else is `planned` or
`unsupported` with the exact alternative that works today. Nothing here pretends to analyse
schematics, PCBs, RTL, netlists, assembly or firmware beyond what the parsers below actually do.
"""

from __future__ import annotations

from typing import Literal, TypedDict

Status = Literal["supported", "planned", "unsupported"]


class FileFormat(TypedDict):
    id: str
    name: str
    extensions: list[str]
    status: Status
    gives: str  # what the analysis gets from it (supported) or why not (others)
    required: str  # exact format we need / the alternative that works today


MODEL_FORMATS: list[FileFormat] = [
    {"id": "onnx", "name": "ONNX model", "extensions": [".onnx"], "status": "supported",
     "gives": "Per-operator graph: shapes, FLOPs, weights and activation traffic; operator-level "
              "execution trace; local execution with ONNX Runtime; INT8 conversion.",
     "required": "ONNX opset 7 or later, weights embedded (no external data), under 100 MB. "
                 "Export with torch.onnx.export(model, example_input, 'model.onnx') or tf2onnx."},
    {"id": "pytorch", "name": "PyTorch checkpoint", "extensions": [".pt", ".pth", ".ckpt"],
     "status": "unsupported",
     "gives": "Refused on purpose: these files are pickles and can run code when loaded.",
     "required": "Export to ONNX: torch.onnx.export(model, example_input, 'model.onnx', opset_version=17)."},
    {"id": "tflite", "name": "TensorFlow Lite", "extensions": [".tflite"], "status": "planned",
     "gives": "Not parsed yet.",
     "required": "Convert with tf2onnx (python -m tf2onnx.convert --tflite model.tflite --output model.onnx), "
                 "or enter the model's parameters and GFLOPs by hand."},
    {"id": "tensorflow", "name": "TensorFlow SavedModel / Keras", "extensions": [".pb", ".h5", ".keras"],
     "status": "planned", "gives": "Not parsed yet.",
     "required": "Convert with tf2onnx (python -m tf2onnx.convert --saved-model DIR --output model.onnx)."},
    {"id": "safetensors", "name": "safetensors weights", "extensions": [".safetensors"],
     "status": "planned", "gives": "Weights without the graph cannot be costed per operator.",
     "required": "Upload the ONNX export of the full model, or enter parameters and GFLOPs by hand."},
]

_PROFILE: FileFormat = {
    "id": "device_profile", "name": "Device profile (YAML/JSON)", "extensions": [".yaml", ".yml", ".json"],
    "status": "supported",
    "gives": "Compute per precision, memory size and bandwidth, idle/dynamic/memory/leakage power, "
             "power modes, cooling options, throttle limits: everything the engine models.",
    "required": "The device profile template (download it below the table). "
                "Units: TFLOPS/TOPS, GB/s, GB, W, K/W, °C; values may carry units as text, e.g. '68 GB/s'.",
}
_DESCRIPTION: FileFormat = {
    "id": "hardware_description", "name": "Hardware description (YAML/JSON)",
    "extensions": [".yaml", ".yml", ".json"], "status": "supported",
    "gives": "A short description (style + headline numbers) from which a full profile is derived.",
    "required": "Keys: name, style (generic | accelerator | mcu | fpga) and the numbers that style needs "
                "(see the hardware form for the list).",
}
_POWER_LOG: FileFormat = {
    "id": "power_csv", "name": "Power log (CSV)", "extensions": [".csv"], "status": "supported",
    "gives": "Average and peak power from a power meter (Joulescope, Otii, Nordic PPK2, any "
             "time,current/power CSV); imported as a measurement, never as a prediction.",
    "required": "A header row with a time column and a power (W/mW) or current (A/mA/uA) column; "
                "give the supply voltage when only current is logged.",
}
_TELEMETRY: FileFormat = {
    "id": "telemetry", "name": "Device telemetry log", "extensions": [".csv", ".log", ".txt"],
    "status": "supported",
    "gives": "Power and temperature from nvidia-smi CSV or Jetson tegrastats logs (measured).",
    "required": "nvidia-smi --query-gpu=power.draw,temperature.gpu --format=csv -lms 100, or "
                "tegrastats --interval 100.",
}
_DATASHEET: FileFormat = {
    "id": "datasheet_pdf", "name": "Datasheet (PDF)", "extensions": [".pdf"], "status": "supported",
    "gives": "Candidate values found in the text (compute, memory, power, temperature limits), each "
             "shown with the line it came from for you to confirm. Scanned PDFs are read with OCR "
             "when it is installed on the server; otherwise they go to manual review.",
    "required": "A text PDF works best. Nothing from a datasheet is used until you confirm it.",
}
_ELF: FileFormat = {
    "id": "firmware_elf", "name": "Firmware image (ELF)", "extensions": [".elf", ".axf", ".out"],
    "status": "supported",
    "gives": "Flash and RAM footprint from the section table (.text, .rodata, .data, .bss), "
             "checked against the device's flash and SRAM. Instructions are not analysed.",
    "required": "The linked ELF from your build (e.g. build/firmware.elf), not a .hex or .bin.",
}


def _planned(fid: str, name: str, exts: list[str], required: str) -> FileFormat:
    return {"id": fid, "name": name, "extensions": exts, "status": "planned",
            "gives": "No parser for this format exists in the platform yet, so it is not analysed.",
            "required": required}  # fmt: skip


SCHEMATIC = _planned("schematic", "Schematic", [".sch", ".kicad_sch", ".schdoc", ".dsn"],
                     "Today: describe the power rails and regulators in the device profile "
                     "(idle_w, regulator_efficiency) or upload a power log measured on the board.")  # fmt: skip
PCB = _planned("pcb", "PCB layout / Gerber", [".kicad_pcb", ".brd", ".pcbdoc", ".gbr", ".gtl", ".gbl"],
               "Today: give the cooling as thermal resistance (K/W) in the profile's cooling options; "
               "a board thermal simulation export (e.g. a CSV of junction-to-ambient vs airflow) can be "
               "entered as cooling options.")  # fmt: skip
RTL = _planned("rtl", "RTL source", [".v", ".sv", ".vhd", ".vhdl"],
               "Today: upload the synthesis/implementation report instead (Vivado report_utilization "
               "and report_power .rpt) — those numbers are parsed.")  # fmt: skip
NETLIST = _planned("netlist", "Netlist", [".edf", ".edif", ".net", ".vqm"],
                   "Today: upload the Vivado utilisation and power reports (.rpt).")  # fmt: skip
ASSEMBLY = _planned("assembly", "Assembly source", [".s", ".asm"],
                    "Today: upload the linked firmware ELF for flash/RAM footprint, and measure "
                    "latency on the device (import a CSV/JSON measurement).")  # fmt: skip
FIRMWARE_RAW = _planned("firmware_raw", "Raw firmware image", [".hex", ".bin", ".uf2", ".srec"],
                        "Upload the linked .elf instead: raw images carry no section table.")  # fmt: skip

VENDOR_REPORTS: list[FileFormat] = [
    {"id": "vivado", "name": "Xilinx/AMD Vivado reports", "extensions": [".rpt", ".txt"], "status": "supported",
     "gives": "LUT/FF/BRAM/URAM/DSP utilisation and on-chip power (static and dynamic) as profile facts.",
     "required": "report_utilization -file util.rpt and report_power -file power.rpt."},
    {"id": "stedgeai", "name": "ST Edge AI / X-CUBE-AI analyze report", "extensions": [".txt", ".log"],
     "status": "supported", "gives": "MACC count, weights (flash) and activations (RAM) for the model on STM32.",
     "required": "stedgeai analyze --model model.tflite --target stm32 (the printed report saved to a file)."},
    {"id": "vela", "name": "Arm Vela summary (Ethos-U)", "extensions": [".txt", ".csv"], "status": "supported",
     "gives": "SRAM/flash use, cycles and inferences/s estimated by Vela.",
     "required": "vela model.tflite --output-format tflite (the summary printed to the console)."},
]

CATEGORIES: list[dict] = [
    {"id": "board_soc", "name": "Board / SoC", "kinds": ["edge_soc", "sbc", "laptop_soc", "datacenter_gpu"],
     "examples": "Jetson Orin, Raspberry Pi 5, Snapdragon, Apple M-series, NVIDIA L4",
     "formats": [_PROFILE, _DESCRIPTION, _DATASHEET, _POWER_LOG, _TELEMETRY, SCHEMATIC, PCB]},
    {"id": "mcu", "name": "Microcontroller", "kinds": ["mcu"],
     "examples": "STM32H7/N6, nRF52840, ESP32-S3",
     "formats": [_PROFILE, _DESCRIPTION, _ELF, VENDOR_REPORTS[1], VENDOR_REPORTS[2], _POWER_LOG, _DATASHEET,
                 ASSEMBLY, FIRMWARE_RAW, SCHEMATIC]},
    {"id": "fpga", "name": "FPGA", "kinds": ["fpga"], "examples": "Kria KV260, Zynq UltraScale+",
     "formats": [_PROFILE, _DESCRIPTION, VENDOR_REPORTS[0], _POWER_LOG, _DATASHEET, RTL, NETLIST]},
    {"id": "accelerator", "name": "AI accelerator", "kinds": ["accelerator"],
     "examples": "Hailo-8, Coral Edge TPU, Ethos-U NPUs",
     "formats": [_PROFILE, _DESCRIPTION, VENDOR_REPORTS[2], _POWER_LOG, _DATASHEET, RTL]},
    {"id": "custom_system", "name": "Custom system", "kinds": ["custom"],
     "examples": "Your own board or chip, a prototype, a design study",
     "formats": [_PROFILE, _DESCRIPTION, _DATASHEET, _POWER_LOG, _ELF, SCHEMATIC, PCB, RTL, NETLIST]},
]

MAX_BYTES = {"model": 100 * 1024 * 1024, "hardware": 20 * 1024 * 1024}


def all_hardware_formats() -> list[FileFormat]:
    seen: dict[str, FileFormat] = {}
    for c in CATEGORIES:
        for f in c["formats"]:
            seen.setdefault(f["id"], f)
    return list(seen.values())


def unsupported_for(filename: str) -> FileFormat | None:
    """The planned/unsupported format a file name belongs to, if any."""
    low = filename.lower()
    for f in [*MODEL_FORMATS, *all_hardware_formats()]:
        if f["status"] != "supported" and any(low.endswith(e) for e in f["extensions"]):
            return f
    return None


def catalogue() -> dict:
    return {"model": MODEL_FORMATS, "categories": CATEGORIES, "max_bytes": MAX_BYTES}
