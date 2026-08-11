"""
PYTHON DATA PREP — patch metrics and barrier inputs for ArcGIS connectivity.

Builds analysis-ready habitat patches with documented geometric rules.
Does NOT invent a weighted suitability / resistance score.

ARCGIS ANALYSIS (handoff): least-cost corridors, Scenario A/B, network measures.
"""

from __future__ import annotations

import re
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union


def _union_find_components(geoms: list[Any], *, link_distance_m: float) -> list[list[int]]:
    """
    Group polygon indices whose edges are within link_distance_m
    (buffers of link_distance/2 intersect).
    """
    n = len(geoms)
    parent = list(range(n))
    rank = [0] * n

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def unite(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri == rj:
            return
        if rank[ri] < rank[rj]:
            parent[ri] = rj
        elif rank[ri] > rank[rj]:
            parent[rj] = ri
        else:
            parent[rj] = ri
            rank[ri] += 1

    if n == 0:
        return []
    if link_distance_m <= 0:
        return [[i] for i in range(n)]

    half = link_distance_m / 2.0
    buffered = [g.buffer(half) for g in geoms]
    tree = shapely.STRtree(buffered)
    for i, buf in enumerate(buffered):
        for j in tree.query(buf, predicate="intersects"):
            j = int(j)
            if i < j:
                unite(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def filter_core_habitat(
    native_veg: gpd.GeoDataFrame,
    *,
    form_contains: list[str],
) -> gpd.GeoDataFrame:
    """Subset native veg to rainforest / wet sclerophyll style formations."""
    if native_veg.empty:
        return native_veg.copy()
    form = native_veg.get("veg_form", pd.Series("", index=native_veg.index)).fillna("").astype(str)
    cls = native_veg.get("veg_class", pd.Series("", index=native_veg.index)).fillna("").astype(str)
    text = form + " | " + cls
    mask = pd.Series(False, index=native_veg.index)
    for needle in form_contains:
        mask |= text.str.contains(re.escape(needle), case=False, na=False)
    return native_veg.loc[mask].copy()


def dissolve_habitat_patches(
    veg: gpd.GeoDataFrame,
    *,
    crs_analysis: str,
    gap_close_m: float,
    min_patch_area_ha: float,
    habitat_class: str,
) -> gpd.GeoDataFrame:
    """
    Build habitat patches:
      1) reproject
      2) optional morphological close (buffer +gap, unary_union, buffer -gap)
      3) explode multipart → single patches
      4) drop patches below min area
    """
    if veg.empty:
        return gpd.GeoDataFrame(
            columns=[
                "patch_id",
                "habitat_class",
                "area_ha",
                "perimeter_m",
                "rule_gap_close_m",
                "rule_min_area_ha",
                "geometry",
            ],
            geometry=[],
            crs=crs_analysis,
        )

    gdf = veg.to_crs(crs_analysis).explode(index_parts=False, ignore_index=True)
    min_src_m2 = max(min_patch_area_ha * 10000.0 * 0.25, 100.0)
    gdf = gdf.loc[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    gdf = gdf.loc[gdf.geometry.area >= min_src_m2].copy()
    geoms = list(gdf.geometry)
    if not geoms:
        return gpd.GeoDataFrame(
            columns=[
                "patch_id",
                "habitat_class",
                "area_ha",
                "perimeter_m",
                "rule_gap_close_m",
                "rule_min_area_ha",
                "geometry",
            ],
            geometry=[],
            crs=crs_analysis,
        )

    # Gap-close only when requested; otherwise each SVTM polygon is a patch unit
    if gap_close_m and gap_close_m > 0:
        components = _union_find_components(geoms, link_distance_m=float(gap_close_m))
        parts: list[Any] = []
        for idxs in components:
            members = [geoms[i] for i in idxs]
            if len(members) == 1:
                merged = members[0]
            else:
                try:
                    merged = shapely.union_all(members)
                except Exception:
                    merged = unary_union(members)
            if merged is None or merged.is_empty:
                continue
            if merged.geom_type == "Polygon":
                parts.append(merged)
            elif merged.geom_type == "MultiPolygon":
                parts.extend(list(merged.geoms))
            else:
                for g in getattr(merged, "geoms", []):
                    if g.geom_type == "Polygon":
                        parts.append(g)
                    elif g.geom_type == "MultiPolygon":
                        parts.extend(list(g.geoms))
    else:
        parts = geoms

    rows = []
    for i, geom in enumerate(parts):
        if geom is None or geom.is_empty:
            continue
        area_ha = float(geom.area) / 10000.0
        if area_ha < min_patch_area_ha:
            continue
        rows.append(
            {
                "patch_id": f"{habitat_class}_{i:04d}",
                "habitat_class": habitat_class,
                "area_ha": area_ha,
                "perimeter_m": float(geom.length),
                "rule_gap_close_m": gap_close_m,
                "rule_min_area_ha": min_patch_area_ha,
                "geometry": geom,
            }
        )

    if not rows:
        return gpd.GeoDataFrame(
            columns=[
                "patch_id",
                "habitat_class",
                "area_ha",
                "perimeter_m",
                "rule_gap_close_m",
                "rule_min_area_ha",
                "geometry",
            ],
            geometry=[],
            crs=crs_analysis,
        )
    out = gpd.GeoDataFrame(rows, crs=crs_analysis)
    out["interpretation"] = (
        f"SVTM-derived {habitat_class} patch after gap-close {gap_close_m} m "
        f"and min area {min_patch_area_ha} ha. Not a field-validated habitat boundary."
    )
    return out.reset_index(drop=True)


def add_patch_network_metrics(
    patches: gpd.GeoDataFrame,
    *,
    reserve: gpd.GeoDataFrame,
    nn_search_cap_m: float,
    isolation_radius_m: float,
) -> gpd.GeoDataFrame:
    """
    Add nearest-neighbour edge distance, reserve distance, and local patch count.
    Isolation proxies only — not a connectivity model.
    """
    if patches.empty:
        return patches.copy()

    out = patches.copy()
    geoms = np.array(out.geometry.values, dtype=object)
    n = len(geoms)
    nn_dist = np.full(n, np.nan)
    n_near = np.zeros(n, dtype=int)

    if n >= 2:
        centroids = shapely.centroid(geoms)
        coords = np.column_stack([shapely.get_x(centroids), shapely.get_y(centroids)])
        from scipy.spatial import cKDTree

        kdt = cKDTree(coords)
        # k=6 → self + 5 candidates; refine with true edge distance
        k = min(6, n)
        _, idxs = kdt.query(coords, k=k)
        if k == 1:
            idxs = idxs.reshape(-1, 1)
        for i in range(n):
            cand = [int(j) for j in np.atleast_1d(idxs[i]) if int(j) != i]
            if not cand:
                continue
            edge = np.asarray(shapely.distance(geoms[i], geoms[cand]), dtype=float)
            nn_dist[i] = float(np.min(edge))
        neighbors = kdt.query_ball_point(coords, r=isolation_radius_m)
        n_near = np.array([max(len(nbrs) - 1, 0) for nbrs in neighbors], dtype=int)

        if nn_search_cap_m and nn_search_cap_m > 0:
            nn_dist = np.where(nn_dist <= nn_search_cap_m, nn_dist, np.nan)

    out["nn_distance_m"] = nn_dist
    out["n_patches_within_isolation_r"] = n_near
    out["isolation_radius_m"] = isolation_radius_m

    res = reserve.to_crs(out.crs)
    res_union = unary_union(list(res.geometry))
    out["dist_to_reserve_m"] = shapely.distance(out.geometry.values, res_union)
    out["touches_reserve"] = out["dist_to_reserve_m"] <= 1.0

    with np.errstate(divide="ignore", invalid="ignore"):
        iq = (4.0 * np.pi * (out["area_ha"] * 10000.0)) / (out["perimeter_m"] ** 2)
    out["shape_isoperimetric"] = iq.replace([np.inf, -np.inf], np.nan)

    out["metric_note"] = (
        "nn_distance_m = edge-to-edge to nearest other patch (cap search). "
        "n_patches_within_isolation_r uses centroid proximity. "
        "Not least-cost connectivity — ArcGIS required for corridors/cost distance."
    )
    return out


def prepare_road_barriers(
    roads: gpd.GeoDataFrame,
    *,
    crs_analysis: str,
    study_area: gpd.GeoDataFrame,
    barrier_map: dict[str, Any],
    default_barrier: dict[str, Any],
) -> gpd.GeoDataFrame:
    """
    Clip roads and attach barrier_class + cost_hint for ArcGIS cost surfaces.

    cost_hint is an explicit ordinal preparation field — not a calibrated
    species resistance model and not a suitability score.
    """
    if roads.empty:
        return roads.to_crs(crs_analysis) if roads.crs else roads

    gdf = roads.to_crs(crs_analysis)
    sa = study_area.to_crs(crs_analysis)
    try:
        gdf = gpd.clip(gdf, sa)
    except Exception:
        union = unary_union(list(sa.geometry))
        gdf = gdf.loc[gdf.intersects(union)].copy()

    if gdf.empty:
        return gdf

    hier = pd.to_numeric(gdf.get("functionhierarchy"), errors="coerce")
    classes = []
    costs = []
    for val in hier.fillna(-1):
        key = str(int(val)) if val == val and int(val) == val else None
        # YAML keys may be ints
        entry = None
        if key is not None:
            entry = barrier_map.get(int(key)) or barrier_map.get(key)
        if entry is None:
            entry = default_barrier
        classes.append(entry.get("barrier_class", "low"))
        costs.append(int(entry.get("cost_hint", 5)))

    out = gdf.copy()
    out["barrier_class"] = classes
    out["cost_hint"] = costs
    out["length_m"] = out.geometry.length
    out["interpretation"] = (
        "Road barrier candidate for ArcGIS cost distance. "
        "cost_hint is a documented ordinal hint from road hierarchy — "
        "not a calibrated ecological resistance or suitability score."
    )
    prefer = [
        "roadnamebase",
        "roadnametype",
        "functionhierarchy",
        "barrier_class",
        "cost_hint",
        "length_m",
        "source",
        "interpretation",
        "geometry",
    ]
    keep = [c for c in prefer if c in out.columns]
    return out[keep].reset_index(drop=True)


def patch_summary_table(patches: gpd.GeoDataFrame) -> pd.DataFrame:
    if patches.empty:
        return pd.DataFrame(
            columns=[
                "habitat_class",
                "n_patches",
                "total_area_ha",
                "median_area_ha",
                "median_nn_distance_m",
                "n_touching_reserve",
            ]
        )
    rows = []
    for cls, grp in patches.groupby("habitat_class"):
        rows.append(
            {
                "habitat_class": cls,
                "n_patches": len(grp),
                "total_area_ha": round(float(grp["area_ha"].sum()), 2),
                "median_area_ha": round(float(grp["area_ha"].median()), 2),
                "median_nn_distance_m": round(float(grp["nn_distance_m"].median(skipna=True)), 1)
                if "nn_distance_m" in grp
                else None,
                "n_touching_reserve": int(grp["touches_reserve"].sum())
                if "touches_reserve" in grp
                else 0,
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    raise SystemExit("Run src/04_prepare_network.py for Phase 4.")


if __name__ == "__main__":
    main()
