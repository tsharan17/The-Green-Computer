"""ONNX bytes -> per-layer workload graph (shapes, MACs, bytes moved).

Pure function of the file contents: no network, no code execution. Only the ONNX
protobuf format is accepted (pickle / torch archives are refused by the caller and here).

Modelling assumptions (documented in docs/assumptions.md):
- A graph runs at batch 1; dynamic dims need an explicit default.
- Elementwise ops (activations, Add/Mul, BatchNorm) are assumed fused into their producer:
  their FLOPs are added to the previous layer, they add no activation traffic or launches.
- View ops (Reshape, Flatten, ...) cost nothing.
- Every other op reads its activation inputs and writes its outputs once (unfused traffic).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import onnx
from onnx import TensorProto, shape_inference

from app.schemas.model import Layer, ModelProfile

VIEW_OPS = {
    "Reshape", "Flatten", "Squeeze", "Unsqueeze", "Identity", "Shape", "Constant",
    "ConstantOfShape", "Cast", "Dropout",
}  # fmt: skip
FUSED_ELEMENTWISE = {
    "Relu", "LeakyRelu", "Sigmoid", "Tanh", "Clip", "HardSwish", "HardSigmoid", "Add", "Sub",
    "Mul", "Div", "BatchNormalization", "PRelu", "Elu", "Gelu", "Erf", "Mish", "Neg", "Sqrt",
    "Pow", "Min", "Max", "Where", "Softplus", "Softsign", "Abs", "Exp", "Log", "Sin", "Cos", "Ceil",
    "Floor", "Round", "Sign", "Mod", "Sum", "Mean", "Equal", "Less", "LessOrEqual", "Greater",
    "GreaterOrEqual", "And", "Or", "Not", "QuantizeLinear", "DequantizeLinear", "QLinearAdd",
    "QLinearMul", "QLinearSigmoid", "QLinearLeakyRelu",
}  # fmt: skip
# Operators with their own cost model (the branches of the layer loop below).
COMPUTE_OPS = {
    "Conv", "ConvTranspose", "ConvInteger", "QLinearConv", "Gemm", "MatMul", "MatMulInteger", "QLinearMatMul", "Einsum",
    "LSTM", "GRU", "RNN", "Attention", "MultiHeadAttention", "MaxPool", "AveragePool", "GlobalAveragePool",
    "QLinearAveragePool", "QLinearGlobalAveragePool", "ReduceMean", "ReduceSum", "ReduceMax", "ReduceMin", "ReduceProd",
    "ReduceL1", "ReduceL2", "ArgMax", "ArgMin", "TopK", "LpPool", "GlobalMaxPool", "Softmax", "LayerNormalization", "InstanceNormalization", "GroupNormalization",
}  # fmt: skip
# Weights may be quantised. Scalars (scales, zero points) and int64 shapes are not weights.
WEIGHT_TYPES = {
    TensorProto.FLOAT, TensorProto.FLOAT16, TensorProto.DOUBLE, TensorProto.BFLOAT16, TensorProto.INT8,
    TensorProto.UINT8, TensorProto.INT16, TensorProto.UINT16, TensorProto.INT32,
}  # fmt: skip


class ModelParseError(ValueError):
    """The file is not a usable ONNX model."""


@dataclass
class ParseResult:
    profile: ModelProfile
    warnings: list[str] = field(default_factory=list)


def _prod(xs) -> int:
    return int(math.prod(xs)) if xs else 1


def _dims(vi_type, name: str, default: int | None, first: bool) -> list[int] | None:
    t = vi_type.tensor_type
    if not t.HasField("shape"):
        return None
    out = []
    for i, d in enumerate(t.shape.dim):
        if d.HasField("dim_value") and d.dim_value > 0:
            out.append(int(d.dim_value))
        elif i == 0 and first:
            out.append(1)
        elif default is not None:
            out.append(default)
        else:
            raise ModelParseError(
                f"tensor '{name}' has a dynamic dimension ('{d.dim_param or '?'}'); "
                "provide dynamic_dim_default"
            )
    return out


def _einsum_macs(equation: str, shapes: list[list[int] | None]) -> float | None:
    """One multiply per combination of index values. None if the equation cannot be read."""
    left = equation.replace(" ", "").split("->")[0]
    terms = left.split(",")
    if "." in left or len(terms) != len(shapes):
        return None
    sizes: dict[str, int] = {}
    for term, shape in zip(terms, shapes, strict=True):
        if shape is None or len(term) != len(shape):
            return None
        sizes.update(zip(term, shape, strict=True))
    return float(_prod(list(sizes.values())))


def parse_onnx(
    data: bytes, name: str = "uploaded-model", dynamic_dim_default: int | None = None
) -> ParseResult:
    if data[:1] == b"\x80" or data[:2] == b"PK":
        raise ModelParseError("pickle / torch archives are refused; export to ONNX first")
    try:
        model = onnx.load_model_from_string(data)
    except Exception as e:  # protobuf decode errors surface as various types
        raise ModelParseError(f"not a valid ONNX file: {e}") from e

    g = model.graph
    for init in g.initializer:
        if init.data_location == TensorProto.EXTERNAL:
            raise ModelParseError("ONNX files with external data are not supported")

    init_names = {i.name for i in g.initializer}
    # Pin dynamic input dims so shape inference can propagate concrete shapes.
    for vi in g.input:
        if vi.name in init_names or not vi.type.tensor_type.HasField("shape"):
            continue
        dims = _dims(vi.type, vi.name, dynamic_dim_default, first=True)
        t = vi.type.tensor_type
        for d, v in zip(t.shape.dim, dims or [], strict=False):
            d.dim_value = v
    try:
        model = shape_inference.infer_shapes(model)
    except Exception as e:
        raise ModelParseError(f"shape inference failed: {e}") from e
    g = model.graph

    shapes: dict[str, list[int]] = {}
    for init in g.initializer:
        shapes[init.name] = [int(d) for d in init.dims]
    for coll in (g.input, g.value_info, g.output):
        for vi in coll:
            if vi.name in shapes or not vi.type.HasField("tensor_type"):
                continue
            dims = _dims(vi.type, vi.name, dynamic_dim_default, first=True)
            if dims is not None:
                shapes[vi.name] = dims

    float_init = {i.name for i in g.initializer if i.data_type in WEIGHT_TYPES and _prod(i.dims) > 1}
    warnings: list[str] = []
    seen_init: set[str] = set()
    layers: list[Layer] = []
    pending_flops = 0.0
    # Tensor wiring for lifetimes: in-place (fused elementwise) and view ops alias their output to
    # an existing buffer, so they never allocate.
    alias: dict[str, str] = {}
    pending_inputs: list[str] = []

    def elems(t: str) -> int:
        return _prod(shapes[t]) if t in shapes else 0

    def canon(t: str) -> str:
        while t in alias:
            t = alias[t]
        return t

    for idx, node in enumerate(g.node):
        op = node.op_type
        outs = [o for o in node.output if o]
        ins = [i for i in node.input if i]
        out_e = sum(elems(o) for o in outs)

        acts = [canon(i) for i in ins if i not in init_names]
        if op in VIEW_OPS:
            if acts:
                for o in outs:
                    alias[o] = acts[0]
            continue
        if op in FUSED_ELEMENTWISE:
            f = float(out_e)
            if layers:
                layers[-1].flops += f
                last = layers[-1]
                last.in_tensors.extend(
                    a for a in acts if a not in last.in_tensors and a not in last.out_tensors
                )
            else:
                pending_flops += f
                pending_inputs.extend(acts)
            if acts:
                for o in outs:
                    alias[o] = acts[0]
            continue

        act_in = sum(elems(i) for i in ins if i not in init_names)
        params = 0.0
        for i in ins:
            if i in float_init and i not in seen_init:
                seen_init.add(i)
                params += elems(i)

        macs = 0.0
        if op in ("QLinearConv", "ConvInteger"):
            w = shapes.get(ins[3 if op == "QLinearConv" else 1]) if len(ins) > 3 or op == "ConvInteger" else None
            if not w or len(w) < 3:
                raise ModelParseError(f"{op} node '{node.name or idx}' has unknown weight shape")
            macs = out_e * w[1] * _prod(w[2:])
        elif op in ("LSTM", "GRU", "RNN") and shapes.get(ins[0]) and len(ins) > 2 and ins[1] in shapes and ins[2] in shapes:
            # Every time step multiplies by all the input and recurrent weights.
            layout = next((a_.i for a_ in node.attribute if a_.name == "layout"), 0)
            x = shapes[ins[0]]
            steps, batch = (x[1], x[0]) if layout else (x[0], x[1])
            macs = float(steps * batch) * (_prod(shapes[ins[1]]) + _prod(shapes[ins[2]]))
        elif op == "Einsum":
            equation = next((a_.s.decode() for a_ in node.attribute if a_.name == "equation"), "")
            got = _einsum_macs(equation, [shapes.get(i) for i in ins])
            if got is None:
                warnings.append("Einsum with a form that could not be read counted as data movement only")
            macs = got or 0.0
        elif op in ("Attention", "MultiHeadAttention") and shapes.get(ins[0]) and len(shapes[ins[0]]) == 3:
            # Query, key and value projections, then the attention product (ignoring head count).
            _, n, d = shapes[ins[0]]
            macs = float(3 * n * d * d + n * n * d)
        elif op in ("QLinearMatMul", "MatMulInteger"):
            a = shapes.get(ins[0])
            if not a:
                raise ModelParseError(f"{op} node '{node.name or idx}' has unknown input shape")
            macs = out_e * a[-1]
        elif op in ("QLinearAveragePool", "QLinearGlobalAveragePool", "ReduceMax", "ReduceMin", "ReduceProd",
                    "ReduceL2", "ReduceL1", "ArgMax", "ArgMin", "TopK", "LpPool", "GlobalMaxPool"):  # fmt: skip
            macs = elems(ins[0]) / 2.0
        elif op == "QLinearConcat":
            macs = 0.0
        elif op in ("Conv", "ConvTranspose"):
            w = shapes.get(ins[1]) if len(ins) > 1 else None
            if not w or len(w) < 3:
                raise ModelParseError(f"{op} node '{node.name or idx}' has unknown weight shape")
            if op == "Conv":
                macs = out_e * w[1] * _prod(w[2:])
            else:
                macs = elems(ins[0]) * w[1] * _prod(w[2:])
        elif op == "Gemm":
            a = shapes.get(ins[0])
            trans_a = next((a_.i for a_ in node.attribute if a_.name == "transA"), 0)
            if not a or len(a) != 2:
                raise ModelParseError(f"Gemm node '{node.name or idx}' has unknown input shape")
            k = a[0] if trans_a else a[1]
            macs = out_e * k
        elif op == "MatMul":
            a = shapes.get(ins[0])
            if not a:
                raise ModelParseError(f"MatMul node '{node.name or idx}' has unknown input shape")
            macs = out_e * a[-1]
        elif op in ("MaxPool", "AveragePool", "GlobalAveragePool", "ReduceMean", "ReduceSum"):
            macs = elems(ins[0]) / 2.0  # ~1 FLOP per input element
        elif op in ("Softmax", "LayerNormalization", "InstanceNormalization", "GroupNormalization"):
            macs = out_e * 2.5  # ~5 FLOPs per element
        elif op in ("Transpose", "Concat", "Slice", "Split", "Gather", "Resize", "Pad", "Expand",
                    "Tile", "Upsample", "ScatterND", "GatherND"):  # fmt: skip
            macs = 0.0  # pure data movement
        else:
            warnings.append(f"unsupported op '{op}' has no cost model: counted as zero compute")

        layer = Layer(
            name=node.name or f"{op}_{idx}",
            op=op,
            flops=2.0 * macs + pending_flops,
            params=params,
            act_elems=float(act_in + out_e),
            in_tensors=list(dict.fromkeys([*pending_inputs, *acts])),
            out_tensors=list(outs),
        )
        pending_flops = 0.0
        pending_inputs = []
        layers.append(layer)

    if not layers:
        raise ModelParseError("the graph has no compute layers")

    total_params = sum(elems(n) for n in float_init)
    total_flops = sum(layer.flops for layer in layers)
    total_act = sum(layer.act_elems for layer in layers)
    first_input = next((vi for vi in g.input if vi.name not in init_names), None)
    in_shape = shapes.get(first_input.name) if first_input else None
    produced = {t for layer in layers for t in layer.out_tensors}
    used = {t for layer in layers for t in layer.in_tensors}
    tensors = {t: float(elems(t)) for t in produced | used}
    graph_inputs = [vi.name for vi in g.input if vi.name not in init_names]
    graph_outputs = list(dict.fromkeys(canon(vi.name) for vi in g.output))

    profile = ModelProfile(
        id="",  # assigned on storage
        name=name,
        task="custom (ONNX upload)",
        input_desc="x".join(str(d) for d in in_shape) if in_shape else "unknown",
        params_m=total_params / 1e6,
        gflops=total_flops / 1e9,
        n_layers=len(layers),
        act_mb_fp32=total_act * 4.0 / 1e6,
        baseline_accuracy=1.0,
        accuracy_metric="not provided (relative accuracy only)",
        fidelity="graph",
        resolution_scalable=bool(in_shape and len(in_shape) == 4),
        layers=layers,
        tensors=tensors,
        graph_inputs=graph_inputs,
        graph_outputs=graph_outputs,
        notes="Parsed from ONNX at batch 1. Elementwise ops assumed fused.",
    )
    # De-duplicate repeated warnings.
    return ParseResult(profile=profile, warnings=sorted(set(warnings)))


def manual_profile(
    name: str,
    params_m: float,
    gflops: float,
    n_layers: int,
    act_mb_fp32: float | None,
    baseline_accuracy: float = 1.0,
    accuracy_metric: str = "not provided (relative accuracy only)",
) -> ModelProfile:
    """Build a profile from user-entered numbers. Wider uncertainty bands apply."""
    estimated = act_mb_fp32 is None
    act = act_mb_fp32 if act_mb_fp32 is not None else max(1.0, 12.0 * gflops)
    return ModelProfile(
        id="",
        name=name,
        task="custom (manual parameters)",
        input_desc="manual",
        params_m=params_m,
        gflops=gflops,
        n_layers=n_layers,
        act_mb_fp32=act,
        baseline_accuracy=baseline_accuracy,
        accuracy_metric=accuracy_metric,
        fidelity="manual",
        notes=(
            "Manual parameters; activation traffic estimated at 12 MB per GFLOP."
            if estimated
            else "Manual parameters."
        ),
    )
