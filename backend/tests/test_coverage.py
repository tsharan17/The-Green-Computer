"""A model the engine cannot fully cost must never be reported as feasible."""

from __future__ import annotations

import numpy as np
from onnx import TensorProto as T
from onnx import helper as h
from onnx import numpy_helper as nh

from app.data_loader import load_devices
from app.engine.coverage import coverage, unmodelled_ops
from app.engine.evaluator import evaluate
from app.engine.workload.onnx_parser import parse_onnx
from app.schemas.metrics import Feasibility
from app.schemas.project import Constraints, Workload
from app.schemas.results import Config


def _model(nodes, init, x_type, x_shape) -> bytes:
    g = h.make_graph(nodes, "g", [h.make_tensor_value_info("x", x_type, x_shape)],
                     [h.make_tensor_value_info("y", x_type, None)], initializer=init)  # fmt: skip
    m = h.make_model(g, opset_imports=[h.make_opsetid("", 17)])
    m.ir_version = 8
    return m.SerializeToString()


def _lstm() -> bytes:
    init = [nh.from_array(np.ones((1, 4 * 512, 1024), np.float32), "W"),
            nh.from_array(np.ones((1, 4 * 512, 512), np.float32), "R")]  # fmt: skip
    return _model([h.make_node("LSTM", ["x", "W", "R"], ["y"], hidden_size=512)], init, T.FLOAT, [1000, 1, 1024])


def _qlinear() -> bytes:
    init = [nh.from_array(np.ones((64, 3, 3, 3), np.int8), "w"), nh.from_array(np.array(0.1, np.float32), "s"),
            nh.from_array(np.array(0, np.uint8), "z"), nh.from_array(np.array(0, np.int8), "zw")]  # fmt: skip
    node = h.make_node("QLinearConv", ["x", "s", "z", "w", "s", "zw", "s", "z"], ["y"], kernel_shape=[3, 3], pads=[1, 1, 1, 1])
    return _model([node], init, T.UINT8, [1, 3, 1024, 1024])


def _einsum() -> bytes:
    init = [nh.from_array(np.ones((8, 8), np.float32), "w")]
    return _model([h.make_node("Einsum", ["x", "w"], ["y"], equation="ij,jk->ik")], init, T.FLOAT, [8, 8])


def _unknown() -> bytes:
    return _model([h.make_node("NonMaxSuppression", ["x"], ["y"])], [], T.FLOAT, [1, 4, 8])


def test_recurrent_quantised_and_einsum_layers_now_have_a_cost():
    lstm = parse_onnx(_lstm()).profile
    assert lstm.gflops > 3.0 and coverage(lstm) == 1.0  # 1000 steps x 3.1 M weights x 2 FLOPs
    q = parse_onnx(_qlinear()).profile
    assert q.gflops > 3.0 and q.params_m > 1e-3  # int8 weights count as parameters
    assert parse_onnx(_einsum()).profile.gflops > 0


def test_an_operator_with_no_cost_model_caps_the_verdict(monkeypatch):
    model = parse_onnx(_unknown()).profile
    model.id = "t"
    assert unmodelled_ops(model) == {"NonMaxSuppression": 1} and coverage(model) == 0.0
    hw = load_devices()["jetson-orin-nx"]
    top = max(hw.power_modes, key=lambda p: p.cap_w)
    cfg = Config(precision="fp16", batch=1, power_mode_id=top.id, cooling_id=hw.default_cooling)
    r = evaluate(model, hw, cfg, Workload(fps=1, ambient_c=25, hours_per_day=8), Constraints())
    assert r.feasibility != Feasibility.PREDICTED_FEASIBLE and r.model_coverage == 0.0
    assert "NonMaxSuppression" in r.notes[0]
