"""
PYTHON DATA PREP — unweighted restoration opportunity components only.

Do not apply index weights until variables are independently mapped and approved.
"""

from __future__ import annotations

from typing import Iterable

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.ops import unary_union


NO_WEIGHTS_NOTE = (
    "Unweighted opportunity component. Mapped independently — "
    "NOT a Restoration Opportunity Index score."
)


def _edge_distance(grid: gpd.GeoDataFrame, targets: gpd.GeoDataFrame) -> np.ndarray:
    if targets.empty:
        return np.full(len(grid), np.nan)
    union = unary_union(list(targets.geometry))
    return np.asarray(grid.geometry.centroid.distance(union), dtype=float)


def _intersects_any(grid: gpd.GeoDataFrame, targets: gpd.GeoDataFrame) -> np.ndarray:
    if targets.empty:
        return np.zeros(len(grid), dtype=bool)
    # Spatial index join on cell geometry
    joined = gpd.sjoin(
        grid[["cell_id", "geometry"]],
        targets[["geometry"]].copy(),
        how="left",
        predicate="intersects",
    )
    hit = set(joined.loc[joined["index_right"].notna(), "cell_id"])
    return grid["cell_id"].isin(hit).to_numpy()


def build_opportunity_components(
    grid: gpd.GeoDataFrame,
    *,
    protected_areas: gpd.GeoDataFrame,
    reserve: gpd.GeoDataFrame,
    core_patches: gpd.GeoDataFrame,
    cleared: gpd.GeoDataFrame,
    crown_land: gpd.GeoDataFrame,
    basalt_geology: gpd.GeoDataFrame,
    crs_analysis: str,
    near_protected_m: float,
    near_core_m: float,
    near_reserve_m: float,
    isolated_nn_m: float,
    isolated_influence_m: float,
    plantable_slope_deg: float,
) -> gpd.GeoDataFrame:
    """
    Attach independent opportunity component fields to the analysis grid.

    Continuous distances + boolean flags. No weighted sum.
    """
    out = grid.to_crs(crs_analysis).copy()

    # Carry useful Phase 5 context if present
    for col in ("dist_to_stream_m", "riparian_50m", "riparian_100m", "slope_deg", "elev_m"):
        if col not in out.columns:
            out[col] = pd.NA if col.endswith("_m") or col.endswith("_deg") else False

    prot = protected_areas.to_crs(crs_analysis) if not protected_areas.empty else protected_areas
    res = reserve.to_crs(crs_analysis)
    core = core_patches.to_crs(crs_analysis) if not core_patches.empty else core_patches
    clr = cleared.to_crs(crs_analysis) if not cleared.empty else cleared
    crown = crown_land.to_crs(crs_analysis) if not crown_land.empty else crown_land
    basalt = basalt_geology.to_crs(crs_analysis) if not basalt_geology.empty else basalt_geology

    out["dist_to_protected_m"] = _edge_distance(out, prot)
    out["near_protected"] = out["dist_to_protected_m"] <= near_protected_m

    out["dist_to_reserve_m"] = _edge_distance(out, res)
    out["near_reserve"] = out["dist_to_reserve_m"] <= near_reserve_m

    out["dist_to_core_m"] = _edge_distance(out, core)
    out["near_core"] = out["dist_to_core_m"] <= near_core_m
    out["on_core"] = _intersects_any(out, core)

    out["on_cleared"] = _intersects_any(out, clr)
    # If cleared is a single large mask, centroids outside tiny slivers still count via intersects

    riparian = out["riparian_100m"].fillna(False).astype(bool)
    out["riparian_gap"] = riparian & out["on_cleared"] & ~out["on_core"]

    out["patch_gap_edge"] = out["near_core"] & out["on_cleared"] & ~out["on_core"]

    # Cells near core patches that are relatively isolated from other core patches
    if not core.empty and "nn_distance_m" in core.columns:
        isolated = core.loc[core["nn_distance_m"].fillna(0) >= isolated_nn_m].copy()
    else:
        isolated = core.iloc[0:0].copy() if hasattr(core, "iloc") else gpd.GeoDataFrame(geometry=[], crs=crs_analysis)
    out["dist_to_isolated_core_m"] = _edge_distance(out, isolated)
    out["isolated_patch_context"] = (
        (out["dist_to_isolated_core_m"] <= isolated_influence_m)
        & out["on_cleared"]
        & ~out["on_core"]
    )

    out["on_crown_land"] = _intersects_any(out, crown)
    out["on_public_land"] = out["on_crown_land"] | _intersects_any(out, prot)

    out["on_basalt_volcanic"] = _intersects_any(out, basalt)

    slope = pd.to_numeric(out.get("slope_deg"), errors="coerce")
    out["plantable_slope"] = slope.isna() | (slope <= plantable_slope_deg)

    # Explicit non-score metadata
    out["interpretation"] = NO_WEIGHTS_NOTE
    bool_cols = [
        "near_protected",
        "near_reserve",
        "near_core",
        "on_core",
        "on_cleared",
        "riparian_gap",
        "patch_gap_edge",
        "isolated_patch_context",
        "on_crown_land",
        "on_public_land",
        "on_basalt_volcanic",
        "plantable_slope",
    ]
    for c in bool_cols:
        out[c] = out[c].fillna(False).astype(bool)

    return out


