"""
PYTHON DATA PREP — SVTM remnant / habitat classification helpers.

Labels modelled pre-clearing clearly. Does not fabricate Yarrawa Brush boundaries.
"""

from __future__ import annotations

import re
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely.ops import unary_union


def standardise_svtm_columns(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Normalise SVTM Quickview attribute names."""
    if gdf.empty:
        return gdf
    out = gdf.copy()
    rename = {
        "PCTID": "pct_id",
        "PCTName": "pct_name",
        "vegClass": "veg_class",
        "vegForm": "veg_form",
    }
    out = out.rename(columns={k: v for k, v in rename.items() if k in out.columns})
    keep = [c for c in ["pct_id", "pct_name", "veg_class", "veg_form", "geometry"] if c in out.columns]
    return out[keep]


def _contains_any(series: pd.Series, needles: list[str]) -> pd.Series:
    text = series.fillna("").astype(str)
    mask = pd.Series(False, index=series.index)
    for needle in needles:
        mask |= text.str.contains(re.escape(needle), case=False, na=False)
    return mask


def filter_classified_native(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Extant SVTM polygons with a classified native PCT.

    Excludes PCT 0 / 'Not classified' (cleared, non-native, or unmapped mask
    that tiles the full landscape in Quickview).
    """
    if gdf.empty:
        return gdf.copy()
    out = gdf.copy()
    unclassified = pd.Series(False, index=out.index)
    if "pct_id" in out.columns:
        unclassified |= pd.to_numeric(out["pct_id"], errors="coerce").fillna(-1).eq(0)
    if "veg_form" in out.columns:
        unclassified |= out["veg_form"].fillna("").astype(str).str.contains(
            "Not classified", case=False, na=False
        )
    if "pct_name" in out.columns:
        unclassified |= out["pct_name"].fillna("").astype(str).str.fullmatch(
            r"Not classified", case=False, na=False
        )
    return out.loc[~unclassified].copy()


def _form_or_class_mask(
    gdf: gpd.GeoDataFrame,
    *,
    veg_forms: list[str],
    veg_class_contains: list[str],
) -> pd.Series:
    form_ok = (
        _contains_any(gdf["veg_form"], veg_forms) if "veg_form" in gdf.columns else False
    )
    class_ok = (
        _contains_any(gdf["veg_class"], veg_class_contains)
        if "veg_class" in gdf.columns
        else False
    )
    return form_ok | class_ok


def filter_rainforest(
    gdf: gpd.GeoDataFrame,
    *,
    veg_forms: list[str],
    veg_class_contains: list[str],
) -> gpd.GeoDataFrame:
    if gdf.empty:
        return gdf.copy()
    return gdf.loc[_form_or_class_mask(gdf, veg_forms=veg_forms, veg_class_contains=veg_class_contains)].copy()


def filter_wet_sclerophyll(
    gdf: gpd.GeoDataFrame,
    *,
    veg_forms: list[str],
    veg_class_contains: list[str],
) -> gpd.GeoDataFrame:
    if gdf.empty:
        return gdf.copy()
    return gdf.loc[_form_or_class_mask(gdf, veg_forms=veg_forms, veg_class_contains=veg_class_contains)].copy()


def build_cleared_landscape(
    study_area: gpd.GeoDataFrame,
    native_veg: gpd.GeoDataFrame,
    crs_analysis: str,
) -> gpd.GeoDataFrame:
    """
    Approximate cleared / non-native map area = study_area minus extant native PCT union.

    This is a landscape contrast layer, not a cadastral land-use product.
    """
    sa = study_area.to_crs(crs_analysis)
    if native_veg.empty:
        out = sa.copy()
        out["name"] = "cleared_or_non_native_extent"
        out["method"] = "study_area_minus_empty_native"
        out["interpretation"] = "contrast_only_not_cadastral_landuse"
        return out[["name", "method", "interpretation", "geometry"]]

    native = native_veg.to_crs(crs_analysis)
    native_union = unary_union(list(native.geometry))
    cleared = sa.geometry.iloc[0].difference(native_union)
    return gpd.GeoDataFrame(
        [
            {
                "name": "cleared_or_non_native_extent",
                "method": "study_area_difference_extant_svtm_pct",
                "interpretation": (
                    "Approximate cleared/non-native contrast from SVTM extant mask. "
                    "Not NSW Landuse cadastral classes. Association only."
                ),
            }
        ],
        geometry=[cleared],
        crs=crs_analysis,
    )


def pct_summary_table(gdf: gpd.GeoDataFrame, *, layer_label: str) -> pd.DataFrame:
    """Summarise PCT area (ha) for documentation."""
    if gdf.empty:
        return pd.DataFrame(
            columns=["layer", "pct_id", "pct_name", "veg_class", "veg_form", "area_ha", "polygon_count"]
        )
    tmp = gdf.copy()
    tmp["area_ha"] = tmp.geometry.area / 10000.0
    grouped = (
        tmp.groupby(["pct_id", "pct_name", "veg_class", "veg_form"], dropna=False, as_index=False)
        .agg(area_ha=("area_ha", "sum"), polygon_count=("geometry", "count"))
        .sort_values("area_ha", ascending=False)
    )
    grouped.insert(0, "layer", layer_label)
    return grouped


def tag_modelled_preclearing(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    out = gdf.copy()
    out["map_era"] = "modelled_pre_clearing_svtm"
    out["interpretation"] = (
        "SVTM pre-clearing (1750) modelled PCT extent — NOT a surveyed historic "
        "Yarrawa Brush boundary. Use for landscape context only."
    )
    return out


def tag_extant(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    out = gdf.copy()
    out["map_era"] = "extant_svtm"
    out["interpretation"] = (
        "SVTM extant PCT mapping (regional scale). Not a field survey substitute."
    )
    return out
