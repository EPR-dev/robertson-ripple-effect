"""
Phase 2 — The Remnant.

Download SVTM extant + pre-clearing PCT Quickview for the study AOI,
build rainforest / wet sclerophyll / native / cleared contrast layers,
document PCT interest list, export phase2_remnant.gpkg.
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
from prepare_habitat import (  # noqa: E402
    build_cleared_landscape,
    filter_classified_native,
    filter_rainforest,
    filter_wet_sclerophyll,
    pct_summary_table,
    standardise_svtm_columns,
    tag_extant,
    tag_modelled_preclearing,
)
from utils import (  # noqa: E402
    append_qa_rows,
    arcgis_query_geojson,
    basic_vector_qa,
    ensure_dirs,
    setup_logging,
    to_analysis_crs,
    write_gdf,
)
def _update_sources(csv_path: Path, dataset_ids: list[str]) -> None:
    if not csv_path.is_file():
        return
    df = pd.read_csv(csv_path)
    today = date.today().isoformat()
    mask = df["dataset_id"].isin(dataset_ids)
    df.loc[mask, "download_date"] = today
    df.loc[mask, "status"] = "Downloaded"
    df.to_csv(csv_path, index=False)


def download_svtm_for_aoi(
    query_url: str,
    aoi_native_crs: gpd.GeoDataFrame,
    *,
    out_path: Path,
    layer_name: str,
    native_epsg: int,
    logger,
) -> gpd.GeoDataFrame:
    """Envelope query SVTM Quickview in native CRS, cache to raw GPKG."""
    ensure_dirs(out_path.parent)
    if out_path.is_file() and out_path.stat().st_size > 0:
        logger.info("Cache hit: %s", out_path)
        return gpd.read_file(out_path, layer=layer_name)

    geom = unary_union(list(aoi_native_crs.geometry))
    gdf = arcgis_query_geojson(
        query_url,
        where="1=1",
        out_fields="PCTID,PCTName,vegClass,vegForm",
        geometry=geom,
        in_sr=native_epsg,
        out_sr=native_epsg,
        page_size=1000,
        logger=logger,
    )
    if gdf.empty:
        logger.warning("No features returned for %s", layer_name)
    else:
        gdf = standardise_svtm_columns(gdf)
    write_gdf(gdf, out_path, layer=layer_name)
    logger.info("Saved %s: %s features -> %s", layer_name, len(gdf), out_path)
    return gdf


def precise_clip(gdf: gpd.GeoDataFrame, aoi: gpd.GeoDataFrame, crs: str) -> gpd.GeoDataFrame:
    if gdf.empty:
        return gdf.to_crs(crs) if gdf.crs else gdf
    left = to_analysis_crs(gdf, crs)
    poly = aoi.to_crs(crs)
    try:
        clipped = gpd.clip(left, poly)
    except Exception:
        # Fallback: intersects filter only
        union = unary_union(list(poly.geometry))
        clipped = left[left.intersects(union)].copy()
    return clipped


def main() -> None:
    settings = load_settings()
    paths = settings["resolved_paths"]
    study_cfg = settings["study_area"]
    veg_cfg = settings.get("vegetation", {})
    dl = settings["downloads"]
    crs = str(study_cfg["crs_analysis"])
    native_crs = str(dl.get("svtm_native_crs", "EPSG:3308"))
    native_epsg = int(native_crs.split(":")[-1])

    logger = setup_logging(
        paths["logs_dir"],
        name="phase2_remnant",
        level=str(settings.get("logging", {}).get("level", "INFO")),
    )
    ensure_dirs(paths["raw_dir"], paths["interim_dir"], paths["reports_dir"], paths["reference_dir"])

    phase1 = paths["interim_dir"] / str(
        settings.get("outputs", {}).get("phase1_interim_gpkg", "phase1_foundation.gpkg")
    )
    if not phase1.is_file():
        raise FileNotFoundError(f"Phase 1 GPKG missing. Run 01_build_foundation.py first: {phase1}")

    logger.info("=== Phase 2: The Remnant (SVTM) ===")
    study_area = gpd.read_file(phase1, layer="study_area")
    reserve = gpd.read_file(phase1, layer="robertson_nature_reserve")
    aoi_3308 = study_area.to_crs(native_crs)

    # Downloads
    extant_raw_path = paths["raw_dir"] / "vegetation" / "svtm_extant_pct_aoi_raw.gpkg"
    preclear_raw_path = paths["raw_dir"] / "vegetation" / "svtm_preclear_pct_aoi_raw.gpkg"
    ceec_raw_path = paths["raw_dir"] / "vegetation" / "ceec_labels_aoi_raw.gpkg"

    extant_raw = download_svtm_for_aoi(
        dl["svtm_extant_pct_query"],
        aoi_3308,
        out_path=extant_raw_path,
        layer_name="svtm_extant_pct",
        native_epsg=native_epsg,
        logger=logger,
    )
    preclear_raw = download_svtm_for_aoi(
        dl["svtm_preclear_pct_query"],
        aoi_3308,
        out_path=preclear_raw_path,
        layer_name="svtm_preclear_pct",
        native_epsg=native_epsg,
        logger=logger,
    )

    # Optional TEC / CEEC labels
    try:
        ceec_raw = download_svtm_for_aoi(
            dl["ceec_labels_query"],
            aoi_3308,
            out_path=ceec_raw_path,
            layer_name="ceec_labels",
            native_epsg=native_epsg,
            logger=logger,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("CEEC download failed/unavailable: %s", exc)
        ceec_raw = gpd.GeoDataFrame(geometry=[], crs=native_crs)

    # Precise clip + analysis CRS
    extant_all = precise_clip(extant_raw, study_area, crs)
    # Native = classified PCTs only (exclude PCT 0 / Not classified mask)
    native_vegetation = filter_classified_native(extant_all)
    preclear_all = precise_clip(preclear_raw, study_area, crs)

    rainforest_extant = filter_rainforest(
        native_vegetation,
        veg_forms=list(veg_cfg.get("rainforest_veg_forms") or ["Rainforests"]),
        veg_class_contains=list(veg_cfg.get("rainforest_veg_class_contains") or ["Rainforest"]),
    )
    wet_sclerophyll_extant = filter_wet_sclerophyll(
        native_vegetation,
        veg_forms=list(veg_cfg.get("wet_sclerophyll_veg_forms") or ["Wet Sclerophyll Forests"]),
        veg_class_contains=list(
            veg_cfg.get("wet_sclerophyll_veg_class_contains") or ["Wet Sclerophyll"]
        ),
    )
    rainforest_preclear = filter_rainforest(
        preclear_all,
        veg_forms=list(veg_cfg.get("rainforest_veg_forms") or ["Rainforests"]),
        veg_class_contains=list(veg_cfg.get("rainforest_veg_class_contains") or ["Rainforest"]),
    )

    native_vegetation = tag_extant(native_vegetation)
    rainforest_extant = tag_extant(rainforest_extant)
    wet_sclerophyll_extant = tag_extant(wet_sclerophyll_extant)
    rainforest_preclear = tag_modelled_preclearing(rainforest_preclear)
    preclear_rainforest_context = rainforest_preclear  # alias clarity for export

    cleared = build_cleared_landscape(study_area, native_vegetation, crs)

    # Area fields
    for gdf in (
        native_vegetation,
        rainforest_extant,
        wet_sclerophyll_extant,
        preclear_rainforest_context,
    ):
        if not gdf.empty:
            gdf["area_ha"] = gdf.geometry.area / 10000.0

    tec = precise_clip(ceec_raw, study_area, crs) if not ceec_raw.empty else ceec_raw
    if not tec.empty and "interpretation" not in tec.columns:
        tec = tec.copy()
        tec["interpretation"] = "CEEC/TEC indicative mapping if present — confirm listing locally"

    # PCT documentation
    pct_docs = pd.concat(
        [
            pct_summary_table(rainforest_extant, layer_label="rainforest_extant"),
            pct_summary_table(wet_sclerophyll_extant, layer_label="wet_sclerophyll_extant"),
            pct_summary_table(preclear_rainforest_context, layer_label="rainforest_preclear_modelled"),
        ],
        ignore_index=True,
    )
    pct_path = paths["reference_dir"] / "pct_interest_list.csv"
    pct_docs.to_csv(pct_path, index=False)
    logger.info("Wrote PCT interest list: %s (%s rows)", pct_path, len(pct_docs))

    # Formation summary for full extant clip (includes Not classified)
    if not extant_all.empty:
        form_summary = (
            extant_all.assign(area_ha=extant_all.geometry.area / 10000.0)
            .groupby("veg_form", dropna=False)["area_ha"]
            .sum()
            .sort_values(ascending=False)
            .reset_index()
        )
        form_summary.to_csv(paths["reports_dir"] / "phase2_extant_formation_summary.csv", index=False)

    # Narrative limitation note
    note_path = paths["reports_dir"] / "phase2_yarrawa_brush_limitation.md"
    note_path.write_text(
        """# Yarrawa Brush — representation limits (Phase 2)

