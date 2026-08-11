"""
PYTHON DATA PREP — BioNet/ALA cleaning, dedupe, sensitivity aggregation rules.

Public dashboards must not expose precise sensitive species coordinates.
Sensitive classes are excluded from the public point layer and retained only
via grid aggregation (BioNet public coords are already denatured).
"""

from __future__ import annotations

import re
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box


BIONET_SELECT = [
    "catalogNumber",
    "occurrenceID",
    "scientificName",
    "vernacularName",
    "decimalLatitude",
    "decimalLongitude",
    "eventDate",
    "kingdom",
    "class",
    "family",
    "order",
    "genus",
    "taxonRank",
    "stateConservation",
    "countryConservation",
    "sensitivityClass",
    "coordinateUncertaintyInMeters",
    "dataGeneralizations",
    "informationWithheld",
    "occurrenceStatus",
    "basisOfRecord",
    "protectedInNSW",
    "establishmentMeans",
    "sortOrder",
]


def build_analysis_grid(
    study_area: gpd.GeoDataFrame,
    *,
    cell_size_m: float,
    crs_analysis: str,
) -> gpd.GeoDataFrame:
    """Build a fishnet clipped to the study area."""
    sa = study_area.to_crs(crs_analysis)
    minx, miny, maxx, maxy = sa.total_bounds
    xs = np.arange(minx, maxx + cell_size_m, cell_size_m)
    ys = np.arange(miny, maxy + cell_size_m, cell_size_m)
    cells = []
    cell_ids = []
    idx = 0
    for y0 in ys[:-1]:
        for x0 in xs[:-1]:
            cells.append(box(x0, y0, x0 + cell_size_m, y0 + cell_size_m))
            cell_ids.append(f"c{idx:06d}")
            idx += 1
    grid = gpd.GeoDataFrame({"cell_id": cell_ids}, geometry=cells, crs=crs_analysis)
    clipped = gpd.overlay(grid, sa[["geometry"]], how="intersection", keep_geom_type=True)
    clipped = clipped[clipped.geometry.area > 1.0].copy()
    clipped["cell_area_ha"] = clipped.geometry.area / 10000.0
    return clipped.reset_index(drop=True)


def bionet_records_to_gdf(records: list[dict[str, Any]] | pd.DataFrame) -> gpd.GeoDataFrame:
    df = records if isinstance(records, pd.DataFrame) else pd.DataFrame(records)
    if df.empty:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    out = df.copy()
    out["source"] = "bionet"
    out["source_record_id"] = out.get("catalogNumber", pd.Series(dtype=str)).astype(str)
    return _frame_to_points(out)


def ala_records_to_gdf(records: list[dict[str, Any]] | pd.DataFrame) -> gpd.GeoDataFrame:
    df = records if isinstance(records, pd.DataFrame) else pd.DataFrame(records)
    if df.empty:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

    def _col(*names: str) -> pd.Series:
        for name in names:
            if name in df.columns:
                return df[name]
        return pd.Series([None] * len(df), index=df.index)

    sens_raw = _col("sensitive")
    out = pd.DataFrame(
        {
            "source": "ala",
            "source_record_id": _col("uuid", "occurrenceID").astype(str),
            "catalogNumber": _col("raw_catalogNumber", "catalogNumber"),
            "occurrenceID": _col("occurrenceID", "uuid"),
            "scientificName": _col("scientificName", "raw_scientificName"),
            "vernacularName": _col("vernacularName"),
            "decimalLatitude": _col("decimalLatitude"),
            "decimalLongitude": _col("decimalLongitude"),
            "eventDate": _col("eventDate"),
            "kingdom": _col("kingdom"),
            "class": _col("classs", "class"),
            "family": _col("family"),
            "order": _col("order"),
            "genus": _col("genus"),
            "taxonRank": _col("taxonRank"),
            "stateConservation": _col("stateConservation"),
            "countryConservation": _col("countryConservation"),
            "sensitivityClass": sens_raw.map(
                lambda v: "Sensitive" if v in (True, "true", "True", "yes") else "Not Sensitive"
            ),
            "coordinateUncertaintyInMeters": _col("coordinateUncertaintyInMeters"),
            "dataGeneralizations": _col("dataGeneralizations"),
            "informationWithheld": _col("informationWithheld"),
            "occurrenceStatus": _col("occurrenceStatus"),
            "basisOfRecord": _col("basisOfRecord"),
            "protectedInNSW": None,
            "establishmentMeans": _col("establishmentMeans"),
        }
    )
    return _frame_to_points(out)


