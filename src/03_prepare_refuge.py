"""
Phase 3 — The Refuge (biodiversity).

Download BioNet public sightings (+ optional ALA), clean/dedupe, build 250 m
analysis grid, aggregate threatened/sensitive metrics, export phase3_refuge.gpkg.
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

from clean_species_data import (  # noqa: E402
    aggregate_to_grid,
    ala_records_to_gdf,
    bionet_records_to_gdf,
    build_analysis_grid,
    clean_species_observations,
    dedupe_observations,
    public_point_layer,
    richness_by_group_year,
    threatened_species_summary,
)
from config import load_settings  # noqa: E402
from download_data import download_ala_occurrences, download_bionet_sightings  # noqa: E402
from utils import (  # noqa: E402
    append_qa_rows,
    basic_vector_qa,
    ensure_dirs,
    setup_logging,
    write_gdf,
)


KEEP_POINT_COLS = [
    "source",
    "source_record_id",
    "scientificName",
    "vernacularName",
    "eventDate",
    "year",
    "kingdom",
    "taxon_group",
    "family",
    "stateConservation",
    "countryConservation",
    "sensitivityClass",
    "is_threatened",
    "is_sensitive",
    "coordinateUncertaintyInMeters",
    "coord_flag",
    "date_flag",
    "basisOfRecord",
    "interpretation",
    "geometry",
]


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
    sp = settings.get("species", {})
    grid_cfg = settings.get("grid", {})
    crs = str(study_cfg["crs_analysis"])

    logger = setup_logging(
        paths["logs_dir"],
        name="phase3_refuge",
        level=str(settings.get("logging", {}).get("level", "INFO")),
    )
    ensure_dirs(
        paths["raw_dir"],
        paths["interim_dir"],
        paths["reports_dir"],
        paths["reference_dir"],
        paths["csv_dir"],
    )

    phase1 = paths["interim_dir"] / str(
        settings.get("outputs", {}).get("phase1_interim_gpkg", "phase1_foundation.gpkg")
    )
    if not phase1.is_file():
        raise FileNotFoundError(f"Phase 1 GPKG missing. Run 01_build_foundation.py first: {phase1}")

    logger.info("=== Phase 3: The Refuge (BioNet / ALA) ===")
    study_area = gpd.read_file(phase1, layer="study_area")
    reserve = gpd.read_file(phase1, layer="robertson_nature_reserve")
    aoi_wgs = study_area.to_crs("EPSG:4326")

    bionet_path = download_bionet_sightings(settings, aoi_wgs, logger)
    ala_path = download_ala_occurrences(settings, aoi_wgs, logger)

    bionet_df = pd.read_parquet(bionet_path)
    bionet_gdf = bionet_records_to_gdf(bionet_df)
    logger.info("BioNet points loaded: %s", len(bionet_gdf))

    frames = [bionet_gdf]
    downloaded_ids = ["bionet_sightings"]
    if ala_path is not None:
        ala_df = pd.read_parquet(ala_path)
        ala_gdf = ala_records_to_gdf(ala_df)
        logger.info("ALA points loaded: %s", len(ala_gdf))
        frames.append(ala_gdf)
        downloaded_ids.append("ala_occurrences")

    combined = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")
    cleaned = clean_species_observations(
        combined,
        study_area=study_area,
        crs_analysis=crs,
        max_coordinate_uncertainty_m=float(sp.get("max_coordinate_uncertainty_m", 25000)),
        min_year_keep=int(sp.get("min_year_keep", 1950)),
        threatened_statuses=list(sp.get("threatened_state_statuses") or []),
    )
    logger.info("After clip/clean: %s", len(cleaned))
    cleaned = dedupe_observations(cleaned)
    logger.info("After dedupe: %s", len(cleaned))

    # Analysis grid
    cell = float(grid_cfg.get("cell_size_m", 250))
    grid = build_analysis_grid(study_area, cell_size_m=cell, crs_analysis=crs)
    logger.info("Analysis grid cells: %s (%.0f m)", len(grid), cell)

    # Biodiversity grid (all cleaned public records)
    biodiv = aggregate_to_grid(cleaned, grid, prefix="")
    # Group counts on grid (animals / plants)
    animals = cleaned["kingdom"].fillna("").astype(str).str.contains("Animalia", case=False, na=False)
    plants = cleaned["kingdom"].fillna("").astype(str).str.contains("Plantae", case=False, na=False)
    animal_grid = aggregate_to_grid(cleaned, grid, subset_mask=animals, prefix="animal_")
    plant_grid = aggregate_to_grid(cleaned, grid, subset_mask=plants, prefix="plant_")
    biodiv = biodiv.merge(
        animal_grid.drop(columns=["geometry", "cell_area_ha"], errors="ignore"),
        on="cell_id",
        how="left",
    )
    biodiv = biodiv.merge(
        plant_grid.drop(columns=["geometry", "cell_area_ha"], errors="ignore"),
        on="cell_id",
        how="left",
    )
    for col in ("animal_n_records", "animal_n_species", "plant_n_records", "plant_n_species"):
        if col in biodiv.columns:
            biodiv[col] = biodiv[col].fillna(0).astype(int)
    biodiv["interpretation"] = (
        f"Observation effort-biased richness on {int(cell)} m grid. "
        "Not abundance. Sensitive taxa denatured at source."
    )

    # Threatened / sensitive → grid only (no precise public sensitive points layer)
    thr_or_sens = cleaned["is_threatened"] | cleaned["is_sensitive"]
    threatened_agg = aggregate_to_grid(cleaned, grid, subset_mask=thr_or_sens, prefix="threat_")
    threatened_agg["interpretation"] = (
        "Grid-aggregated threatened and/or sensitive public records. "
        "Do not reverse-engineer precise locations from this layer."
    )
    # Keep only cells with at least one threatened/sensitive record for a compact layer
    threatened_cells = threatened_agg.loc[threatened_agg["threat_n_records"] > 0].copy()

    points_public = public_point_layer(
        cleaned,
        sensitive_exclude=list(sp.get("sensitive_classes_point_exclude") or []),
    )
    # Slim columns for GPKG
    point_cols = [c for c in KEEP_POINT_COLS if c in points_public.columns]
    points_public = points_public[point_cols].copy()

    # Reports
    group_year = richness_by_group_year(cleaned)
    group_year.to_csv(paths["reports_dir"] / "phase3_richness_by_group_year.csv", index=False)
    thr_summary = threatened_species_summary(cleaned)
    thr_summary.to_csv(paths["reports_dir"] / "phase3_threatened_species_summary.csv", index=False)
    thr_summary.to_csv(paths["reference_dir"] / "threatened_species_list.csv", index=False)

    summary = pd.DataFrame(
        [
            {
                "metric": "observations_clean_total",
                "value": len(cleaned),
            },
            {
                "metric": "observations_public_points",
                "value": len(points_public),
            },
            {
                "metric": "observations_threatened",
                "value": int(cleaned["is_threatened"].sum()),
            },
            {
                "metric": "observations_sensitive",
                "value": int(cleaned["is_sensitive"].sum()),
            },
            {
                "metric": "species_total",
                "value": int(cleaned["scientificName"].nunique()),
            },
            {
                "metric": "species_threatened",
                "value": int(cleaned.loc[cleaned["is_threatened"], "scientificName"].nunique()),
            },
            {
                "metric": "grid_cells",
                "value": len(grid),
            },
            {
                "metric": "grid_cells_with_threat_sens",
                "value": len(threatened_cells),
            },
            {
                "metric": "sources",
                "value": ",".join(sorted(cleaned["source"].dropna().unique())),
            },
        ]
    )
    summary.to_csv(paths["reports_dir"] / "phase3_summary.csv", index=False)

    note_path = paths["reports_dir"] / "phase3_sensitivity_note.md"
    note_path.write_text(
        """# Species sensitivity & effort (Phase 3)

