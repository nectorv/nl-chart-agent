from __future__ import annotations

from abc import abstractmethod
from pydantic import BaseModel


VEGA_THEME = {
    "background": "#0f0f0f",
    "config": {
        "axis": {
            "labelColor": "#f0ede8",
            "titleColor": "#f0ede8",
            "gridColor": "#2a2a2a",
            "domainColor": "#3a3a3a",
            "tickColor": "#3a3a3a",
            "labelFont": "DM Sans",
            "titleFont": "DM Sans",
        },
        "legend": {
            "labelColor": "#f0ede8",
            "titleColor": "#f0ede8",
            "labelFont": "DM Sans",
            "titleFont": "DM Sans",
        },
        "title": {
            "color": "#f0ede8",
            "font": "Playfair Display",
            "fontSize": 18,
        },
        "mark": {"color": "#e8c547"},
        "view": {"stroke": "transparent"},
    },
}

_SCHEME = "goldred"  # fallback multi-series color scheme


class BaseChartSpec(BaseModel):
    title: str = ""
    x_field: str = ""
    y_field: str = ""
    color_field: str | None = None

    @abstractmethod
    def to_vega_lite(self, data: list[dict]) -> dict:
        ...

    def _base(self, mark: str | dict, encoding: dict) -> dict:
        spec: dict = {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            **VEGA_THEME,
            "width": "container",
            "height": 400,
            "data": {"values": []},  # caller injects data
            "mark": mark,
            "encoding": encoding,
        }
        if self.title:
            spec["title"] = self.title
        return spec


class BarChartSpec(BaseChartSpec):
    x_type: str = "nominal"  # nominal | ordinal
    y_type: str = "quantitative"
    horizontal: bool = False

    def to_vega_lite(self, data: list[dict]) -> dict:
        x_enc = {"field": self.x_field, "type": self.x_type, "axis": {"labelAngle": -30}}
        y_enc = {"field": self.y_field, "type": self.y_type}
        if self.horizontal:
            x_enc, y_enc = y_enc, x_enc
        encoding: dict = {"x": x_enc, "y": y_enc}
        if self.color_field:
            encoding["color"] = {
                "field": self.color_field,
                "type": "nominal",
                "scale": {"scheme": _SCHEME},
            }
        spec = self._base("bar", encoding)
        spec["data"] = {"values": data}
        return spec


class LineChartSpec(BaseChartSpec):
    x_type: str = "temporal"
    y_type: str = "quantitative"
    point: bool = False

    def to_vega_lite(self, data: list[dict]) -> dict:
        mark: dict | str = {"type": "line", "point": self.point} if self.point else "line"
        encoding: dict = {
            "x": {"field": self.x_field, "type": self.x_type},
            "y": {"field": self.y_field, "type": self.y_type},
        }
        if self.color_field:
            encoding["color"] = {
                "field": self.color_field,
                "type": "nominal",
                "scale": {"scheme": _SCHEME},
            }
        spec = self._base(mark, encoding)
        spec["data"] = {"values": data}
        return spec


class ScatterSpec(BaseChartSpec):
    x_type: str = "quantitative"
    y_type: str = "quantitative"
    size_field: str | None = None

    def to_vega_lite(self, data: list[dict]) -> dict:
        encoding: dict = {
            "x": {"field": self.x_field, "type": self.x_type},
            "y": {"field": self.y_field, "type": self.y_type},
        }
        if self.color_field:
            encoding["color"] = {
                "field": self.color_field,
                "type": "nominal",
                "scale": {"scheme": _SCHEME},
            }
        if self.size_field:
            encoding["size"] = {"field": self.size_field, "type": "quantitative"}
        spec = self._base("point", encoding)
        spec["data"] = {"values": data}
        return spec


class AreaChartSpec(BaseChartSpec):
    x_type: str = "temporal"
    y_type: str = "quantitative"
    stacked: bool = False

    def to_vega_lite(self, data: list[dict]) -> dict:
        mark: dict = {"type": "area", "opacity": 0.7}
        y_enc: dict = {"field": self.y_field, "type": self.y_type}
        if self.stacked:
            y_enc["stack"] = "zero"
        encoding: dict = {
            "x": {"field": self.x_field, "type": self.x_type},
            "y": y_enc,
        }
        if self.color_field:
            encoding["color"] = {
                "field": self.color_field,
                "type": "nominal",
                "scale": {"scheme": _SCHEME},
            }
        spec = self._base(mark, encoding)
        spec["data"] = {"values": data}
        return spec


class HeatmapSpec(BaseChartSpec):
    x_type: str = "ordinal"
    y_type: str = "ordinal"
    color_field: str = ""  # required for heatmap
    color_type: str = "quantitative"

    def to_vega_lite(self, data: list[dict]) -> dict:
        encoding: dict = {
            "x": {"field": self.x_field, "type": self.x_type},
            "y": {"field": self.y_field, "type": self.y_type},
            "color": {
                "field": self.color_field,
                "type": self.color_type,
                "scale": {"scheme": "yelloworangered"},
            },
        }
        spec = self._base("rect", encoding)
        spec["data"] = {"values": data}
        return spec


class PieChartSpec(BaseChartSpec):
    theta_field: str = ""
    theta_type: str = "quantitative"
    color_type: str = "nominal"

    def to_vega_lite(self, data: list[dict]) -> dict:
        encoding: dict = {
            "theta": {"field": self.theta_field, "type": self.theta_type},
            "color": {
                "field": self.color_field or self.x_field,
                "type": self.color_type,
                "scale": {"scheme": _SCHEME},
            },
        }
        spec = self._base({"type": "arc", "innerRadius": 60}, encoding)
        spec["data"] = {"values": data}
        spec["view"] = {"stroke": None}
        return spec


CHART_TYPE_MAP: dict[str, type[BaseChartSpec]] = {
    "bar": BarChartSpec,
    "line": LineChartSpec,
    "scatter": ScatterSpec,
    "area": AreaChartSpec,
    "heatmap": HeatmapSpec,
    "pie": PieChartSpec,
}
