"""
Phase 3 — Enrich rainforest remnants + habitat network attributes.

Adds transparent patch attributes for StoryMap pop-ups and ArcGIS handoff.
Does not invent connectivity scores or animal movement corridors.
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
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(__file__).resolve().parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from config import load_settings  # noqa: E402
from utils import ensure_dirs, setup_logging, to_analysis_crs, write_gdf  # noqa: E402


def _majority_from_overlay(
    patches: gpd.GeoDataFrame,
    veg: gpd.GeoDataFrame,
    field: str,
    crs: str,
) -> pd.Series:
    """Majority attribute by intersecting area (approx via overlay)."""
    if patches.empty or veg.empty or field not in veg.columns:
        return pd.Series(["unknown"] * len(patches), index=patches.index)

    left = to_analysis_crs(patches, crs)[["patch_id", "geometry"]].copy()
    right = to_analysis_crs(veg, crs)[[field, "geometry"]].copy()
    right = right[right[field].notna()].copy()
    if right.empty:
        return pd.Series(["unknown"] * len(patches), index=patches.index)

    try:
        ov = gpd.overlay(left, right, how="intersection", keep_geom_type=False)
    except Exception:
        return pd.Series(["unknown"] * len(patches), index=patches.index)
    if ov.empty:
        return pd.Series(["unknown"] * len(patches), index=patches.index)

    ov["_a"] = ov.geometry.area
    top = (
        ov.groupby(["patch_id", field], dropna=False)["_a"]
        .sum()
        .reset_index()
        .sort_values(["patch_id", "_a"], ascending=[True, False])
        .drop_duplicates("patch_id")
    )
    mapping = dict(zip(top["patch_id"], top[field].astype(str)))
    return patches["patch_id"].map(mapping).fillna("unknown")


def _protection_status(
    patches: gpd.GeoDataFrame,
    protected: gpd.GeoDataFrame,
    crown: gpd.GeoDataFrame,
    crs: str,
) -> pd.Series:
    p = to_analysis_crs(patches, crs)
    status = pd.Series(["none"] * len(p), index=p.index)
    if protected is not None and not protected.empty:
        prot = to_analysis_crs(protected, crs)
        union = unary_union(list(prot.geometry))
        status = status.mask(p.intersects(union), "protected_npws")
    if crown is not None and not crown.empty:
        cr = to_analysis_crs(crown, crs)
        union_c = unary_union(list(cr.geometry))
        # only upgrade none → crown; keep protected
        status = status.mask((status == "none") & p.intersects(union_c), "crown_or_public")
    return status


def _dist_to_lines(patches: gpd.GeoDataFrame, lines: gpd.GeoDataFrame, crs: str) -> pd.Series:
    if patches.empty:
        return pd.Series(dtype=float)
    p = to_analysis_crs(patches, crs)
    if lines is None or lines.empty:
        return pd.Series([None] * len(p), index=p.index)
    ln = to_analysis_crs(lines, crs)
    union = unary_union(list(ln.geometry))
    return p.geometry.distance(union)


def _richness_join(
    patches: gpd.GeoDataFrame,
    grid: gpd.GeoDataFrame,
    crs: str,
) -> tuple[pd.Series, pd.Series]:
    """Join mean n_species and max threatened flag from intersecting grid cells."""
    if patches.empty or grid is None or grid.empty:
        return (
            pd.Series([0] * len(patches), index=patches.index),
            pd.Series([False] * len(patches), index=patches.index),
        )
    p = to_analysis_crs(patches, crs)[["patch_id", "geometry"]]
    g = to_analysis_crs(grid, crs)
    spp_col = "n_species" if "n_species" in g.columns else None
    thr_col = None
    for c in ("n_threatened_species", "n_threat_species", "threatened_n_species"):
        if c in g.columns:
            thr_col = c
            break
    cols = ["geometry"]
    if spp_col:
        cols.append(spp_col)
    if thr_col:
        cols.append(thr_col)
    g = g[cols].copy()
    try:
        ov = gpd.overlay(p, g, how="intersection", keep_geom_type=False)
    except Exception:
        return (
            pd.Series([0] * len(patches), index=patches.index),
            pd.Series([False] * len(patches), index=patches.index),
        )
    if ov.empty:
        return (
            pd.Series([0] * len(patches), index=patches.index),
            pd.Series([False] * len(patches), index=patches.index),
        )
    if spp_col:
        rich = ov.groupby("patch_id")[spp_col].mean()
    else:
        rich = pd.Series(dtype=float)
    if thr_col:
        thr = ov.groupby("patch_id")[thr_col].max() > 0
    else:
        thr = pd.Series(dtype=bool)
    return (
        patches["patch_id"].map(rich).fillna(0).round(2),
        patches["patch_id"].map(thr).fillna(False),
    )


def _size_class(area_ha: pd.Series) -> pd.Series:
    return pd.cut(
        area_ha,
        bins=[-0.1, 2, 5, 20, 100, np.inf],
        labels=["micro_<2ha", "small_2_5ha", "medium_5_20ha", "large_20_100ha", "very_large_>100ha"],
    ).astype(str)


def enrich_patches(
    patches: gpd.GeoDataFrame,
    *,
    veg: gpd.GeoDataFrame,
    protected: gpd.GeoDataFrame,
    crown: gpd.GeoDataFrame,
    hydro: gpd.GeoDataFrame,
    grid: gpd.GeoDataFrame,
    crs: str,
    layer_label: str,
) -> gpd.GeoDataFrame:
    out = to_analysis_crs(patches, crs).copy()
    if "patch_id" not in out.columns:
        out["patch_id"] = [f"{layer_label}_{i:04d}" for i in range(len(out))]
    if "area_ha" not in out.columns:
        out["area_ha"] = out.geometry.area / 10000.0
    if "perimeter_m" not in out.columns:
        out["perimeter_m"] = out.geometry.length

    out["edge_area_ratio"] = (out["perimeter_m"] / out.geometry.area.replace(0, np.nan)).fillna(0)
    out["size_class"] = _size_class(out["area_ha"])
    out["majority_pct_name"] = _majority_from_overlay(out, veg, "pct_name", crs)
    out["majority_veg_class"] = _majority_from_overlay(out, veg, "veg_class", crs)
    out["protection_status"] = _protection_status(out, protected, crown, crs)
    out["dist_to_waterway_m"] = _dist_to_lines(out, hydro, crs).round(1)
    rich, thr = _richness_join(out, grid, crs)
    out["nearby_species_richness_mean"] = rich
    out["threatened_species_context"] = thr
    out["interpretation"] = (
        "Patch metrics are geometric / landscape context — not animal movement proof."
    )
    out["evidence_tag"] = "CALCULATED"
    out["enriched_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return out


def main() -> None:
    settings = load_settings()
    paths = settings["resolved_paths"]
    crs = str(settings["study_area"]["crs_analysis"])
    logger = setup_logging(paths["logs_dir"], name="phase3_habitat_enrich", level="INFO")
    ensure_dirs(paths["interim_dir"], paths["reports_dir"], paths["csv_dir"], paths["geojson_dir"])

    master = paths["gpkg_dir"] / str(settings.get("outputs", {}).get("master_gpkg", "robertson_conservation.gpkg"))
    logger.info("=== Phase 3: Enrich habitat network ===")

    rainforest_patches = gpd.read_file(master, layer="rainforest_patches")
    core_patches = gpd.read_file(master, layer="core_habitat_patches")
    habitat_patches = gpd.read_file(master, layer="habitat_patches")
    veg = gpd.read_file(master, layer="rainforest_extant")
    native = gpd.read_file(master, layer="native_vegetation")
    protected = gpd.read_file(master, layer="protected_areas")
    crown = gpd.read_file(master, layer="crown_land")
    hydro = gpd.read_file(master, layer="hydro_lines")
    grid = gpd.read_file(master, layer="analysis_grid_metrics")

    rf_enriched = enrich_patches(
        rainforest_patches,
        veg=veg,
        protected=protected,
        crown=crown,
        hydro=hydro,
        grid=grid,
        crs=crs,
        layer_label="rf",
    )
    core_enriched = enrich_patches(
        core_patches,
        veg=pd.concat([veg, native], ignore_index=True) if not native.empty else veg,
        protected=protected,
        crown=crown,
        hydro=hydro,
        grid=grid,
        crs=crs,
        layer_label="core",
    )
    # Small pieces story layer: rainforest + core patches under 5 ha
    small = pd.concat(
        [
            rf_enriched.assign(source_layer="rainforest_patches"),
            core_enriched.assign(source_layer="core_habitat_patches"),
        ],
        ignore_index=True,
    )
    small = gpd.GeoDataFrame(small, geometry="geometry", crs=crs)
    small = small[small["area_ha"] < 5].copy()
    small = small.drop_duplicates(subset=["geometry"], keep="first")
    small["story_role"] = "other_little_piece"
    small["why_location_may_matter"] = (
        "Small patches can still matter when they sit near larger habitat, streams, or gaps."
    )

    # Counts within distance bands among rainforest patches
    rf = rf_enriched.copy()
    if not rf.empty:
        centroids = rf.geometry.centroid
        tree_idx = rf.sindex
        counts_500 = []
        counts_1000 = []
        for i, geom in enumerate(rf.geometry):
            # use centroid buffer query then refine edge distance
            c = centroids.iloc[i]
            cand = list(tree_idx.intersection(c.buffer(1100).bounds))
            d500 = d1000 = 0
            for j in cand:
                if i == j:
                    continue
                d = geom.distance(rf.geometry.iloc[j])
                if d <= 500:
                    d500 += 1
                if d <= 1000:
                    d1000 += 1
            counts_500.append(d500)
            counts_1000.append(d1000)
        rf["n_rf_patches_within_500m"] = counts_500
        rf["n_rf_patches_within_1km"] = counts_1000
        rf_enriched = rf

    gpkg = paths["interim_dir"] / "phase3_habitat_enriched.gpkg"
    write_gdf(rf_enriched, gpkg, layer="rainforest_patches_enriched")
    write_gdf(core_enriched, gpkg, layer="core_habitat_patches_enriched")
    write_gdf(small, gpkg, layer="small_habitat_pieces")

    # Update master
    write_gdf(rf_enriched, master, layer="rainforest_patches")
    write_gdf(core_enriched, master, layer="core_habitat_patches")
    write_gdf(small, master, layer="small_habitat_pieces")
    processed = paths["processed_dir"] / master.name
    if processed.is_file():
        write_gdf(rf_enriched, processed, layer="rainforest_patches")
        write_gdf(core_enriched, processed, layer="core_habitat_patches")
        write_gdf(small, processed, layer="small_habitat_pieces")

    rf_enriched.drop(columns="geometry").to_csv(
        paths["csv_dir"] / "rainforest_patches_enriched.csv", index=False
    )
    small.drop(columns="geometry").to_csv(paths["csv_dir"] / "small_habitat_pieces.csv", index=False)

    # Lightweight geojson for StoryMap art (simplify)
    try:
        art = rf_enriched.copy()
        art["geometry"] = art.geometry.simplify(10)
        art.to_crs("EPSG:4326").to_file(
            paths["geojson_dir"] / "rainforest_patches_enriched.geojson", driver="GeoJSON"
        )
        sart = small.copy()
        sart["geometry"] = sart.geometry.simplify(5)
        sart.to_crs("EPSG:4326").to_file(
            paths["geojson_dir"] / "small_habitat_pieces.geojson", driver="GeoJSON"
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("GeoJSON export issue: %s", exc)

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rainforest_patches_n": int(len(rf_enriched)),
        "rainforest_total_ha": round(float(rf_enriched["area_ha"].sum()), 2) if len(rf_enriched) else 0,
        "core_patches_n": int(len(core_enriched)),
        "small_pieces_n": int(len(small)),
        "small_pieces_ha": round(float(small["area_ha"].sum()), 2) if len(small) else 0,
        "size_class_rainforest": rf_enriched["size_class"].value_counts().to_dict() if len(rf_enriched) else {},
        "protection_rainforest": rf_enriched["protection_status"].value_counts().to_dict()
        if len(rf_enriched)
        else {},
        "cartographic_art": (
            "Paint remnants as soft moss islands; emphasise micro/small size classes in "
            "'Other Little Pieces' with dawn-gold outlines — never accusatory fills."
        ),
    }
    (paths["csv_dir"] / "habitat_network_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    md = f"""# Phase 3 complete — Habitat network enrichment

