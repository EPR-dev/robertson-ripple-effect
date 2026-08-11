"""
Phase 6 — The Opportunity (unweighted components).

Map restoration / protection opportunity factors independently on the 250 m grid.
No weighted index is computed.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(__file__).resolve().parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from config import load_settings  # noqa: E402
from prepare_restoration import (  # noqa: E402
    COMPONENT_DEFS,
    NO_WEIGHTS_NOTE,
    build_opportunity_components,
    component_summary,
    export_component_polygon_collection,
)
from utils import (  # noqa: E402
    append_qa_rows,
    arcgis_query_geojson,
    basic_vector_qa,
    ensure_dirs,
    setup_logging,
    write_gdf,
)


def _cache_or_download(query_url: str, aoi_wgs, *, out_path: Path, layer_name: str, logger, page_size: int = 500):
    ensure_dirs(out_path.parent)
    if out_path.is_file() and out_path.stat().st_size > 0:
        logger.info("Cache hit: %s", out_path)
        return gpd.read_file(out_path, layer=layer_name)
    geom = unary_union(list(aoi_wgs.geometry))
    gdf = arcgis_query_geojson(
        query_url,
        geometry=geom,
        in_sr=4326,
        out_sr=4326,
        page_size=page_size,
        logger=logger,
    )
    write_gdf(gdf, out_path, layer=layer_name)
    logger.info("Saved %s: %s -> %s", layer_name, len(gdf), out_path)
    return gdf


def _update_sources(csv_path: Path, dataset_ids: list[str]) -> None:
    if not csv_path.is_file():
        return
    df = pd.read_csv(csv_path)
    today = date.today().isoformat()
    mask = df["dataset_id"].isin(dataset_ids)
    df.loc[mask, "download_date"] = today
    df.loc[mask, "status"] = "Downloaded"
    df.to_csv(csv_path, index=False)


def main() -> None:
    settings = load_settings()
    paths = settings["resolved_paths"]
    study_cfg = settings["study_area"]
    opp = settings.get("opportunity", {})
    dl = settings["downloads"]
    crs = str(study_cfg["crs_analysis"])

    logger = setup_logging(
        paths["logs_dir"],
        name="phase6_opportunity",
        level=str(settings.get("logging", {}).get("level", "INFO")),
    )
    ensure_dirs(paths["raw_dir"], paths["interim_dir"], paths["reports_dir"])

    phase1 = paths["interim_dir"] / str(settings["outputs"]["phase1_interim_gpkg"])
    phase2 = paths["interim_dir"] / str(settings["outputs"]["phase2_interim_gpkg"])
    phase4 = paths["interim_dir"] / str(settings["outputs"]["phase4_interim_gpkg"])
    phase5 = paths["interim_dir"] / str(settings["outputs"]["phase5_interim_gpkg"])
    for p in (phase1, phase2, phase4, phase5):
        if not p.is_file():
            raise FileNotFoundError(f"Required interim GPKG missing: {p}")

    logger.info("=== Phase 6: The Opportunity (unweighted components) ===")
    logger.info(NO_WEIGHTS_NOTE)

    study_area = gpd.read_file(phase1, layer="study_area")
    reserve = gpd.read_file(phase1, layer="robertson_nature_reserve")
    protected = gpd.read_file(phase1, layer="protected_areas")
    cleared = gpd.read_file(phase2, layer="cleared_or_non_native")
    core = gpd.read_file(phase4, layer="core_habitat_patches")
    landscape_grid = gpd.read_file(phase5, layer="landscape_grid")
    geology = gpd.read_file(phase5, layer="geology_rock_units")
    basalt = (
        geology.loc[geology["is_basalt_or_volcanic"]].copy()
        if "is_basalt_or_volcanic" in geology.columns
        else geology.iloc[0:0].copy()
    )

    aoi_wgs = study_area.to_crs("EPSG:4326")
    crown_raw = _cache_or_download(
        dl["crown_land_query"],
        aoi_wgs,
        out_path=paths["raw_dir"] / "tenure" / "crown_land_aoi_raw.gpkg",
        layer_name="crown_land",
        logger=logger,
        page_size=500,
    )
    # Clip crown to study
    crown = crown_raw.to_crs(crs)
    try:
        crown = gpd.clip(crown, study_area.to_crs(crs))
    except Exception:
        union = unary_union(list(study_area.to_crs(crs).geometry))
        crown = crown.loc[crown.intersects(union)].copy()
    crown["interpretation"] = "Crown land tenure context for public-land opportunity — not a score."

    opportunity_grid = build_opportunity_components(
        landscape_grid,
        protected_areas=protected,
        reserve=reserve,
        core_patches=core,
        cleared=cleared,
        crown_land=crown,
        basalt_geology=basalt,
        crs_analysis=crs,
        near_protected_m=float(opp.get("near_protected_m", 500)),
        near_core_m=float(opp.get("near_core_m", 250)),
        near_reserve_m=float(opp.get("near_reserve_m", 1000)),
        isolated_nn_m=float(opp.get("isolated_nn_m", 200)),
        isolated_influence_m=float(opp.get("isolated_influence_m", 500)),
        plantable_slope_deg=float(opp.get("plantable_slope_deg", 15)),
    )
    logger.info("Opportunity grid cells: %s", len(opportunity_grid))

    summary = component_summary(opportunity_grid)
    summary.to_csv(paths["reports_dir"] / "phase6_component_summary.csv", index=False)

    # Dissolved candidate polygons for key story components (still unweighted)
    polygon_components = [
        "riparian_gap",
        "patch_gap_edge",
        "isolated_patch_context",
        "near_protected",
        "on_public_land",
        "on_basalt_volcanic",
    ]
    component_polys = export_component_polygon_collection(
        opportunity_grid,
        components=polygon_components,
        crs_analysis=crs,
    )

    # High-interest intersection examples (still NOT a weighted score — diagnostic only)
    diagnostic = opportunity_grid.copy()
    diagnostic["diag_riparian_public"] = (
        diagnostic["riparian_gap"] & diagnostic["on_public_land"]
    )
    diagnostic["diag_edge_basalt"] = (
        diagnostic["patch_gap_edge"] & diagnostic["on_basalt_volcanic"]
    )
    diag_summary = pd.DataFrame(
        [
            {
                "diagnostic": "riparian_gap AND on_public_land",
                "true_cells": int(diagnostic["diag_riparian_public"].sum()),
                "note": "Intersection for exploration only — not an index weight",
            },
            {
                "diagnostic": "patch_gap_edge AND on_basalt_volcanic",
                "true_cells": int(diagnostic["diag_edge_basalt"].sum()),
                "note": "Intersection for exploration only — not an index weight",
            },
        ]
    )
    diag_summary.to_csv(paths["reports_dir"] / "phase6_diagnostic_intersections.csv", index=False)

    rules = paths["reports_dir"] / "phase6_opportunity_rules.md"
    thresh = {
        "near_protected_m": opp.get("near_protected_m", 500),
        "near_core_m": opp.get("near_core_m", 250),
        "near_reserve_m": opp.get("near_reserve_m", 1000),
        "isolated_nn_m": opp.get("isolated_nn_m", 200),
        "isolated_influence_m": opp.get("isolated_influence_m", 500),
        "plantable_slope_deg": opp.get("plantable_slope_deg", 15),
    }
    comp_table = "\n".join(f"| `{n}` | {d} |" for n, d in COMPONENT_DEFS)
    rules.write_text(
        f"""# Phase 6 — Unweighted opportunity components

