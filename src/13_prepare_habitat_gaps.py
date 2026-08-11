"""
Phase 4 — Typed habitat connection opportunities (Missing Links).

Identifies candidate gaps between habitat patches using transparent geometry rules.
Labels outputs as potential habitat connections — NOT known animal movement corridors.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points, unary_union

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(__file__).resolve().parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from config import load_settings  # noqa: E402
from utils import ensure_dirs, setup_logging, to_analysis_crs, write_gdf  # noqa: E402


GAP_SHORT_M = 50
GAP_MED_M = 150
GAP_MAX_PAIR_M = 250  # max edge distance for pair-based short gaps
STEPPING_STONE_MAX_M = 400
STEPPING_STONE_MAX_HA = 5.0


def _nearest_pair_gaps(
    patches: gpd.GeoDataFrame,
    *,
    max_dist_m: float,
    crs: str,
) -> list[dict[str, Any]]:
    """
    Build gap opportunities from nearest-neighbour patch pairs under max_dist_m.

    Performance: use centroids + STRtree for candidate search, then refine with
    polygon edge distance only for a small candidate set. Prefer precomputed
    nn_distance_m when present to skip patches that are already too far.
    """
    gdf = to_analysis_crs(patches, crs).copy()
    if gdf.empty or len(gdf) < 2:
        return []
    if "patch_id" not in gdf.columns:
        gdf["patch_id"] = [f"p{i:04d}" for i in range(len(gdf))]
    if "area_ha" not in gdf.columns:
        gdf["area_ha"] = gdf.geometry.area / 10000.0

    # Skip patches whose known NN is already beyond threshold
    if "nn_distance_m" in gdf.columns:
        gdf = gdf[gdf["nn_distance_m"].fillna(1e9) <= max_dist_m].copy()
    if len(gdf) < 2:
        return []

    gdf = gdf.reset_index(drop=True)
    geoms = list(gdf.geometry)
    ids = list(gdf["patch_id"].astype(str))
    areas = list(gdf["area_ha"].astype(float))
    centroids = list(gdf.geometry.centroid)
    # STRtree on centroids (fast)
    cent_gdf = gpd.GeoDataFrame(geometry=centroids, crs=crs)
    tree = cent_gdf.sindex

    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for i, geom in enumerate(geoms):
        # Candidate centroids within max_dist + cushion
        cand_idx = list(tree.intersection(centroids[i].buffer(max_dist_m + 50).bounds))
        best_j = None
        best_d = None
        # Rank by centroid distance first (cheap), refine top few with edge distance
        ranked: list[tuple[float, int]] = []
        for j in cand_idx:
            if j == i:
                continue
            cd = centroids[i].distance(centroids[j])
            if cd <= max_dist_m + 200:
                ranked.append((cd, j))
        ranked.sort(key=lambda x: x[0])
        for _, j in ranked[:12]:
            d = geom.distance(geoms[j])
            if d <= 0 or d > max_dist_m:
                continue
            if best_d is None or d < best_d:
                best_d = d
                best_j = j
        if best_j is None or best_d is None:
            continue
        a, b = ids[i], ids[best_j]
        key = tuple(sorted((a, b)))
        if key in seen:
            continue
        seen.add(key)

        p1, p2 = nearest_points(geoms[i], geoms[best_j])
        link = LineString([p1, p2])
        if best_d <= GAP_SHORT_M:
            gap_type = "SHORT_50M"
        elif best_d <= GAP_MED_M:
            gap_type = "SHORT_MED"
        else:
            gap_type = "NEAR_PAIR"

        rows.append(
            {
                "opportunity_id": f"GAP_{len(rows)+1:04d}",
                "opportunity_type": gap_type,
                "gap_length_m": round(float(best_d), 1),
                "patch_id_a": a,
                "patch_id_b": b,
                "patch_area_ha_a": round(areas[i], 3),
                "patch_area_ha_b": round(areas[best_j], 3),
                "habitat_potentially_connected_ha": round(areas[i] + areas[best_j], 3),
                "geometry": link.buffer(max(best_d * 0.35, 8.0)),
                "link_geometry_wkt": link.wkt,
                "why_it_matters": (
                    f"Two habitat patches are separated by about {best_d:.0f} m. "
                    "Closing or revegetating this gap could strengthen a potential habitat connection."
                ),
            }
        )
    return rows


def _road_gaps(
    patches: gpd.GeoDataFrame,
    roads: gpd.GeoDataFrame,
    *,
    crs: str,
    search_m: float = 60.0,
) -> list[dict[str, Any]]:
    """
    Where habitat exists on both sides of a high/medium road barrier.

    Fast path: use patch centroids only for side tests and distance ranking.
    """
    p = to_analysis_crs(patches, crs).copy()
    if p.empty or roads is None or roads.empty:
        return []
    r = to_analysis_crs(roads, crs)
    if "barrier_class" in r.columns:
        r = r[r["barrier_class"].isin(["high", "medium"])].copy()
    if r.empty:
        return []
    if "area_ha" not in p.columns:
        p["area_ha"] = p.geometry.area / 10000.0
    p["centroid"] = p.geometry.centroid

    rows = []
    sample = r.sample(min(80, len(r)), random_state=42) if len(r) else r
    p_tree = p.sindex

    for _, road in sample.iterrows():
        geom = road.geometry
        if geom is None or geom.is_empty:
            continue
        buf = geom.buffer(search_m)
        cand = list(p_tree.intersection(buf.bounds))
        if len(cand) < 2:
            continue
        hits = p.iloc[cand]
        mid = geom.interpolate(0.5, normalized=True)
        try:
            coords = list(geom.coords)
            ax = coords[-1][0] - coords[0][0]
            ay = coords[-1][1] - coords[0][1]
        except Exception:
            ax, ay = 1.0, 0.0
        side_a = []
        side_b = []
        for i, patch in hits.iterrows():
            c = patch["centroid"]
            if not buf.contains(c):
                continue
            cross = ax * (c.y - mid.y) - ay * (c.x - mid.x)
            (side_a if cross >= 0 else side_b).append(patch)
        if not side_a or not side_b:
            continue
        # centroid distances only (fast)
        best = None
        for pa in side_a[:8]:
            for pb in side_b[:8]:
                d = pa["centroid"].distance(pb["centroid"])
                if d <= 0 or d > search_m * 3:
                    continue
                if best is None or d < best[0]:
                    best = (d, pa, pb)
        if best is None:
            continue
        d, pa, pb = best
        link = LineString([pa["centroid"], pb["centroid"]])
        rows.append(
            {
                "opportunity_id": f"ROAD_{len(rows)+1:04d}",
                "opportunity_type": "ROAD_GAP",
                "gap_length_m": round(float(d), 1),
                "patch_id_a": str(pa.get("patch_id", "")),
                "patch_id_b": str(pb.get("patch_id", "")),
                "patch_area_ha_a": round(float(pa.get("area_ha", 0)), 3),
                "patch_area_ha_b": round(float(pb.get("area_ha", 0)), 3),
                "habitat_potentially_connected_ha": round(
                    float(pa.get("area_ha", 0) or 0) + float(pb.get("area_ha", 0) or 0), 3
                ),
                "geometry": link.buffer(12.0),
                "link_geometry_wkt": link.wkt,
                "major_barrier": str(road.get("barrier_class", "road")),
                "why_it_matters": (
                    "Vegetation occurs on both sides of a road barrier. "
                    "This is a modelled road-gap opportunity, not evidence of crossing behaviour."
                ),
            }
        )
        if len(rows) >= 40:
            break
    return rows


def _riparian_gaps(
    component_polys: gpd.GeoDataFrame,
    *,
    crs: str,
) -> list[dict[str, Any]]:
    if component_polys is None or component_polys.empty:
        return []
    g = to_analysis_crs(component_polys, crs)
    # expect a component field
    col = None
    for c in ("component", "opportunity_component", "flag", "name"):
        if c in g.columns:
            col = c
            break
    if col:
        g = g[g[col].astype(str).str.contains("riparian", case=False, na=False)].copy()
    if g.empty:
        # if no filter worked, try riparian_gap in columns as boolean dissolve leftovers
        return []
    rows = []
    g = g.explode(index_parts=False, ignore_index=True)
    g = g[g.geometry.area / 10000.0 >= 0.05].copy()
    if len(g) > 120:
        # keep largest
        g = g.assign(_a=g.geometry.area).sort_values("_a", ascending=False).head(120)
    for i, row in g.iterrows():
        area_ha = float(row.geometry.area) / 10000.0
        rows.append(
            {
                "opportunity_id": f"CREEK_{len(rows)+1:04d}",
                "opportunity_type": "CREEK_GAP",
                "gap_length_m": None,
                "gap_area_ha": round(area_ha, 3),
                "patch_id_a": "",
                "patch_id_b": "",
                "patch_area_ha_a": None,
                "patch_area_ha_b": None,
                "habitat_potentially_connected_ha": None,
                "geometry": row.geometry,
                "link_geometry_wkt": "",
                "why_it_matters": (
                    "Cleared land within the riparian zone may interrupt a streamside vegetation link. "
                    "Field assessment is required."
                ),
            }
        )
    return rows


def _stepping_stones(patches: gpd.GeoDataFrame, *, crs: str) -> list[dict[str, Any]]:
    """Small patch between two larger patches — classic stepping-stone geometry."""
    gdf = to_analysis_crs(patches, crs).copy()
    if gdf.empty:
        return []
    if "area_ha" not in gdf.columns:
        gdf["area_ha"] = gdf.geometry.area / 10000.0
    small = gdf[gdf["area_ha"] <= STEPPING_STONE_MAX_HA].reset_index(drop=True)
    large = gdf[gdf["area_ha"] > STEPPING_STONE_MAX_HA].reset_index(drop=True)
    if small.empty or len(large) < 2:
        return []
    # Cap small-patch scan for runtime
    if len(small) > 200:
        small = small.sample(200, random_state=42).reset_index(drop=True)

    large_c = list(large.geometry.centroid)
    large_tree = gpd.GeoSeries(large_c, crs=crs).sindex
    rows = []
    for _, s in small.iterrows():
        sc = s.geometry.centroid
        cand = list(large_tree.intersection(sc.buffer(STEPPING_STONE_MAX_M).bounds))
        if len(cand) < 2:
            continue
        dists = []
        for j in cand:
            d = sc.distance(large_c[j])
            if 0 < d <= STEPPING_STONE_MAX_M:
                dists.append((d, j))
        if len(dists) < 2:
            continue
        dists.sort(key=lambda x: x[0])
        d1, j1 = dists[0]
        d2, j2 = dists[1]
        l1 = large.iloc[j1]
        l2 = large.iloc[j2]
        connected_ha = float(l1["area_ha"]) + float(l2["area_ha"]) + float(s["area_ha"])
        rows.append(
            {
                "opportunity_id": f"STEP_{len(rows)+1:04d}",
                "opportunity_type": "STEPPING_STONE",
                "gap_length_m": round(float(d1 + d2), 1),
                "gap_area_ha": round(float(s["area_ha"]), 3),
                "patch_id_a": str(l1.get("patch_id", "")),
                "patch_id_b": str(l2.get("patch_id", "")),
                "stepping_patch_id": str(s.get("patch_id", "")),
                "patch_area_ha_a": round(float(l1["area_ha"]), 3),
                "patch_area_ha_b": round(float(l2["area_ha"]), 3),
                "habitat_potentially_connected_ha": round(connected_ha, 3),
                "geometry": s.geometry.buffer(15),
                "link_geometry_wkt": "",
                "why_it_matters": (
                    "A small vegetation patch sits near two larger habitat areas and may act as a "
                    "stepping-stone in the landscape network (modelled geometry only)."
                ),
            }
        )
        if len(rows) >= 60:
            break
    return rows


def _remnant_expansion(
    patches: gpd.GeoDataFrame,
    grid: gpd.GeoDataFrame,
    *,
    crs: str,
) -> list[dict[str, Any]]:
    """
    Remnant expansion candidates from existing opportunity grid flags.

    Uses `patch_gap_edge` cells (already calculated in Phase 6 prep) near rainforest
    patches — avoids expensive polygon intersections with a single huge cleared mask.
    """
    p = to_analysis_crs(patches, crs)
    g = to_analysis_crs(grid, crs) if grid is not None else None
    if p.empty or g is None or g.empty or "patch_gap_edge" not in g.columns:
        return []

    edge = g[g["patch_gap_edge"] == True].copy()  # noqa: E712
    if edge.empty:
        return []
    # Prefer cells already tagged near core / near reserve when available
    if "near_core" in edge.columns:
        near = edge[edge["near_core"] == True]  # noqa: E712
        if not near.empty:
            edge = near
    if len(edge) > 800:
        edge = edge.sample(800, random_state=42)

    # Dissolve into contiguous expansion zones
    try:
        dissolved = edge.dissolve().explode(index_parts=False, ignore_index=True)
    except Exception:
        dissolved = edge.copy()
    dissolved["area_ha"] = dissolved.geometry.area / 10000.0
    dissolved = dissolved[(dissolved["area_ha"] >= 0.2) & (dissolved["area_ha"] <= 25)].copy()
    dissolved = dissolved.sort_values("area_ha", ascending=False).head(60)

    rows = []
    p_tree = p.sindex
    for _, cell in dissolved.iterrows():
        cand = list(p_tree.intersection(cell.geometry.bounds))
        nearest_patch = None
        nearest_d = None
        for j in cand:
            d = cell.geometry.distance(p.geometry.iloc[j])
            if nearest_d is None or d < nearest_d:
                nearest_d = d
                nearest_patch = p.iloc[j]
        if nearest_patch is None:
            continue
        area_ha = float(cell["area_ha"])
        rows.append(
            {
                "opportunity_id": f"EXP_{len(rows)+1:04d}",
                "opportunity_type": "REMNANT_EXPANSION",
                "gap_length_m": None if nearest_d is None else round(float(nearest_d), 1),
                "gap_area_ha": round(area_ha, 3),
                "patch_id_a": str(nearest_patch.get("patch_id", "")),
                "patch_id_b": "",
                "patch_area_ha_a": round(float(nearest_patch.get("area_ha", 0)), 3),
                "patch_area_ha_b": None,
                "habitat_potentially_connected_ha": round(
                    float(nearest_patch.get("area_ha", 0)) + area_ha, 3
                ),
                "geometry": cell.geometry,
                "link_geometry_wkt": "",
                "why_it_matters": (
                    "A modest revegetation fringe beside an existing remnant could increase "
                    "effective habitat size (restoration potential — not a land-use decision)."
                ),
            }
        )
    return rows


def _to_gdf(rows: list[dict[str, Any]], crs: str) -> gpd.GeoDataFrame:
    if not rows:
        return gpd.GeoDataFrame(geometry=[], crs=crs)
    df = pd.DataFrame(rows)
    gdf = gpd.GeoDataFrame(df, geometry="geometry", crs=crs)
    gdf["evidence_tag"] = "CALCULATED"
    gdf["model_label"] = "potential_habitat_connection"
    gdf["not_animal_tracking"] = True
    gdf["generated_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # ensure area
    gdf["opportunity_area_ha"] = (gdf.geometry.area / 10000.0).round(3)
    return gdf


def main() -> None:
    settings = load_settings()
    paths = settings["resolved_paths"]
    crs = str(settings["study_area"]["crs_analysis"])
    logger = setup_logging(paths["logs_dir"], name="phase4_habitat_gaps", level="INFO")
    ensure_dirs(paths["interim_dir"], paths["reports_dir"], paths["csv_dir"], paths["geojson_dir"])

    master = paths["gpkg_dir"] / str(settings.get("outputs", {}).get("master_gpkg", "robertson_conservation.gpkg"))
    logger.info("=== Phase 4: Habitat connection opportunities ===")

    core = gpd.read_file(master, layer="core_habitat_patches")
    rainforest = gpd.read_file(master, layer="rainforest_patches")
    roads = gpd.read_file(master, layer="roads_barriers")
    grid = gpd.read_file(master, layer="analysis_grid_metrics")
    try:
        components = gpd.read_file(master, layer="component_polygons")
    except Exception:
        components = gpd.GeoDataFrame(geometry=[], crs=crs)

    # Prefer core habitat for network gaps; rainforest for expansion
    logger.info("Computing nearest-pair gaps...")
    pair_rows = _nearest_pair_gaps(core, max_dist_m=GAP_MAX_PAIR_M, crs=crs)
    logger.info("Pair gaps: %s", len(pair_rows))

    logger.info("Computing road gaps...")
    road_rows = _road_gaps(core, roads, crs=crs)
    logger.info("Road gaps: %s", len(road_rows))

    logger.info("Computing riparian gaps...")
    rip_rows = _riparian_gaps(components, crs=crs)
    logger.info("Riparian gaps: %s", len(rip_rows))

    logger.info("Computing stepping stones...")
    step_rows = _stepping_stones(core, crs=crs)
    logger.info("Stepping stones: %s", len(step_rows))

    logger.info("Computing remnant expansion from opportunity grid...")
    exp_rows = _remnant_expansion(rainforest, grid, crs=crs)
    logger.info("Expansion: %s", len(exp_rows))

    all_rows = pair_rows + road_rows + rip_rows + step_rows + exp_rows
    # stable IDs
    for i, row in enumerate(all_rows, start=1):
        row["opportunity_id"] = f"HCO_{i:04d}"

    gdf = _to_gdf(all_rows, crs)
    # Attach waterway / species context lightly via centroid → nearest grid later optional
    gpkg = paths["interim_dir"] / "phase4_habitat_gaps.gpkg"
    write_gdf(gdf, gpkg, layer="habitat_connection_opportunities")
    write_gdf(gdf, master, layer="habitat_connection_opportunities")
    processed = paths["processed_dir"] / master.name
    if processed.is_file():
        write_gdf(gdf, processed, layer="habitat_connection_opportunities")

    gdf.drop(columns="geometry").to_csv(
        paths["csv_dir"] / "habitat_connection_opportunities.csv", index=False
    )
    try:
        art = gdf.copy()
        art["geometry"] = art.geometry.simplify(5)
        art.to_crs("EPSG:4326").to_file(
            paths["geojson_dir"] / "habitat_connection_opportunities.geojson",
            driver="GeoJSON",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("GeoJSON failed: %s", exc)

    counts = gdf["opportunity_type"].value_counts().to_dict() if len(gdf) else {}
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n_opportunities": int(len(gdf)),
        "by_type": counts,
        "label": "potential habitat connections / modelled connectivity pathways",
        "arcgis_next": [
            "Build cost surface from roads_barriers.cost_hint",
            "Least-cost corridors between core_habitat_patches",
            "Scenario A without reserve",
            "Scenario B connectivity gain per hectare",
        ],
    }
    (paths["csv_dir"] / "habitat_gaps_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    md = f"""# Phase 4 complete — Missing links (habitat connection opportunities)