**Do not treat any layer in `phase2_remnant.gpkg` as a digitised historic Yarrawa Brush cadastral boundary.**

## What we used instead
- **SVTM extant** rainforest / wet sclerophyll PCTs — current mapped remnants (regional scale).
- **SVTM pre-clearing (1750)** rainforest PCTs — **modelled** pre-clearing extent for landscape context.
- Literature / NPWS narrative (~2,450–2,500 ha former Yarrawa Brush) remains **text context only**.

## Why
No official open polygon named “Yarrawa Brush” was identified for defensive mapping.
Fabricating a historic boundary from tourism maps or rough area figures would overstate certainty.

## Interpretation language for the dashboard
- “Modelled pre-clearing rainforest PCT extent (SVTM)”
- “Extant rainforest remnants (SVTM)”
- Not: “Historic Yarrawa Brush boundary”
""",
        encoding="utf-8",
    )

    out_gpkg = paths["interim_dir"] / str(
        settings.get("outputs", {}).get("phase2_interim_gpkg", "phase2_remnant.gpkg")
    )
    if out_gpkg.is_file():
        out_gpkg.unlink()

    layers = {
        "study_area": study_area.to_crs(crs),
        "robertson_nature_reserve": reserve.to_crs(crs),
        "native_vegetation": native_vegetation,
        "rainforest_extant": rainforest_extant,
        "wet_sclerophyll_extant": wet_sclerophyll_extant,
        "rainforest_preclear_modelled": preclear_rainforest_context,
        "cleared_or_non_native": cleared,
    }
    if not tec.empty:
        layers["tec_ceec_indicative"] = tec

    for name, gdf in layers.items():
        write_gdf(gdf, out_gpkg, layer=name)
        logger.info("Wrote %-32s %6s features", name, len(gdf))

    # QA
    qa_path = paths["reports_dir"] / "data_quality_report.csv"
    qa_rows = []
    for name, gdf in layers.items():
        qa_rows.extend(basic_vector_qa(gdf, f"phase2::{name}"))
    append_qa_rows(qa_rows, qa_path)

    summary = pd.DataFrame(
        [
            {
                "layer": k,
                "features": len(v),
                "area_ha": round(float(v.geometry.area.sum() / 10000.0), 2) if not v.empty else 0.0,
                "crs": str(v.crs),
            }
            for k, v in layers.items()
        ]
    )
    summary.to_csv(paths["reports_dir"] / "phase2_layer_summary.csv", index=False)

    _update_sources(paths["data_sources_csv"], ["svtm_extant", "svtm_preclear", "tec_nsw"])

    logger.info("Phase 2 complete.")
    logger.info("Interim GPKG: %s", out_gpkg)
    logger.info("Summary:\n%s", summary.to_string(index=False))


if __name__ == "__main__":
    main()