def _frame_to_points(df: pd.DataFrame) -> gpd.GeoDataFrame:
    out = df.copy()
    out["decimalLatitude"] = pd.to_numeric(out.get("decimalLatitude"), errors="coerce")
    out["decimalLongitude"] = pd.to_numeric(out.get("decimalLongitude"), errors="coerce")
    valid = out["decimalLatitude"].notna() & out["decimalLongitude"].notna()
    out = out.loc[valid].copy()
    if out.empty:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    geom = gpd.points_from_xy(out["decimalLongitude"], out["decimalLatitude"])
    return gpd.GeoDataFrame(out, geometry=geom, crs="EPSG:4326")


def _parse_year(series: pd.Series) -> pd.Series:
    """Extract year from ISO dates or ALA epoch milliseconds."""
    years = pd.Series(pd.NA, index=series.index, dtype="Int64")
    text = series.fillna("").astype(str)
    # ISO / date-like
    m = text.str.extract(r"(?P<y>(?:19|20)\d{2})", expand=True)["y"]
    years = pd.to_numeric(m, errors="coerce").astype("Int64")
    # epoch ms (ALA sometimes returns numeric eventDate)
    numeric = pd.to_numeric(series, errors="coerce")
    epoch_mask = numeric.notna() & (numeric > 1e11)
    if epoch_mask.any():
        epoch_years = pd.to_datetime(numeric.loc[epoch_mask], unit="ms", errors="coerce").dt.year
        years.loc[epoch_mask] = epoch_years.astype("Int64")
    return years


def clean_species_observations(
    gdf: gpd.GeoDataFrame,
    *,
    study_area: gpd.GeoDataFrame,
    crs_analysis: str,
    max_coordinate_uncertainty_m: float,
    min_year_keep: int,
    threatened_statuses: list[str],
) -> gpd.GeoDataFrame:
    """Clip, flag, and standardise species observations."""
    if gdf.empty:
        return gdf

    out = gdf.copy()
    # Clip to study polygon (precise)
    sa = study_area.to_crs("EPSG:4326")
    out = gpd.clip(out, sa)
    if out.empty:
        return out

    out["coordinateUncertaintyInMeters"] = pd.to_numeric(
        out.get("coordinateUncertaintyInMeters"), errors="coerce"
    )
    out["year"] = _parse_year(out.get("eventDate", pd.Series(index=out.index)))
    out["taxon_group"] = out.get("class", pd.Series(index=out.index)).fillna("Unknown").astype(str)
    # Plants often have empty class — use kingdom
    plant_mask = out.get("kingdom", pd.Series(index=out.index)).fillna("").astype(str).str.contains(
        "Plantae", case=False, na=False
    )
    out.loc[plant_mask & out["taxon_group"].isin(["", "Unknown", "nan", "None"]), "taxon_group"] = (
        "Plantae"
    )

    threatened_set = {s.lower() for s in threatened_statuses}
    listed_pat = re.compile(
        r"critically endangered|\bendangered\b|\bvulnerable\b|\bextinct\b",
        re.IGNORECASE,
    )

    def _is_listed(val: object) -> bool:
        text = str(val or "").strip()
        if not text or text.lower() == "not listed":
            return False
        if text.lower() in threatened_set:
            return True
        return bool(listed_pat.search(text))

    state = out.get("stateConservation", pd.Series(index=out.index)).fillna("").astype(str)
    country = out.get("countryConservation", pd.Series(index=out.index)).fillna("").astype(str)
    out["is_threatened"] = state.map(_is_listed) | country.map(_is_listed)

    sens = out.get("sensitivityClass", pd.Series(index=out.index)).fillna("Not Sensitive").astype(str)
    out["sensitivityClass"] = sens
    out["is_sensitive"] = ~sens.str.fullmatch(r"Not Sensitive", case=False, na=False)

    unc = out["coordinateUncertaintyInMeters"]
    out["coord_flag"] = "ok"
    out.loc[unc.isna(), "coord_flag"] = "uncertainty_missing"
    out.loc[unc > max_coordinate_uncertainty_m, "coord_flag"] = "uncertainty_high"
    out.loc[out["year"].isna(), "date_flag"] = "year_missing"
    out.loc[out["year"].notna() & (out["year"] < min_year_keep), "date_flag"] = "year_old"
    out["date_flag"] = out.get("date_flag", pd.Series(index=out.index)).fillna("ok")

    # Drop absent / invalid occurrence status when present
    if "occurrenceStatus" in out.columns:
        status = out["occurrenceStatus"].fillna("").astype(str).str.lower()
        out = out.loc[~status.isin(["absent", "excluded"])].copy()

    # Drop records with missing scientific name
    out = out.loc[out["scientificName"].fillna("").astype(str).str.len() > 0].copy()

    # Analysis CRS for later joins
    out = out.to_crs(crs_analysis)
    out["interpretation"] = (
        "Public occurrence record. Effort-biased. Sensitive taxa may be denatured; "
        "do not treat coordinates as survey-precise."
    )
    return out.reset_index(drop=True)


