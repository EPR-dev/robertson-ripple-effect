"""
Phase 5 — The Ripple (landscape functions).

Hydro + riparian proximity, DEM/slope/aspect, soils, geology, bushfire prone land.
All outputs labelled as association / potential function — not reserve causation.
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
from prepare_landscape import (  # noqa: E402
    ASSOCIATION_NOTE,
    clip_dem_and_derivatives,
    clip_polygons,
    download_copernicus_dem,
    dominant_polygon_attribute,
    flag_basalt_units,
    landscape_summaries,
    sample_raster_at_points,
    tag_association,
)
from prepare_water import (  # noqa: E402
    add_riparian_metrics_to_grid,
    build_riparian_buffers,
    clip_hydro,
    hydro_summary,
)
from utils import (  # noqa: E402
    append_qa_rows,
    arcgis_query_geojson,
    basic_vector_qa,
    ensure_dirs,
    setup_logging,
    write_gdf,
)


def _cache_or_download(
    query_url: str,
    aoi_wgs: gpd.GeoDataFrame,
    *,
    out_path: Path,
    layer_name: str,
    logger,
    page_size: int = 1000,
) -> gpd.GeoDataFrame:
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
    dl = settings["downloads"]
    land_cfg = settings.get("landscape", {})
    crs = str(study_cfg["crs_analysis"])
    buffers = list(land_cfg.get("riparian_buffers_m") or [50, 100])

    logger = setup_logging(
        paths["logs_dir"],
        name="phase5_ripple",
        level=str(settings.get("logging", {}).get("level", "INFO")),
    )
    ensure_dirs(
        paths["raw_dir"],
        paths["interim_dir"],
        paths["reports_dir"],
        paths["raster_dir"],
    )

    phase1 = paths["interim_dir"] / str(
        settings.get("outputs", {}).get("phase1_interim_gpkg", "phase1_foundation.gpkg")
    )
    phase3 = paths["interim_dir"] / str(
        settings.get("outputs", {}).get("phase3_interim_gpkg", "phase3_refuge.gpkg")
    )
    if not phase1.is_file():
        raise FileNotFoundError(f"Phase 1 GPKG missing: {phase1}")

    logger.info("=== Phase 5: The Ripple (landscape functions) ===")
    logger.info(ASSOCIATION_NOTE)

    study_area = gpd.read_file(phase1, layer="study_area")
    reserve = gpd.read_file(phase1, layer="robertson_nature_reserve")
    aoi_wgs = study_area.to_crs("EPSG:4326")

    if phase3.is_file():
        grid = gpd.read_file(phase3, layer="analysis_grid")
        logger.info("Loaded analysis grid from Phase 3: %s cells", len(grid))
    else:
        from clean_species_data import build_analysis_grid

        grid = build_analysis_grid(
            study_area,
            cell_size_m=float(settings.get("grid", {}).get("cell_size_m", 250)),
            crs_analysis=crs,
        )
        logger.info("Built analysis grid: %s cells", len(grid))

    raw = paths["raw_dir"]

    # --- Downloads ---
    hydro_lines_raw = _cache_or_download(
        dl["hydroline_query"],
        aoi_wgs,
        out_path=raw / "water" / "hydroline_aoi_raw.gpkg",
        layer_name="hydroline",
        logger=logger,
        page_size=1000,
    )
    hydro_areas_raw = _cache_or_download(
        dl["hydroarea_query"],
        aoi_wgs,
        out_path=raw / "water" / "hydroarea_aoi_raw.gpkg",
        layer_name="hydroarea",
        logger=logger,
        page_size=1000,
    )
    named_raw = _cache_or_download(
        dl["named_watercourse_query"],
        aoi_wgs,
        out_path=raw / "water" / "named_watercourse_aoi_raw.gpkg",
        layer_name="named_watercourse",
        logger=logger,
        page_size=500,
    )
    soils_raw = _cache_or_download(
        dl["soil_landscapes_query"],
        aoi_wgs,
        out_path=raw / "soils" / "soil_landscapes_aoi_raw.gpkg",
        layer_name="soil_landscapes",
        logger=logger,
        page_size=200,
    )
    geology_raw = _cache_or_download(
        dl["geology_rock_units_query"],
        aoi_wgs,
        out_path=raw / "geology" / "geology_rock_units_aoi_raw.gpkg",
        layer_name="geology_rock_units",
        logger=logger,
        page_size=200,
    )
    fire_raw = _cache_or_download(
        dl["bushfire_prone_query"],
        aoi_wgs,
        out_path=raw / "fire" / "bushfire_prone_aoi_raw.gpkg",
        layer_name="bushfire_prone",
        logger=logger,
        page_size=500,
    )

    # --- Vector prep ---
    hydro_lines = clip_hydro(hydro_lines_raw, study_area, crs_analysis=crs)
    hydro_areas = clip_hydro(hydro_areas_raw, study_area, crs_analysis=crs)
    named = clip_hydro(named_raw, study_area, crs_analysis=crs)
    riparian = build_riparian_buffers(hydro_lines, buffers_m=buffers, crs_analysis=crs)

    soils = clip_polygons(soils_raw, study_area, crs_analysis=crs)
    geology = flag_basalt_units(clip_polygons(geology_raw, study_area, crs_analysis=crs))
    fire = clip_polygons(fire_raw, study_area, crs_analysis=crs)

    # --- DEM ---
    dem_tile = paths["raw_dir"] / "terrain" / "copernicus_glo30_aoi.tif"
    dem_tile = download_copernicus_dem(
        aoi_wgs,
        url_template=str(dl["dem_copernicus_template"]),
        out_path=dem_tile,
        logger=logger,
    )
    dem_dir = paths["raster_dir"] / "phase5"
    dem_paths = clip_dem_and_derivatives(
        dem_tile,
        study_area,
        crs_analysis=crs,
        out_dir=dem_dir,
        logger=logger,
    )

    # --- Grid metrics ---
    landscape_grid = add_riparian_metrics_to_grid(
        grid, hydro_lines, buffers_m=buffers, crs_analysis=crs
    )
    cents = landscape_grid.copy()
    cents["geometry"] = cents.geometry.centroid
    landscape_grid["elev_m"] = sample_raster_at_points(dem_paths["dem"], cents, value_name="elev_m")
    landscape_grid["slope_deg"] = sample_raster_at_points(
        dem_paths["slope"], cents, value_name="slope_deg"
    )
    landscape_grid["aspect_deg"] = sample_raster_at_points(
        dem_paths["aspect"], cents, value_name="aspect_deg"
    )
    landscape_grid = dominant_polygon_attribute(
        landscape_grid, soils, attr="NAME", out_col="soil_landscape", crs_analysis=crs
    )
    geo_attr = "Unit_Name" if "Unit_Name" in geology.columns else None
    if geo_attr:
        landscape_grid = dominant_polygon_attribute(
            landscape_grid, geology, attr=geo_attr, out_col="geology_unit", crs_analysis=crs
        )
    fire_attr = "d_category" if "d_category" in fire.columns else None
    if fire_attr:
        landscape_grid = dominant_polygon_attribute(
            landscape_grid, fire, attr=fire_attr, out_col="bushfire_category", crs_analysis=crs
        )
    landscape_grid["interpretation"] = ASSOCIATION_NOTE

    # --- Reports ---
    hydro_summary(hydro_lines, hydro_areas).to_csv(
        paths["reports_dir"] / "phase5_hydro_summary.csv", index=False
    )
    summaries = landscape_summaries(soils, geology, fire)
    for key, frame in summaries.items():
        frame.to_csv(paths["reports_dir"] / f"phase5_{key}_summary.csv", index=False)

    note = paths["reports_dir"] / "phase5_association_note.md"
    note.write_text(
        f"""# Phase 5 — Association / potential function (not causation)

