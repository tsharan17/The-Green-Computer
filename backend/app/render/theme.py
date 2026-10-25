"""Green and white palettes for the figures (light and dark), matching the interface."""

from __future__ import annotations

from typing import Any

import numpy as np


def _ramp(light: str, dark: str, n: int) -> list[str]:
    from matplotlib.colors import LinearSegmentedColormap, to_hex

    cm = LinearSegmentedColormap.from_list("r", [light, dark])
    return [to_hex(cm(v)) for v in np.linspace(0, 1, max(n, 2))][:n]


def _on_heat(dark_text: str, light_text: str, cmap_ramp: list[str]) -> Any:
    from matplotlib.colors import LinearSegmentedColormap, to_rgb

    cm = LinearSegmentedColormap.from_list("h", cmap_ramp)

    def pick(temp: np.ndarray, lay: dict[str, float]) -> str:
        n = temp.shape[0]
        cy, cx = int((lay["y"] + lay["h"] / 2) * (n - 1)), int((lay["x"] + lay["w"] / 2) * (n - 1))
        lo, hi = float(temp.min()), float(temp.max())
        r, g, b = to_rgb(cm((temp[cy, cx] - lo) / max(hi - lo, 1e-9)))
        lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
        return dark_text if lum > 0.45 else light_text

    return pick


_LIGHT_HEAT = ["#ffffff", "#e3f4e6", "#b9e2c0", "#7cc58d", "#3e9d5a", "#1a6e2f", "#0a3d1a"]
_DARK_HEAT = ["#0f2318", "#17402a", "#1f6e37", "#34a152", "#5acb73", "#a6ebb4", "#eaffe9"]

PALETTES: dict[str, dict[str, Any]] = {
    "light": {
        "bg": "#ffffff", "ink": "#0e2216", "muted": "#3c5645", "line": "#b3d1ba", "grid": "#e1eee4", "contour": "#0e2216",
        "series": ["#0e4d26", "#1f8a3f", "#52b266", "#8cc98f", "#bfe3c1"], "on_series": ["#ffffff", "#ffffff", "#0e2216", "#0e2216", "#0e2216"],
        "heat_ramp": _LIGHT_HEAT, "seq_ramp": ["#f3faf4", "#b9e2c0", "#52b266", "#1a6e2f", "#0a3d1a"],
        "bar_ramp": lambda n: _ramp("#0a3d1a", "#8cc98f", n), "on_heat": _on_heat("#0e2216", "#ffffff", _LIGHT_HEAT),
    },
    "dark": {
        "bg": "#14261a", "ink": "#ecf8ee", "muted": "#b3cdb9", "line": "#3a5d47", "grid": "#264333", "contour": "#ecf8ee",
        "series": ["#d5f7da", "#93e0a4", "#5acb73", "#34a152", "#1f6e37"], "on_series": ["#05140a", "#05140a", "#05140a", "#ffffff", "#ffffff"],
        "heat_ramp": _DARK_HEAT, "seq_ramp": ["#14261a", "#1f6e37", "#34a152", "#93e0a4", "#eaffe9"],
        "bar_ramp": lambda n: _ramp("#eaffe9", "#34a152", n), "on_heat": _on_heat("#05140a", "#ecf8ee", _DARK_HEAT),
    },
}  # fmt: skip
