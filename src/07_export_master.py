"""
Phase 7 — Grid compilation & master export.

Compile the 250 m metrics grid; build robertson_conservation.gpkg, key GeoJSON/CSV,
refresh QA inventory, and write ArcGIS handoff notes.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(__file__).resolve().parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from config import load_settings  # noqa: E402
from export_arcgis import (  # noqa: E402
    compile_master_grid,
    copy_layer,
    export_geojson_subset,
    export_grid_csv,
    layer_inventory,
    write_master_gpkg,
)
from utils import append_qa_rows, basic_vector_qa, ensure_dirs, setup_logging  # noqa: E402


def _safe_layer(gpkg: Path, layer: str, crs: str, logger) -> gpd.GeoDataFrame | None:
    try:
        return copy_layer(gpkg, layer, crs_analysis=crs)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Skip %s::%s (%s)", gpkg.name, layer, exc)
        return None


def _write_handoff(path: Path, master_path: Path, grid_csv: Path, raster_dir: Path) -> None:
    path.write_text(
        f"""# ArcGIS handoff — The Ripple Effect (Phase 7)

**Date:** {date.today().isoformat()}  
**Master GeoPackage:** `{master_path}`  
**Compiled grid CSV:** `{grid_csv}`  
**Terrain rasters:** `{raster_dir}`

## What Python prep has delivered

| Story beat | Key layers in master GPKG |
|------------|---------------------------|
| Reserve / AOI | `study_area`, `context_aoi`, `robertson_nature_reserve`, `protected_areas`, `lga`, `roads` |
| Remnant | `native_vegetation`, `rainforest_extant`, `wet_sclerophyll_extant`, `rainforest_preclear_modelled`, `cleared_or_non_native` |
| Refuge | `species_observations_clean`, `threatened_species_aggregated`, biodiv fields on `analysis_grid_metrics` |
| Network | `habitat_patches`, `core_habitat_patches`, `rainforest_patches`, `roads_barriers` |
| Ripple | `hydro_lines`, `hydro_areas`, `riparian_buffers`, `soil_landscapes`, `geology_rock_units`, `bushfire_prone_land` |
| Opportunity | `component_polygons`, `crown_land`, opportunity flags on `analysis_grid_metrics` |

## Compiled grid (`analysis_grid_metrics`)

250 m cells with:
- Biodiversity counts / richness (public observations; effort-biased)
- Threatened/sensitive **grid aggregates only**
- Landscape: stream distance, riparian flags, elev/slope/aspect, soil, geology, fire
- Unweighted opportunity components (no ROI score)

## Your ArcGIS analysis (still required)

1. **Cost surface** from `roads_barriers.cost_hint` (+ any land costs you document)
2. **Least-cost corridors** between `core_habitat_patches`
3. **Scenario A** — habitat network with `robertson_nature_reserve` removed
4. **Scenario B** — where small restoration yields largest connectivity gain (use `riparian_gap`, `patch_gap_edge`, `isolated_patch_context`)
5. **Weighted Restoration Opportunity Index** — only after agreeing weights on Phase 6 components
6. Cartographic terrain products (optional polish beyond Python slope/aspect)

## Do not

- Treat Python `cost_hint` or opportunity flags as a finished ecological score
- Publish precise sensitive species points (use `threatened_species_aggregated`)
- Label modelled pre-clear rainforest as a surveyed Yarrawa Brush boundary
- Claim reserve-driven regional climate change

## Suggested load order in ArcGIS Pro

1. Add `{master_path.name}`
2. Symbolize story groups (Reserve → Remnant → Refuge → Network → Ripple → Opportunity)
3. Add rasters from `{raster_dir.name}/` (dem_clip, slope_deg, aspect_deg)
4. Run corridor / scenario tools; write results to `data/processed/`
5. Hand finished products to Phase 8 dashboard packaging

## QA