{ASSOCIATION_NOTE}

## What these layers support
- **Hydro / riparian** — moisture and corridor context; distance-to-stream on the 250 m grid
- **Soils / geology** — why rainforest may occur here (e.g. basalt association flags), not proof of reserve impact
- **DEM / slope / aspect** — terrain context (Copernicus GLO-30 ~30 m; not LiDAR)
- **Bush fire prone land** — planning risk categories (RFS), not fire history severity

## Explicitly not claimed
- Reserve-driven regional climate change
- Causation from Robertson Nature Reserve to landscape pattern
- Fine-scale site soil survey or engineering slope design

## Rasters
- `{dem_paths['dem']}`
- `{dem_paths['slope']}`
- `{dem_paths['aspect']}`

DEA canopy/NDVI left optional (`downloads.dea_enabled`, currently false).
""",
        encoding="utf-8",
    )

    out_gpkg = paths["interim_dir"] / str(
        settings.get("outputs", {}).get("phase5_interim_gpkg", "phase5_ripple.gpkg")
    )
    if out_gpkg.is_file():
        out_gpkg.unlink()

    layers = {
        "study_area": study_area.to_crs(crs),
        "robertson_nature_reserve": reserve.to_crs(crs),
        "hydro_lines": hydro_lines,
        "hydro_areas": hydro_areas,
        "named_watercourses": named,
        "riparian_buffers": riparian,
        "soil_landscapes": soils,
        "geology_rock_units": geology,
        "bushfire_prone_land": fire,
        "landscape_grid": landscape_grid,
    }
    for name, gdf in layers.items():
        write_gdf(gdf, out_gpkg, layer=name)
        logger.info("Wrote %-28s %6s features", name, len(gdf))

    qa_rows = []
    for name, gdf in layers.items():
        qa_rows.extend(basic_vector_qa(gdf, f"phase5::{name}"))
    append_qa_rows(qa_rows, paths["reports_dir"] / "data_quality_report.csv")

    layer_summary = pd.DataFrame(
        [{"layer": k, "features": len(v), "crs": str(v.crs)} for k, v in layers.items()]
    )
    layer_summary.to_csv(paths["reports_dir"] / "phase5_layer_summary.csv", index=False)

    _update_sources(
        paths["data_sources_csv"],
        [
            "nsw_hydro_named",
            "dem_ga",
            "soil_landscapes_nsw",
            "geology_nsw",
            "fire_history_nsw",
        ],
    )

    logger.info("Phase 5 complete.")
    logger.info("Interim GPKG: %s", out_gpkg)
    logger.info("Rasters: %s", dem_dir)
    logger.info("Summary:\n%s", layer_summary.to_string(index=False))


if __name__ == "__main__":
    main()