## Public points
- `species_observations_clean` excludes BioNet sensitivity **Category 1–3**.
- Remaining coordinates are public; sensitive taxa released by BioNet are already **denatured**.

## Threatened / sensitive mapping
- Use `threatened_species_aggregated` (250 m grid counts / richness).
- Do **not** publish or attempt to recover precise locations for sensitive taxa.

## Effort bias
- Record density reflects survey effort, not abundance.
- Compare richness between cells cautiously; empty cells ≠ absence of species.
""",
        encoding="utf-8",
    )

    out_gpkg = paths["interim_dir"] / str(
        settings.get("outputs", {}).get("phase3_interim_gpkg", "phase3_refuge.gpkg")
    )
    if out_gpkg.is_file():
        out_gpkg.unlink()

    layers = {
        "study_area": study_area.to_crs(crs),
        "robertson_nature_reserve": reserve.to_crs(crs),
        "analysis_grid": grid,
        "species_observations_clean": points_public,
        "threatened_species_aggregated": threatened_cells,
        "biodiversity_grid": biodiv,
    }
    for name, gdf in layers.items():
        write_gdf(gdf, out_gpkg, layer=name)
        logger.info("Wrote %-32s %6s features", name, len(gdf))

    qa_path = paths["reports_dir"] / "data_quality_report.csv"
    qa_rows = []
    for name, gdf in layers.items():
        qa_rows.extend(basic_vector_qa(gdf, f"phase3::{name}"))
    append_qa_rows(qa_rows, qa_path)

    layer_summary = pd.DataFrame(
        [
            {
                "layer": k,
                "features": len(v),
                "crs": str(v.crs),
            }
            for k, v in layers.items()
        ]
    )
    layer_summary.to_csv(paths["reports_dir"] / "phase3_layer_summary.csv", index=False)

    _update_sources(paths["data_sources_csv"], downloaded_ids)

    logger.info("Phase 3 complete.")
    logger.info("Interim GPKG: %s", out_gpkg)
    logger.info("Summary:\n%s", summary.to_string(index=False))


if __name__ == "__main__":
    main()
