"""
PYTHON DATA PREP — assemble robertson_conservation.gpkg + selected GeoJSON/CSV.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd

from utils import ensure_dirs, write_gdf


def compile_master_grid(
    *,
    biodiversity_grid: gpd.GeoDataFrame,
    threatened_grid: gpd.GeoDataFrame,
    opportunity_grid: gpd.GeoDataFrame,
    crs_analysis: str,
) -> gpd.GeoDataFrame:
    """
    Join Phase 3 biodiversity / threatened metrics onto the Phase 6 opportunity grid.

    Opportunity grid already carries landscape (Phase 5) + opportunity (Phase 6) fields.
    """
    base = opportunity_grid.to_crs(crs_analysis).copy()
    if "cell_id" not in base.columns:
        raise ValueError("opportunity_grid missing cell_id")

    bio_cols = [
        c
        for c in biodiversity_grid.columns
        if c not in ("geometry", "cell_area_ha", "interpretation")
    ]
    bio = biodiversity_grid[bio_cols].copy()
    # Avoid clashing interpretation columns
    if "interpretation" in bio.columns:
        bio = bio.rename(columns={"interpretation": "interpretation_biodiv"})

    thr_cols = [
        c
        for c in threatened_grid.columns
        if c not in ("geometry", "cell_area_ha", "interpretation")
    ]
    thr = threatened_grid[thr_cols].copy()
    if "interpretation" in thr.columns:
        thr = thr.rename(columns={"interpretation": "interpretation_threat"})

    out = base.merge(bio, on="cell_id", how="left")
    out = out.merge(thr, on="cell_id", how="left")

    # Fill count metrics with 0 where no observations
    for col in out.columns:
        if col.startswith(("n_", "animal_", "plant_", "threat_")) and col.endswith(
            ("_records", "_species")
        ):
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).astype(int)

    out["interpretation"] = (
        "Compiled 250 m analysis grid: biodiversity + landscape + unweighted "
        "opportunity components. Not a weighted opportunity index."
    )
    return out


def copy_layer(
    src_gpkg: Path,
    layer: str,
    *,
    crs_analysis: str,
) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(src_gpkg, layer=layer)
    if gdf.crs is None:
        return gdf
    return gdf.to_crs(crs_analysis)


def write_master_gpkg(
    layers: dict[str, gpd.GeoDataFrame],
    out_path: Path,
    *,
    logger: Any | None = None,
) -> Path:
    """Write/replace master GeoPackage with named layers."""
    ensure_dirs(out_path.parent)
    if out_path.is_file():
        out_path.unlink()
    for name, gdf in layers.items():
        if gdf is None:
            continue
        write_gdf(gdf, out_path, layer=name)
        if logger:
            logger.info("Master %-32s %6s features", name, len(gdf))
    return out_path


def export_geojson_subset(
    layers: dict[str, gpd.GeoDataFrame],
    out_dir: Path,
    *,
    logger: Any | None = None,
) -> list[Path]:
    """Export selected layers to GeoJSON (WGS84) for web/dashboard use."""
    ensure_dirs(out_dir)
    written: list[Path] = []
    for name, gdf in layers.items():
        if gdf is None or gdf.empty:
            continue
        path = out_dir / f"{name}.geojson"
        out = gdf.to_crs("EPSG:4326")
        # Drop long text fields that bloat web GeoJSON
        if "Description" in out.columns and len(out) > 50:
            out = out.drop(columns=["Description"])
        out.to_file(path, driver="GeoJSON")
        written.append(path)
        if logger:
            logger.info("GeoJSON %s (%s features)", path.name, len(out))
    return written


def export_grid_csv(master_grid: gpd.GeoDataFrame, out_path: Path) -> Path:
    ensure_dirs(out_path.parent)
    df = master_grid.drop(columns="geometry", errors="ignore")
    df.to_csv(out_path, index=False)
    return out_path


def layer_inventory(layers: dict[str, gpd.GeoDataFrame]) -> pd.DataFrame:
    rows = []
    for name, gdf in layers.items():
        rows.append(
            {
                "layer": name,
                "features": 0 if gdf is None else len(gdf),
                "crs": None if gdf is None or gdf.empty else str(gdf.crs),
                "geometry_types": None
                if gdf is None or gdf.empty
                else ",".join(sorted(gdf.geom_type.unique())),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    raise SystemExit("Run src/07_export_master.py for Phase 7.")


if __name__ == "__main__":
    main()