def dedupe_observations(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Prefer BioNet when ALA duplicates the same species/day/rounded location."""
    if gdf.empty:
        return gdf
    out = gdf.copy()
    lat = out.to_crs("EPSG:4326").geometry.y.round(4)
    lon = out.to_crs("EPSG:4326").geometry.x.round(4)
    day = out.get("eventDate", pd.Series(index=out.index)).fillna("").astype(str).str.slice(0, 10)
    out["_dedupe_key"] = (
        out["scientificName"].fillna("").astype(str).str.lower()
        + "|"
        + lat.astype(str)
        + "|"
        + lon.astype(str)
        + "|"
        + day
    )
    out["_src_rank"] = out["source"].map({"bionet": 0, "ala": 1}).fillna(2)
    out = out.sort_values(["_dedupe_key", "_src_rank", "source_record_id"])
    out = out.drop_duplicates("_dedupe_key", keep="first")
    return out.drop(columns=["_dedupe_key", "_src_rank"]).reset_index(drop=True)


def public_point_layer(
    gdf: gpd.GeoDataFrame,
    *,
    sensitive_exclude: list[str],
) -> gpd.GeoDataFrame:
    """Points safe to map as individual markers (excludes sensitive classes)."""
    if gdf.empty:
        return gdf.copy()
    exclude = {s.lower() for s in sensitive_exclude}
    sens = gdf["sensitivityClass"].fillna("").astype(str).str.lower()
    return gdf.loc[~sens.isin(exclude)].copy()


def aggregate_to_grid(
    observations: gpd.GeoDataFrame,
    grid: gpd.GeoDataFrame,
    *,
    subset_mask: pd.Series | None = None,
    prefix: str = "",
) -> gpd.GeoDataFrame:
    """Spatial-join observations to grid and compute richness / counts."""
    if grid.empty:
        return grid.copy()
    base = grid[["cell_id", "cell_area_ha", "geometry"]].copy()
    obs = observations if subset_mask is None else observations.loc[subset_mask]
    if obs.empty:
        base[f"{prefix}n_records"] = 0
        base[f"{prefix}n_species"] = 0
        base[f"{prefix}year_min"] = pd.NA
        base[f"{prefix}year_max"] = pd.NA
        return base

    joined = gpd.sjoin(obs, base, how="inner", predicate="intersects")
    if joined.empty:
        base[f"{prefix}n_records"] = 0
        base[f"{prefix}n_species"] = 0
        base[f"{prefix}year_min"] = pd.NA
        base[f"{prefix}year_max"] = pd.NA
        return base

    agg = (
        joined.groupby("cell_id", as_index=False)
        .agg(
            n_records=("scientificName", "count"),
            n_species=("scientificName", "nunique"),
            year_min=("year", "min"),
            year_max=("year", "max"),
        )
        .rename(
            columns={
                "n_records": f"{prefix}n_records",
                "n_species": f"{prefix}n_species",
                "year_min": f"{prefix}year_min",
                "year_max": f"{prefix}year_max",
            }
        )
    )
    out = base.merge(agg, on="cell_id", how="left")
    for col in (f"{prefix}n_records", f"{prefix}n_species"):
        out[col] = out[col].fillna(0).astype(int)
    return out


def richness_by_group_year(observations: gpd.GeoDataFrame) -> pd.DataFrame:
    if observations.empty:
        return pd.DataFrame(columns=["taxon_group", "year", "n_records", "n_species"])
    tmp = observations.copy()
    tmp["year"] = tmp["year"].fillna(-1)
    return (
        tmp.groupby(["taxon_group", "year"], dropna=False, as_index=False)
        .agg(n_records=("scientificName", "count"), n_species=("scientificName", "nunique"))
        .sort_values(["taxon_group", "year"])
    )


def threatened_species_summary(observations: gpd.GeoDataFrame) -> pd.DataFrame:
    if observations.empty:
        return pd.DataFrame(
            columns=[
                "scientificName",
                "vernacularName",
                "stateConservation",
                "countryConservation",
                "n_records",
                "year_min",
                "year_max",
                "is_sensitive",
            ]
        )
    thr = observations.loc[observations["is_threatened"]].copy()
    if thr.empty:
        return pd.DataFrame(
            columns=[
                "scientificName",
                "vernacularName",
                "stateConservation",
                "countryConservation",
                "n_records",
                "year_min",
                "year_max",
                "is_sensitive",
            ]
        )
    return (
        thr.groupby(
            ["scientificName", "vernacularName", "stateConservation", "countryConservation"],
            dropna=False,
            as_index=False,
        )
        .agg(
            n_records=("scientificName", "count"),
            year_min=("year", "min"),
            year_max=("year", "max"),
            is_sensitive=("is_sensitive", "max"),
        )
        .sort_values("n_records", ascending=False)
    )
