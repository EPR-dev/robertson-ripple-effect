"""
PYTHON DATA PREP — build study AOI and clean foundation vector layers.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely.ops import unary_union


def extract_reserve(estate: gpd.GeoDataFrame, reserve_name: str) -> gpd.GeoDataFrame:
    """Exact name match on NPWS Estate NAME field."""
    if "NAME" not in estate.columns:
        raise KeyError("NPWS Estate missing NAME column")
    hit = estate[estate["NAME"].astype(str).str.strip() == reserve_name].copy()
    if hit.empty:
        # fallback contains match
        hit = estate[estate["NAME"].astype(str).str.contains(reserve_name, case=False, na=False)].copy()
    if hit.empty:
        raise ValueError(f"Reserve not found in estate: {reserve_name}")
    return hit


def build_study_area(reserve: gpd.GeoDataFrame, buffer_km: float, crs_analysis: str) -> gpd.GeoDataFrame:
    """Buffer reserve boundary by buffer_km and dissolve."""
    r = reserve.to_crs(crs_analysis)
    buffered = r.buffer(float(buffer_km) * 1000.0)
    geom = unary_union(list(buffered))
    return gpd.GeoDataFrame(
        {
            "name": ["study_area"],
            "method": [f"reserve_buffer_{buffer_km}_km"],
            "buffer_km": [float(buffer_km)],
            "source_reserve": [str(reserve.iloc[0].get("NAME", ""))],
        },
        geometry=[geom],
        crs=crs_analysis,
    )


def select_context_reserves(
    estate: gpd.GeoDataFrame,
    patterns: list[str],
    logger: logging.Logger | None = None,
) -> gpd.GeoDataFrame:
    """Select estate features whose NAME matches any substring pattern."""
    names = estate["NAME"].astype(str)
    mask = pd.Series(False, index=estate.index)
    for pattern in patterns:
        mask |= names.str.contains(re.escape(pattern), case=False, na=False)
    out = estate.loc[mask].copy()
    if logger:
        logger.info("Context reserve pattern matches: %s", len(out))
    return out


def build_context_aoi(
    study_area: gpd.GeoDataFrame,
    context_reserves: gpd.GeoDataFrame,
    halo_km: float,
    crs_analysis: str,
) -> gpd.GeoDataFrame:
    """Union study_area with context reserves (+ halo)."""
    parts = [study_area.to_crs(crs_analysis).geometry.iloc[0]]
    if not context_reserves.empty:
        cr = context_reserves.to_crs(crs_analysis)
        parts.append(unary_union(list(cr.buffer(float(halo_km) * 1000.0))))
    geom = unary_union(parts)
    return gpd.GeoDataFrame(
        {
            "name": ["context_aoi"],
            "method": ["study_area_union_context_reserves"],
            "halo_km": [float(halo_km)],
        },
        geometry=[geom],
        crs=crs_analysis,
    )


def clip_to_aoi(gdf: gpd.GeoDataFrame, aoi: gpd.GeoDataFrame, crs_analysis: str) -> gpd.GeoDataFrame:
    if gdf.empty:
        return gdf.to_crs(crs_analysis) if gdf.crs else gdf
    left = gdf.to_crs(crs_analysis)
    poly = unary_union(list(aoi.to_crs(crs_analysis).geometry))
    return left[left.intersects(poly)].copy()


def repair_geometries(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Fix invalid geometries where possible (buffer(0) / make_valid)."""
    if gdf.empty:
        return gdf
    out = gdf.copy()
    try:
        from shapely import make_valid

        out["geometry"] = out.geometry.map(
            lambda g: make_valid(g) if g is not None and not g.is_valid else g
        )
    except Exception:
        out["geometry"] = out.geometry.buffer(0)
    return out


def standardise_reserve_columns(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    out = repair_geometries(gdf.copy())
    rename = {
        "NAME": "reserve_name",
        "TYPE": "reserve_type",
        "RES_NO": "reserve_no",
        "GAZ_AREA": "gaz_area_ha",
        "GIS_AREA": "gis_area_ha",
        "IUCN": "iucn",
    }
    out = out.rename(columns={k: v for k, v in rename.items() if k in out.columns})
    keep = [c for c in ["reserve_name", "reserve_type", "reserve_no", "gaz_area_ha", "gis_area_ha", "iucn", "geometry"] if c in out.columns]
    return out[keep]
