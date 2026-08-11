"""
Phase 5 — Ecological Opportunity Areas + Parcel Explorer attributes.

Builds anonymous AREA_### polygons from unweighted opportunity ingredients.
Does NOT create acquisition targets or a black-box score.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(__file__).resolve().parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from config import load_settings  # noqa: E402
from utils import ensure_dirs, setup_logging, to_analysis_crs, write_gdf  # noqa: E402


TYPE_RULES = [
    # order matters — first match wins
    ("RIPARIAN", lambda r: bool(r.get("riparian_gap"))),
    ("CONNECT", lambda r: bool(r.get("patch_gap_edge")) or bool(r.get("isolated_patch_context"))),
    ("BUFFER", lambda r: bool(r.get("near_core")) and bool(r.get("on_cleared"))),
    ("PROTECT", lambda r: bool(r.get("on_core")) and not bool(r.get("on_cleared"))),
    ("RESTORE", lambda r: bool(r.get("on_cleared")) and bool(r.get("plantable_slope"))),
    ("INVESTIGATE", lambda r: bool(r.get("near_reserve")) or bool(r.get("near_protected"))),
]


def _assign_type(row) -> str:
    for name, fn in TYPE_RULES:
        try:
            if fn(row):
                return name
        except Exception:
            continue
    return "INVESTIGATE"


def _why(opp_type: str, row) -> str:
    templates = {
        "PROTECT": (
            "This area already contains core habitat and may warrant further conservation attention."
        ),
        "CONNECT": (
            "This area sits beside a habitat edge or near relatively isolated patches and may help "
            "reduce a gap in the network."
        ),
        "RESTORE": (
            "Cleared or non-native cover with plantable slope — revegetation could potentially "
            "strengthen nearby habitat."
        ),
        "BUFFER": (
            "Cleared land immediately beside core habitat — a buffer could reduce edge pressure "
            "on an existing remnant."
        ),
        "RIPARIAN": (
            "Streamside cleared gap — restoring riparian vegetation could strengthen both habitat "
            "and landscape connectivity."
        ),
        "INVESTIGATE": (
            "Metrics suggest ecological interest near protected land or the reserve; field assessment "
            "is needed before any conclusion."
        ),
    }
    base = templates.get(opp_type, templates["INVESTIGATE"])
    extras = []
    if pd.notna(row.get("dist_to_core_m")) and row.get("dist_to_core_m") is not None:
        extras.append(f"Nearest core habitat ~{float(row['dist_to_core_m']):.0f} m")
    if pd.notna(row.get("dist_to_stream_m")) and row.get("dist_to_stream_m") is not None:
        extras.append(f"Nearest waterway ~{float(row['dist_to_stream_m']):.0f} m")
    if extras:
        return base + " " + "; ".join(extras) + "."
    return base


def main() -> None:
    settings = load_settings()
    paths = settings["resolved_paths"]
    crs = str(settings["study_area"]["crs_analysis"])
    logger = setup_logging(paths["logs_dir"], name="phase5_opportunity_areas", level="INFO")
    ensure_dirs(paths["interim_dir"], paths["reports_dir"], paths["csv_dir"], paths["geojson_dir"])

    master = paths["gpkg_dir"] / str(settings.get("outputs", {}).get("master_gpkg", "robertson_conservation.gpkg"))
    logger.info("=== Phase 5: Ecological Opportunity Areas ===")

    grid = gpd.read_file(master, layer="analysis_grid_metrics")
    rainforest = gpd.read_file(master, layer="rainforest_patches")
    gaps = gpd.read_file(master, layer="habitat_connection_opportunities")
    reserve = gpd.read_file(master, layer="robertson_nature_reserve")

    grid = to_analysis_crs(grid, crs)
    # Candidate cells: any unweighted opportunity flag
    flag_cols = [
        c
        for c in (
            "riparian_gap",
            "patch_gap_edge",
            "isolated_patch_context",
            "near_core",
            "near_reserve",
            "near_protected",
            "on_cleared",
            "on_core",
            "on_public_land",
            "plantable_slope",
        )
        if c in grid.columns
    ]
    mask = False
    for c in flag_cols:
        mask = mask | (grid[c] == True)  # noqa: E712
    cand = grid.loc[mask].copy() if not isinstance(mask, bool) else grid.iloc[0:0].copy()
    logger.info("Candidate cells: %s / %s", len(cand), len(grid))

    if cand.empty:
        raise RuntimeError("No opportunity candidate cells found in analysis_grid_metrics")

    # Focus story area: within ~3.5 km of reserve (Action view scale) + keep public/near-core elsewhere lightly
    reserve = to_analysis_crs(reserve, crs)
    rgeom = unary_union(list(reserve.geometry))
    cand["dist_to_reserve_edge_m"] = cand.geometry.distance(rgeom)
    focus = cand[cand["dist_to_reserve_edge_m"] <= 3500].copy()
    if len(focus) < 50:
        focus = cand.copy()

    focus["opportunity_type"] = focus.apply(_assign_type, axis=1)

    # Dissolve by type into areas, then explode
    parts = []
    for opp_type, sub in focus.groupby("opportunity_type"):
        try:
            d = sub.dissolve().explode(index_parts=False, ignore_index=True)
        except Exception:
            d = sub.copy()
        d["opportunity_type"] = opp_type
        parts.append(d)
    areas = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=crs)
    areas["area_ha"] = areas.geometry.area / 10000.0
    # Drop tiny slivers; keep story-useful pieces
    areas = areas[areas["area_ha"] >= 0.25].copy()
    areas = areas.sort_values("area_ha", ascending=False).head(250).reset_index(drop=True)
    areas["area_id"] = [f"AREA_{i:03d}" for i in range(1, len(areas) + 1)]

    # Metrics for Parcel Explorer
    rf = to_analysis_crs(rainforest, crs)
    rf_tree = rf.sindex if not rf.empty else None
    gap = to_analysis_crs(gaps, crs) if gaps is not None and not gaps.empty else None

    native_cols_present = [c for c in ("on_core",) if c in focus.columns]

    records = []
    for idx, row in areas.iterrows():
        geom = row.geometry
        # existing veg approx: share of intersecting focus cells that are on_core
        cells = focus[focus.intersects(geom)]
        if len(cells) and "on_core" in cells.columns:
            veg_frac = float(cells["on_core"].mean())
            existing_veg_ha = round(float(row["area_ha"]) * veg_frac, 3)
        else:
            existing_veg_ha = 0.0

        # nearest rainforest remnant
        nearest_rf_m = None
        if rf_tree is not None and not rf.empty:
            cand_i = list(rf_tree.intersection(geom.bounds))
            best = None
            for j in cand_i:
                d = geom.distance(rf.geometry.iloc[j])
                if best is None or d < best:
                    best = d
            if best is None:
                # fallback global min on sample
                nearest_rf_m = float(rf.distance(geom).min())
            else:
                nearest_rf_m = float(best)

        # patches nearby: rainforest patches within 500 m
        patches_nearby = 0
        if not rf.empty:
            patches_nearby = int(rf.geometry.distance(geom).le(500).sum())

        # potential habitat connected: from overlapping gap opportunities if any
        pot_ha = None
        if gap is not None and not gap.empty:
            ghit = gap[gap.intersects(geom.buffer(30))]
            if not ghit.empty and "habitat_potentially_connected_ha" in ghit.columns:
                pot_ha = float(pd.to_numeric(ghit["habitat_potentially_connected_ha"], errors="coerce").max())

        # waterway
        dist_stream = None
        if "dist_to_stream_m" in cells.columns and len(cells):
            dist_stream = float(cells["dist_to_stream_m"].median())

        # biodiversity
        n_spp = None
        thr_ctx = False
        if "n_species" in cells.columns and len(cells):
            n_spp = int(round(float(cells["n_species"].max())))
        for tc in ("n_threatened_species", "n_threat_species"):
            if tc in cells.columns and len(cells):
                thr_ctx = bool(cells[tc].fillna(0).max() > 0)

        # representative cell for type narrative
        sample_row = cells.iloc[0].to_dict() if len(cells) else row.to_dict()
        why = _why(str(row["opportunity_type"]), sample_row)

        records.append(
            {
                "area_id": row["area_id"],
                "opportunity_type": row["opportunity_type"],
                "area_ha": round(float(row["area_ha"]), 3),
                "existing_vegetation_ha": existing_veg_ha,
                "nearest_rainforest_remnant_m": None if nearest_rf_m is None else round(nearest_rf_m, 1),
                "habitat_patches_nearby": patches_nearby,
                "potential_habitat_connected_ha": None if pot_ha is None or np.isnan(pot_ha) else round(pot_ha, 2),
                "waterway_distance_m": None if dist_stream is None or np.isnan(dist_stream) else round(dist_stream, 1),
                "native_species_recorded_nearby": n_spp,
                "threatened_species_context": thr_ctx,
                "on_public_land_any": bool(cells["on_public_land"].any())
                if len(cells) and "on_public_land" in cells.columns
                else False,
                "why_it_matters": why,
                "language_note": (
                    "Ecological opportunity for conversation — not an acquisition target or land-use decision."
                ),
                "evidence_tag": "CALCULATED",
                "geometry": geom,
            }
        )

    out = gpd.GeoDataFrame(records, geometry="geometry", crs=crs)
    out["generated_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    gpkg = paths["interim_dir"] / "phase5_opportunity_areas.gpkg"
    write_gdf(out, gpkg, layer="ecological_opportunity_areas")
    write_gdf(out, master, layer="ecological_opportunity_areas")
    processed = paths["processed_dir"] / master.name
    if processed.is_file():
        write_gdf(out, processed, layer="ecological_opportunity_areas")

    out.drop(columns="geometry").to_csv(
        paths["csv_dir"] / "ecological_opportunity_areas.csv", index=False
    )
    # Parcel explorer JSON for web prototype
    explorer = {
        "generated_at_utc": out["generated_at_utc"].iloc[0],
        "count": int(len(out)),
        "privacy": "Anonymous AREA_IDs only — no owner names or parcel contacts",
        "areas": out.drop(columns="geometry").to_dict(orient="records"),
    }
    (paths["csv_dir"] / "parcel_explorer.json").write_text(
        json.dumps(explorer, indent=2, default=str), encoding="utf-8"
    )

    try:
        art = out.copy()
        art["geometry"] = art.geometry.simplify(8)
        art.to_crs("EPSG:4326").to_file(
            paths["geojson_dir"] / "ecological_opportunity_areas.geojson", driver="GeoJSON"
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("GeoJSON failed: %s", exc)

    counts = out["opportunity_type"].value_counts().to_dict()
    md = f"""# Phase 5 complete — Ecological Opportunity Areas

