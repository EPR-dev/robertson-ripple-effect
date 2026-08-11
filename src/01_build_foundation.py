"""
Phase 1 orchestrator — download foundation layers, build AOIs, export interim GPKG.

Deliverables in data/interim/phase1_foundation.gpkg:
  - study_area
  - context_aoi
  - robertson_nature_reserve
  - protected_areas
  - lga
  - roads
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

from clean_vector_data import (  # noqa: E402
    build_context_aoi,
    build_study_area,
    clip_to_aoi,
    extract_reserve,
    select_context_reserves,
    standardise_reserve_columns,
)
from config import load_settings  # noqa: E402
from download_data import (  # noqa: E402
    download_lga_for_aoi,
    download_npws_estate_for_aoi,
    download_reserve,
    download_roads_for_aoi,
)
from utils import ensure_dirs, setup_logging, to_analysis_crs, write_gdf  # noqa: E402
from validate_data import validate_foundation_layers  # noqa: E402


def _update_data_sources_download_dates(csv_path: Path, dataset_ids: list[str]) -> None:
    if not csv_path.is_file():
        return
    df = pd.read_csv(csv_path)
    if "dataset_id" not in df.columns or "download_date" not in df.columns:
        return
    today = date.today().isoformat()
    mask = df["dataset_id"].isin(dataset_ids)
    df.loc[mask, "download_date"] = today
    df.loc[mask, "status"] = "Downloaded"
    df.to_csv(csv_path, index=False)


def main() -> None:
    settings = load_settings()
    paths = settings["resolved_paths"]
    study = settings["study_area"]
    crs = str(study["crs_analysis"])
    crs_geo = str(study["crs_geographic"])
    logger = setup_logging(
        paths["logs_dir"],
        name="phase1_foundation",
        level=str(settings.get("logging", {}).get("level", "INFO")),
    )
    ensure_dirs(paths["raw_dir"], paths["interim_dir"], paths["reports_dir"])

    logger.info("=== Phase 1: foundation download + AOI ===")

    # 1) Reserve first
    reserve_path = download_reserve(settings, logger)
    reserve = gpd.read_file(reserve_path, layer="robertson_nature_reserve")
    logger.info("Reserve loaded: %s CRS=%s", list(reserve.get("NAME", [])), reserve.crs)

    # 2) Study area from reserve buffer
    study_area = build_study_area(reserve, float(study["buffer_km"]), crs)
    logger.info(
        "Study area built: buffer=%skm area=%.1f km^2",
        study["buffer_km"],
        study_area.geometry.area.iloc[0] / 1_000_000.0,
    )

    # Provisional context AOI = study area (before we know nearby parks)
    provisional_aoi_wgs84 = study_area.to_crs(crs_geo)

    # 3) Estate features in/near AOI
    estate_path = download_npws_estate_for_aoi(settings, provisional_aoi_wgs84, logger)
    estate = gpd.read_file(estate_path, layer="npws_estate")
    logger.info("NPWS Estate in AOI envelope: %s features", len(estate))

    # Ensure exact reserve extract from estate (or fall back to reserve download)
    try:
        reserve = extract_reserve(estate, str(study["primary_reserve_name"]))
    except ValueError:
        logger.warning("Reserve missing from AOI estate extract; using dedicated reserve download")
        reserve = gpd.read_file(reserve_path, layer="robertson_nature_reserve")

    context_reserves = select_context_reserves(
        estate,
        list(study.get("context_reserve_patterns") or []),
        logger=logger,
    )
    context_aoi = build_context_aoi(
        study_area,
        context_reserves,
        float(study.get("context_halo_km", 1.0)),
        crs,
    )
    logger.info(
        "Context AOI area=%.1f km^2 (%s context reserves)",
        context_aoi.geometry.area.iloc[0] / 1_000_000.0,
        len(context_reserves),
    )

    # 4) LGA + roads for context AOI
    aoi_wgs84 = context_aoi.to_crs(crs_geo)
    lga_path = download_lga_for_aoi(settings, aoi_wgs84, logger)
    roads_path = download_roads_for_aoi(settings, aoi_wgs84, logger)
    lga = gpd.read_file(lga_path, layer="lga")
    roads = gpd.read_file(roads_path, layer="roads")

    # 5) Standardise / clip
    reserve_std = standardise_reserve_columns(to_analysis_crs(reserve, crs))
    protected = standardise_reserve_columns(clip_to_aoi(estate, context_aoi, crs))
    lga_clip = clip_to_aoi(lga, context_aoi, crs)
    roads_clip = clip_to_aoi(roads, context_aoi, crs)

    reserve_std = reserve_std.copy()
    reserve_std["area_ha_calc"] = reserve_std.geometry.area / 10000.0
    protected = protected.copy()
    protected["area_ha_calc"] = protected.geometry.area / 10000.0
    if not roads_clip.empty:
        roads_clip = roads_clip.copy()
        roads_clip["length_m"] = roads_clip.geometry.length

    out_gpkg = paths["interim_dir"] / str(
        settings.get("outputs", {}).get("phase1_interim_gpkg", "phase1_foundation.gpkg")
    )
    if out_gpkg.is_file():
        out_gpkg.unlink()

    layers = {
        "study_area": study_area,
        "context_aoi": context_aoi,
        "robertson_nature_reserve": reserve_std,
        "protected_areas": protected,
        "lga": lga_clip,
        "roads": roads_clip,
    }
    for layer_name, gdf in layers.items():
        write_gdf(gdf, out_gpkg, layer=layer_name)
        logger.info("Wrote layer %-28s %5s features", layer_name, len(gdf))

    qa_path = paths["reports_dir"] / "data_quality_report.csv"
    if qa_path.is_file():
        qa_path.unlink()
    validate_foundation_layers(
        layers,
        qa_path=qa_path,
        study_area=study_area,
        crs_analysis=crs,
        logger=logger,
        context_aoi=context_aoi,
    )

    _update_data_sources_download_dates(
        paths["data_sources_csv"],
        ["npws_estate", "wingecarribee_lga", "roads_nsw"],
    )

    summary = pd.DataFrame(
        [{"layer": k, "features": len(v), "crs": str(v.crs)} for k, v in layers.items()]
    )
    summary_path = paths["reports_dir"] / "phase1_layer_summary.csv"
    summary.to_csv(summary_path, index=False)
    logger.info("Phase 1 complete.")
    logger.info("Interim GPKG: %s", out_gpkg)
    logger.info("QA report:    %s", qa_path)
    logger.info("Summary:\n%s", summary.to_string(index=False))


if __name__ == "__main__":
    main()
