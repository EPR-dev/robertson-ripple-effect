"""
PYTHON DATA PREP — waterways, wetlands/hydro areas, riparian proximity inputs.
"""

from __future__ import annotations

from typing import Iterable

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.ops import unary_union


ASSOCIATION_NOTE = (
    "Hydro/riparian context for landscape function. Association / potential "
    "function only — not reserve causation."
)


def clip_hydro(
    gdf: gpd.GeoDataFrame,
    study_area: gpd.GeoDataFrame,
    *,
    crs_analysis: str,
) -> gpd.GeoDataFrame:
    if gdf.empty:
        return gdf.to_crs(crs_analysis) if gdf.crs else gdf
    left = gdf.to_crs(crs_analysis)
    sa = study_area.to_crs(crs_analysis)
    try:
        out = gpd.clip(left, sa)
    except Exception:
        union = unary_union(list(sa.geometry))
        out = left.loc[left.intersects(union)].copy()
    if out.empty:
        return out
    out = out.copy()
    out["interpretation"] = ASSOCIATION_NOTE
    gtypes = out.geom_type.astype(str)
    if gtypes.str.contains("Line").any():
        out["length_m"] = out.geometry.length
    if gtypes.str.contains("Polygon").any():
        out["area_ha"] = out.geometry.area / 10000.0
    return out.reset_index(drop=True)


def build_riparian_buffers(
    hydro_lines: gpd.GeoDataFrame,
    *,
    buffers_m: Iterable[float],
    crs_analysis: str,
) -> gpd.GeoDataFrame:
    """Dissolve buffered riparian zones at configured distances."""
    if hydro_lines.empty:
        return gpd.GeoDataFrame(
            columns=["buffer_m", "interpretation", "geometry"],
            geometry=[],
            crs=crs_analysis,
        )
    lines = hydro_lines.to_crs(crs_analysis)
    rows = []
    for dist in buffers_m:
        buf = lines.buffer(float(dist))
        geom = unary_union(list(buf))
        rows.append(
            {
                "buffer_m": float(dist),
                "area_ha": float(geom.area) / 10000.0 if not geom.is_empty else 0.0,
                "interpretation": ASSOCIATION_NOTE,
                "geometry": geom,
            }
        )
    return gpd.GeoDataFrame(rows, crs=crs_analysis)


def add_riparian_metrics_to_grid(
    grid: gpd.GeoDataFrame,
    hydro_lines: gpd.GeoDataFrame,
    *,
    buffers_m: Iterable[float],
    crs_analysis: str,
) -> gpd.GeoDataFrame:
    """Distance to nearest hydro line + in-buffer flags for analysis grid cells."""
    out = grid.to_crs(crs_analysis).copy()
    if hydro_lines.empty:
        out["dist_to_stream_m"] = np.nan
        for dist in buffers_m:
            out[f"riparian_{int(dist)}m"] = False
        out["interpretation_water"] = ASSOCIATION_NOTE
        return out

    lines = hydro_lines.to_crs(crs_analysis)
    line_union = unary_union(list(lines.geometry))
    cents = out.geometry.centroid
    out["dist_to_stream_m"] = cents.distance(line_union)
    for dist in buffers_m:
        out[f"riparian_{int(dist)}m"] = out["dist_to_stream_m"] <= float(dist)
    out["interpretation_water"] = ASSOCIATION_NOTE
    return out


def hydro_summary(hydro_lines: gpd.GeoDataFrame, hydro_areas: gpd.GeoDataFrame) -> pd.DataFrame:
    rows = [
        {
            "layer": "hydro_lines",
            "features": len(hydro_lines),
            "length_km": round(float(hydro_lines.geometry.length.sum()) / 1000.0, 2)
            if not hydro_lines.empty
            else 0.0,
        },
        {
            "layer": "hydro_areas",
            "features": len(hydro_areas),
            "area_ha": round(float(hydro_areas.geometry.area.sum()) / 10000.0, 2)
            if not hydro_areas.empty
            else 0.0,
        },
    ]
    return pd.DataFrame(rows)


def main() -> None:
    raise SystemExit("Run src/05_prepare_ripple.py for Phase 5.")


if __name__ == "__main__":
    main()