**Date:** {out['generated_at_utc'].iloc[0][:10]}  
**Status:** Complete for review

## Philosophy

GIS identifies **ecological opportunities**, not land-use decisions.  
Public IDs are anonymous (`AREA_001` …). No owner names.

## Types

{counts}

## Deliverables

- Master layer `ecological_opportunity_areas`
- `outputs/csv/ecological_opportunity_areas.csv`
- `outputs/csv/parcel_explorer.json` (Parcel Explorer payload)
- `outputs/geojson/ecological_opportunity_areas.geojson`
- `src/14_prepare_opportunity_areas.py`

## Parcel Explorer fields (all calculated)

area_id, existing_vegetation_ha, nearest_rainforest_remnant_m, habitat_patches_nearby,
potential_habitat_connected_ha, waterway_distance_m, native_species_recorded_nearby,
threatened_species_context, opportunity_type, why_it_matters

## Cartographic art

Soft dawn-gold outlines by type; never solid “target” fills. Click reveals a quiet card.

## Next

Phase 6 — StoryMap web prototype (12 chapters, cartographic art).
"""
    (paths["reports_dir"] / "PHASE5_COMPLETE.md").write_text(md, encoding="utf-8")
    logger.info("Phase 5 complete: %s areas %s", len(out), counts)


if __name__ == "__main__":
    main()