See `outputs/reports/data_quality_report.csv` and `outputs/reports/phase7_layer_inventory.csv`.
""",
        encoding="utf-8",
    )


def main() -> None:
    settings = load_settings()
    paths = settings["resolved_paths"]
    outs = settings.get("outputs", {})
    crs = str(settings["study_area"]["crs_analysis"])

    logger = setup_logging(
        paths["logs_dir"],
        name="phase7_export",
        level=str(settings.get("logging", {}).get("level", "INFO")),
    )
    ensure_dirs(
        paths["processed_dir"],
        paths["gpkg_dir"],
        paths["geojson_dir"],
        paths["csv_dir"],
        paths["reports_dir"],
    )

    p1 = paths["interim_dir"] / str(outs["phase1_interim_gpkg"])
    p2 = paths["interim_dir"] / str(outs["phase2_interim_gpkg"])
    p3 = paths["interim_dir"] / str(outs["phase3_interim_gpkg"])
    p4 = paths["interim_dir"] / str(outs["phase4_interim_gpkg"])
    p5 = paths["interim_dir"] / str(outs["phase5_interim_gpkg"])
    p6 = paths["interim_dir"] / str(outs["phase6_interim_gpkg"])
    for p in (p1, p2, p3, p4, p5, p6):
        if not p.is_file():
            raise FileNotFoundError(f"Missing interim GPKG: {p}")

    logger.info("=== Phase 7: Grid compilation & master export ===")

    biodiv = copy_layer(p3, "biodiversity_grid", crs_analysis=crs)
    threatened = copy_layer(p3, "threatened_species_aggregated", crs_analysis=crs)
    opportunity = copy_layer(p6, "opportunity_grid", crs_analysis=crs)

    master_grid = compile_master_grid(
        biodiversity_grid=biodiv,
        threatened_grid=threatened,
        opportunity_grid=opportunity,
        crs_analysis=crs,
    )
    logger.info("Compiled analysis_grid_metrics: %s cells, %s fields", len(master_grid), len(master_grid.columns))

    # Curated master layers (story-ready subset)
    layers: dict[str, gpd.GeoDataFrame | None] = {
        # Foundation
        "study_area": _safe_layer(p1, "study_area", crs, logger),
        "context_aoi": _safe_layer(p1, "context_aoi", crs, logger),
        "robertson_nature_reserve": _safe_layer(p1, "robertson_nature_reserve", crs, logger),
        "protected_areas": _safe_layer(p1, "protected_areas", crs, logger),
        "lga": _safe_layer(p1, "lga", crs, logger),
        "roads": _safe_layer(p1, "roads", crs, logger),
        # Remnant
        "native_vegetation": _safe_layer(p2, "native_vegetation", crs, logger),
        "rainforest_extant": _safe_layer(p2, "rainforest_extant", crs, logger),
        "wet_sclerophyll_extant": _safe_layer(p2, "wet_sclerophyll_extant", crs, logger),
        "rainforest_preclear_modelled": _safe_layer(p2, "rainforest_preclear_modelled", crs, logger),
        "cleared_or_non_native": _safe_layer(p2, "cleared_or_non_native", crs, logger),
        # Refuge
        "species_observations_clean": _safe_layer(p3, "species_observations_clean", crs, logger),
        "threatened_species_aggregated": threatened,
        # Network
        "habitat_patches": _safe_layer(p4, "habitat_patches", crs, logger),
        "core_habitat_patches": _safe_layer(p4, "core_habitat_patches", crs, logger),
        "rainforest_patches": _safe_layer(p4, "rainforest_patches", crs, logger),
        "roads_barriers": _safe_layer(p4, "roads_barriers", crs, logger),
        # Ripple
        "hydro_lines": _safe_layer(p5, "hydro_lines", crs, logger),
        "hydro_areas": _safe_layer(p5, "hydro_areas", crs, logger),
        "named_watercourses": _safe_layer(p5, "named_watercourses", crs, logger),
        "riparian_buffers": _safe_layer(p5, "riparian_buffers", crs, logger),
        "soil_landscapes": _safe_layer(p5, "soil_landscapes", crs, logger),
        "geology_rock_units": _safe_layer(p5, "geology_rock_units", crs, logger),
        "bushfire_prone_land": _safe_layer(p5, "bushfire_prone_land", crs, logger),
        # Opportunity
        "component_polygons": _safe_layer(p6, "component_polygons", crs, logger),
        "crown_land": _safe_layer(p6, "crown_land", crs, logger),
        # Compiled grid
        "analysis_grid_metrics": master_grid,
    }
    # Drop None
    layers = {k: v for k, v in layers.items() if v is not None}

    master_name = str(outs.get("master_gpkg", "robertson_conservation.gpkg"))
    master_path = paths["gpkg_dir"] / master_name
    processed_copy = paths["processed_dir"] / master_name
    write_master_gpkg(layers, master_path, logger=logger)
    # Mirror into data/processed for ArcGIS handoff folder convention
    write_master_gpkg(layers, processed_copy, logger=None)
    logger.info("Also wrote processed copy: %s", processed_copy)

    # GeoJSON subset (keep web payload manageable)
    geojson_layers = {
        "study_area": layers["study_area"],
        "robertson_nature_reserve": layers["robertson_nature_reserve"],
        "protected_areas": layers["protected_areas"],
        "core_habitat_patches": layers["core_habitat_patches"],
        "riparian_buffers": layers["riparian_buffers"],
        "component_polygons": layers["component_polygons"],
        "threatened_species_aggregated": layers["threatened_species_aggregated"],
    }
    export_geojson_subset(geojson_layers, paths["geojson_dir"], logger=logger)

    grid_csv = paths["csv_dir"] / "analysis_grid_metrics.csv"
    export_grid_csv(master_grid, grid_csv)
    logger.info("Wrote grid CSV: %s", grid_csv)

    inventory = layer_inventory(layers)
    inventory.to_csv(paths["reports_dir"] / "phase7_layer_inventory.csv", index=False)

    # Compact grid field dictionary
    field_docs = pd.DataFrame(
        [
            {"field": c, "in_master_grid": True}
            for c in master_grid.columns
            if c != "geometry"
        ]
    )
    field_docs.to_csv(paths["reports_dir"] / "phase7_grid_fields.csv", index=False)

    qa_rows = []
    for name, gdf in layers.items():
        qa_rows.extend(basic_vector_qa(gdf, f"phase7::{name}"))
    append_qa_rows(qa_rows, paths["reports_dir"] / "data_quality_report.csv")

    handoff = ROOT / "docs" / "arcgis_handoff.md"
    _write_handoff(handoff, master_path, grid_csv, paths["raster_dir"] / "phase5")
    # Also keep a reports copy
    _write_handoff(
        paths["reports_dir"] / "phase7_arcgis_handoff.md",
        master_path,
        grid_csv,
        paths["raster_dir"] / "phase5",
    )

    # Update README status lightly via a short phase7 summary report
    summary = pd.DataFrame(
        [
            {"metric": "master_layers", "value": len(layers)},
            {"metric": "grid_cells", "value": len(master_grid)},
            {"metric": "grid_fields", "value": len(master_grid.columns) - 1},
            {"metric": "master_gpkg", "value": str(master_path)},
            {"metric": "processed_gpkg", "value": str(processed_copy)},
        ]
    )
    summary.to_csv(paths["reports_dir"] / "phase7_summary.csv", index=False)

    logger.info("Phase 7 complete.")
    logger.info("Master GPKG: %s", master_path)
    logger.info("Handoff: %s", handoff)
    logger.info("Inventory:\n%s", inventory.to_string(index=False))


if __name__ == "__main__":
    main()