{NO_WEIGHTS_NOTE}

## Thresholds (from `config/settings.yaml`)

| Parameter | Value |
|-----------|-------|
| near_protected_m | {thresh['near_protected_m']} |
| near_core_m | {thresh['near_core_m']} |
| near_reserve_m | {thresh['near_reserve_m']} |
| isolated_nn_m | {thresh['isolated_nn_m']} |
| isolated_influence_m | {thresh['isolated_influence_m']} |
| plantable_slope_deg | {thresh['plantable_slope_deg']} |

## Components

| Field | Meaning |
|-------|---------|
{comp_table}

## Continuous fields
- `dist_to_protected_m`, `dist_to_reserve_m`, `dist_to_core_m`, `dist_to_isolated_core_m`
- Plus carried Phase 5: `dist_to_stream_m`, `slope_deg`, `elev_m`

## Outputs
- `opportunity_grid` — cell-level flags/distances
- `component_polygons` — dissolved areas for selected components
- `crown_land` — clipped Crown land tenure
- Diagnostic intersections CSV — **not** an index

## Next (not this phase)
- ArcGIS / analyst-approved weights → Restoration Opportunity Index
- Scenario B restoration targeting using these components + corridor products
""",
        encoding="utf-8",
    )

    out_gpkg = paths["interim_dir"] / str(
        settings.get("outputs", {}).get("phase6_interim_gpkg", "phase6_opportunity.gpkg")
    )
    if out_gpkg.is_file():
        out_gpkg.unlink()

    layers = {
        "study_area": study_area.to_crs(crs),
        "robertson_nature_reserve": reserve.to_crs(crs),
        "opportunity_grid": opportunity_grid,
        "component_polygons": component_polys,
        "crown_land": crown,
    }
    for name, gdf in layers.items():
        write_gdf(gdf, out_gpkg, layer=name)
        logger.info("Wrote %-28s %6s features", name, len(gdf))

    qa_rows = []
    for name, gdf in layers.items():
        qa_rows.extend(basic_vector_qa(gdf, f"phase6::{name}"))
    append_qa_rows(qa_rows, paths["reports_dir"] / "data_quality_report.csv")

    layer_summary = pd.DataFrame(
        [{"layer": k, "features": len(v), "crs": str(v.crs)} for k, v in layers.items()]
    )
    layer_summary.to_csv(paths["reports_dir"] / "phase6_layer_summary.csv", index=False)

    _update_sources(paths["data_sources_csv"], ["public_land_crown", "restoration_candidates"])

    logger.info("Phase 6 complete.")
    logger.info("Interim GPKG: %s", out_gpkg)
    logger.info("Component summary:\n%s", summary.to_string(index=False))


if __name__ == "__main__":
    main()