COMPONENT_DEFS = [
    ("near_protected", "Within near_protected_m of NPWS protected area"),
    ("near_reserve", "Within near_reserve_m of Robertson Nature Reserve"),
    ("near_core", "Within near_core_m of core habitat (rainforest/wet sclerophyll patches)"),
    ("on_cleared", "Intersects SVTM cleared / non-native contrast mask"),
    ("riparian_gap", "Within 100 m of stream AND cleared AND not on core habitat"),
    ("patch_gap_edge", "Near core habitat edge, cleared, not already core"),
    ("isolated_patch_context", "Near relatively isolated core patch, cleared, not core"),
    ("on_public_land", "Intersects Crown land or NPWS protected area"),
    ("on_basalt_volcanic", "Intersects basalt/latite/igneous geology (association only)"),
    ("plantable_slope", "Slope at/under plantable_slope_deg (or unknown)"),
]


def component_summary(opportunity_grid: gpd.GeoDataFrame) -> pd.DataFrame:
    rows = []
    for name, desc in COMPONENT_DEFS:
        if name not in opportunity_grid.columns:
            continue
        n = int(opportunity_grid[name].sum())
        rows.append(
            {
                "component": name,
                "true_cells": n,
                "true_share": round(n / max(len(opportunity_grid), 1), 4),
                "description": desc,
                "weighted": False,
            }
        )
    return pd.DataFrame(rows)


def dissolve_component_polygons(
    opportunity_grid: gpd.GeoDataFrame,
    *,
    component: str,
    crs_analysis: str,
) -> gpd.GeoDataFrame:
    """Dissolve grid cells where a boolean component is True."""
    if component not in opportunity_grid.columns:
        return gpd.GeoDataFrame(geometry=[], crs=crs_analysis)
    sel = opportunity_grid.loc[opportunity_grid[component]].copy()
    if sel.empty:
        return gpd.GeoDataFrame(
            [{"component": component, "n_cells": 0, "interpretation": NO_WEIGHTS_NOTE}],
            geometry=[None],
            crs=crs_analysis,
        ).dropna(subset=["geometry"])
    geom = unary_union(list(sel.geometry))
    return gpd.GeoDataFrame(
        [
            {
                "component": component,
                "n_cells": len(sel),
                "area_ha": float(geom.area) / 10000.0,
                "interpretation": NO_WEIGHTS_NOTE,
            }
        ],
        geometry=[geom],
        crs=crs_analysis,
    )


def export_component_polygon_collection(
    opportunity_grid: gpd.GeoDataFrame,
    *,
    components: Iterable[str],
    crs_analysis: str,
) -> gpd.GeoDataFrame:
    frames = [
        dissolve_component_polygons(opportunity_grid, component=c, crs_analysis=crs_analysis)
        for c in components
    ]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return gpd.GeoDataFrame(geometry=[], crs=crs_analysis)
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=crs_analysis)


def main() -> None:
    raise SystemExit("Run src/06_prepare_opportunity.py for Phase 6.")


if __name__ == "__main__":
    main()