**Date:** {summary['generated_at_utc'][:10]}  
**Status:** Complete for review

## GIS concept

**Potential habitat connections** are places where geometry suggests a relatively small
intervention could link existing vegetation. Without tracking data, these are **not**
proven wildlife corridors.

## Opportunity types

| Type | Meaning |
|------|---------|
| SHORT_50M / SHORT_MED / NEAR_PAIR | Nearby patch pairs with a measurable gap |
| ROAD_GAP | Habitat on both sides of a road barrier |
| CREEK_GAP | Riparian cleared gap component |
| STEPPING_STONE | Small patch between larger patches |
| REMNANT_EXPANSION | Cleared fringe beside rainforest remnant |

## Results

- **Total opportunities:** {summary['n_opportunities']}
- **By type:** {counts}

## Deliverables

- Master layer `habitat_connection_opportunities`
- `outputs/csv/habitat_connection_opportunities.csv`
- `outputs/geojson/habitat_connection_opportunities.geojson`
- `src/13_prepare_habitat_gaps.py`

## Cartographic art

Draw gaps as soft dawn-gold stitches between moss habitat islands — delicate, hopeful,
never like hazard zoning.

## Next

Phase 5 — Ecological Opportunity Areas + Parcel Explorer attributes.
"""
    (paths["reports_dir"] / "PHASE4_COMPLETE.md").write_text(md, encoding="utf-8")
    logger.info("Phase 4 complete: %s opportunities %s", len(gdf), counts)


if __name__ == "__main__":
    main()