**Date:** {summary['generated_at_utc'][:10]}  
**Status:** Complete for review

## GIS concept

**Habitat patches** are dissolved native-vegetation polygons used as nodes in a landscape network.
Attributes here describe patch size, neighbours, protection, water proximity and biodiversity context.
They are **not** proof of wildlife movement.

## Deliverables

- Enriched `rainforest_patches` / `core_habitat_patches` in master GPKG
- `small_habitat_pieces` (< 5 ha) for “Other Little Pieces”
- `outputs/csv/rainforest_patches_enriched.csv`
- `outputs/csv/small_habitat_pieces.csv`
- `outputs/csv/habitat_network_summary.json`
- `src/12_enrich_habitat_network.py`

## Summary

| Layer | Count | Notes |
|-------|------:|-------|
| Rainforest patches | {summary['rainforest_patches_n']} | {summary['rainforest_total_ha']} ha total |
| Core habitat patches | {summary['core_patches_n']} | rainforest + wet sclerophyll |
| Small pieces (<5 ha) | {summary['small_pieces_n']} | {summary['small_pieces_ha']} ha |

## Validation

1. Spot-check 5 rainforest patches: area_ha ≈ geometry area/10000 in EPSG:7856.
2. Confirm protection_status = protected_npws where patch intersects NPWS estate.
3. Confirm small_habitat_pieces all have area_ha < 5.

## Next

Phase 4 — Connectivity prep + typed habitat connection opportunities (gaps).
"""
    (paths["reports_dir"] / "PHASE3_COMPLETE.md").write_text(md, encoding="utf-8")
    logger.info(
        "Phase 3 complete: rf=%s small=%s",
        summary["rainforest_patches_n"],
        summary["small_pieces_n"],
    )


if __name__ == "__main__":
    main()
