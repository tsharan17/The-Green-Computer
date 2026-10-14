"""Test helpers: build tiny ONNX models with known FLOP / parameter counts."""

from __future__ import annotations

import numpy as np
from onnx import TensorProto, helper, numpy_helper


def tiny_cnn_bytes(dynamic: bool = False) -> bytes:
    """Conv(3->4, 3x3, pad 1) -> Relu -> GlobalAveragePool -> Flatten -> Gemm(4->10) on 1x3x8x8.

    Hand-computed expectations (see test_onnx_parser):
      conv   : 6912 MACs, 108 weights, 448 activation elements
      relu   : 256 FLOPs, fused into the conv layer
      gap    : 128 MACs-equivalent (256 FLOPs), 260 activation elements
      gemm   : 40 MACs, 40 + 10 params, 14 activation elements
    """
    shape = ["N", 3, "H", "W"] if dynamic else [1, 3, 8, 8]
    x = helper.make_tensor_value_info("x", TensorProto.FLOAT, shape)
    y = helper.make_tensor_value_info("y", TensorProto.FLOAT, [None, 10] if dynamic else [1, 10])

    inits = [
        numpy_helper.from_array(np.zeros((4, 3, 3, 3), np.float32), "conv_w"),
        numpy_helper.from_array(np.zeros((4, 10), np.float32), "fc_w"),
        numpy_helper.from_array(np.zeros((10,), np.float32), "fc_b"),
    ]
    nodes = [
        helper.make_node("Conv", ["x", "conv_w"], ["c"], pads=[1, 1, 1, 1], name="conv"),
        helper.make_node("Relu", ["c"], ["r"], name="relu"),
        helper.make_node("GlobalAveragePool", ["r"], ["g"], name="gap"),
        helper.make_node("Flatten", ["g"], ["f"], name="flat"),
        helper.make_node("Gemm", ["f", "fc_w", "fc_b"], ["y"], name="fc"),
    ]
    graph = helper.make_graph(nodes, "tiny", [x], [y], initializer=inits)
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    return model.SerializeToString()
