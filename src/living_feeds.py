"""
Living feeds for Twin Lakes / Ripple Effect StoryMap.

1) BioNet (+ optional iNaturalist) → season neighbours + threat grid refresh
2) Sentinel-2 greenness (Planetary Computer) → remnant vs cleared NDVI
3) NSW RFS major incidents → fire pressure near the study AOI
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import requests
from rasterio.mask import mask as rio_mask
from rasterio.warp import transform_geom
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

from clean_species_data import (
    aggregate_to_grid,
    bionet_records_to_gdf,
    build_analysis_grid,
    clean_species_observations,
    dedupe_observations,
)
from download_data import download_bionet_sightings
from utils import ensure_dirs, write_gdf


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _aoi_wgs84(settings: dict, logger: logging.Logger) -> gpd.GeoDataFrame:
    paths = settings["resolved_paths"]
    master = paths["gpkg_dir"] / str(settings["outputs"]["master_gpkg"])
    phase1 = paths["interim_dir"] / str(settings["outputs"]["phase1_interim_gpkg"])
    src = master if master.is_file() else phase1
    study = gpd.read_file(src, layer="study_area")
    return study.to_crs(4326)


# ---------------------------------------------------------------------------
# 1) Species — BioNet + iNaturalist
# ---------------------------------------------------------------------------


def download_inaturalist_observations(
    settings: dict,
    aoi_wgs84: gpd.GeoDataFrame,
    logger: logging.Logger,
    *,
    force: bool = False,
) -> Path | None:
    """Research-grade iNaturalist observations in the AOI envelope."""
    dl = settings.get("downloads", {})
    if not bool(dl.get("inaturalist_enabled", True)):
        logger.info("iNaturalist disabled in settings")
        return None

    out = settings["resolved_paths"]["raw_dir"] / "species" / "inaturalist_aoi.parquet"
    ensure_dirs(out.parent)
    if not force and out.is_file() and out.stat().st_size > 0:
        logger.info("iNaturalist cache hit: %s", out)
        return out

    minx, miny, maxx, maxy = map(float, aoi_wgs84.total_bounds)
    endpoint = str(dl.get("inaturalist_api", "https://api.inaturalist.org/v1/observations"))
    records: list[dict] = []
    page = 1
    while page <= 20:
        params = {
            "swlat": miny,
            "swlng": minx,
            "nelat": maxy,
            "nelng": maxx,
            "quality_grade": "research",
            "per_page": 200,
            "page": page,
            "order_by": "observed_on",
            "order": "desc",
        }
        r = requests.get(endpoint, params=params, timeout=90, headers={"User-Agent": "robertson-ripple-effect/0.1"})
        r.raise_for_status()
        batch = r.json().get("results") or []
        if not batch:
            break
        for obs in batch:
            geo = obs.get("geojson") or {}
            coords = geo.get("coordinates")
            if not coords or len(coords) < 2:
                continue
            taxon = obs.get("taxon") or {}
            records.append(
                {
                    "source": "inaturalist",
                    "source_record_id": str(obs.get("id")),
                    "scientificName": taxon.get("name") or obs.get("species_guess") or "",
                    "vernacularName": (taxon.get("preferred_common_name") or "") if taxon else "",
                    "eventDate": obs.get("observed_on") or obs.get("time_observed_at") or "",
                    "year": int(str(obs.get("observed_on", "0"))[:4]) if obs.get("observed_on") else pd.NA,
                    "kingdom": "",
                    "taxon_group": (taxon.get("iconic_taxon_name") or "Unknown"),
                    "family": "",
                    "stateConservation": "",
                    "countryConservation": "",
                    "sensitivityClass": "Not Sensitive",
                    "decimalLongitude": float(coords[0]),
                    "decimalLatitude": float(coords[1]),
                    "coordinateUncertaintyInMeters": obs.get("positional_accuracy") or 100,
                    "basisOfRecord": "HumanObservation",
                }
            )
        logger.info("iNaturalist page=%s +%s (total %s)", page, len(batch), len(records))
        if len(batch) < 200:
            break
        page += 1

    pd.DataFrame(records).to_parquet(out, index=False)
    logger.info("Saved iNaturalist observations: %s -> %s", len(records), out)
    return out


def _inat_parquet_to_gdf(path: Path, crs_geo: str) -> gpd.GeoDataFrame:
    df = pd.read_parquet(path)
    if df.empty:
        return gpd.GeoDataFrame(columns=["geometry"], crs=crs_geo)
    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df["decimalLongitude"], df["decimalLatitude"]),
        crs=crs_geo,
    )
    gdf["is_threatened"] = False
    gdf["is_sensitive"] = False
    gdf["coord_flag"] = "ok"
    gdf["date_flag"] = "ok"
    gdf["interpretation"] = "iNaturalist research-grade public observation. Effort-biased."
    return gdf


def refresh_species_feed(
    settings: dict,
    logger: logging.Logger,
    *,
    force_download: bool = False,
) -> dict[str, Any]:
    """Refresh BioNet (+ iNat), rebuild threat grid + season neighbours."""
    paths = settings["resolved_paths"]
    study_cfg = settings["study_area"]
    sp = settings.get("species", {})
    live = settings.get("living_feeds", {})
    crs = str(study_cfg["crs_analysis"])
    crs_geo = str(study_cfg["crs_geographic"])
    season_months = int(live.get("season_months", 24))

    aoi = _aoi_wgs84(settings, logger)
    bionet_path = download_bionet_sightings(settings, aoi, logger, force=force_download)
    inat_path = download_inaturalist_observations(settings, aoi, logger, force=force_download)

    bionet_raw = pd.read_parquet(bionet_path)
    obs = bionet_records_to_gdf(bionet_raw)
    frames = [obs]
    if inat_path and inat_path.is_file():
        frames.append(_inat_parquet_to_gdf(inat_path, crs_geo))
    combined = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=crs_geo)

    master = paths["gpkg_dir"] / str(settings["outputs"]["master_gpkg"])
    study = gpd.read_file(master, layer="study_area")
    cleaned = clean_species_observations(
        combined,
        study_area=study,
        crs_analysis=crs,
        max_coordinate_uncertainty_m=float(sp.get("max_coordinate_uncertainty_m", 25000)),
        min_year_keep=int(sp.get("min_year_keep", 1950)),
        threatened_statuses=list(sp.get("threatened_state_statuses") or []),
    )
    cleaned = dedupe_observations(cleaned)

    try:
        grid = gpd.read_file(master, layer="analysis_grid_metrics")[["cell_id", "cell_area_ha", "geometry"]].to_crs(crs)
    except Exception:
        grid = build_analysis_grid(
            study,
            cell_size_m=float(settings.get("grid", {}).get("cell_size_m", 250)),
            crs_analysis=crs,
        )

    threat_mask = cleaned["is_threatened"].fillna(False) | cleaned["is_sensitive"].fillna(False)
    threat_grid = aggregate_to_grid(cleaned, grid, subset_mask=threat_mask, prefix="threat_")
    threat_grid = threat_grid.loc[threat_grid["threat_n_records"] > 0].copy()
    threat_grid["interpretation"] = (
        "Living-feed refresh: grid-aggregated threatened/sensitive public records. "
        "Do not reverse-engineer precise locations."
    )

    reserve = gpd.read_file(master, layer="robertson_nature_reserve").to_crs(crs)
    ru = unary_union(list(reserve.geometry))
    thr = cleaned.loc[cleaned["is_threatened"].fillna(False)].copy()
    if "is_sensitive" in thr.columns:
        thr = thr.loc[~thr["is_sensitive"].fillna(False)]
    cutoff = pd.Timestamp.now(tz="UTC") - pd.DateOffset(months=season_months)
    thr["event_ts"] = pd.to_datetime(thr.get("eventDate"), errors="coerce", utc=True)
    thr["dist_m"] = thr.geometry.distance(ru)
    near = thr.loc[thr["dist_m"] <= 5000].copy()
    year_cut = int(cutoff.year) - 1
    seasonal = near.loc[(near["event_ts"] >= cutoff) | (pd.to_numeric(near["year"], errors="coerce") >= year_cut)].copy()

    roster_rows = []
    src = seasonal if not seasonal.empty else near
    for (sci, vern, group, status), sub in src.groupby(
        ["scientificName", "vernacularName", "taxon_group", "stateConservation"], dropna=False
    ):
        roster_rows.append(
            {
                "Common name": str(vern) if pd.notna(vern) and str(vern).strip() else "—",
                "Scientific name": str(sci),
                "Group": str(group) if pd.notna(group) else "—",
                "NSW status": str(status) if pd.notna(status) else "—",
                "Public records": int(len(sub)),
                "Years": f"{int(sub['year'].min()) if pd.notna(sub['year'].min()) else '—'}–"
                f"{int(sub['year'].max()) if pd.notna(sub['year'].max()) else '—'}",
                "season_window": "season" if not seasonal.empty else "all_public_near",
            }
        )
    roster = pd.DataFrame(roster_rows)
    if not roster.empty:
        roster = roster.sort_values("Public records", ascending=False).reset_index(drop=True)

    twin = paths["twin_lakes_dir"]
    ensure_dirs(twin)
    gpkg = twin / str(live.get("living_gpkg", "living_layers.gpkg"))
    write_gdf(threat_grid.to_crs(crs), gpkg, layer="threatened_species_living")
    keep = [c for c in (
        "source", "source_record_id", "scientificName", "vernacularName", "eventDate", "year",
        "taxon_group", "stateConservation", "is_threatened", "is_sensitive", "geometry",
    ) if c in cleaned.columns]
    write_gdf(cleaned[keep].to_crs(crs), gpkg, layer="species_observations_living")
    roster_path = twin / "neighbours_season.csv"
    roster.to_csv(roster_path, index=False)

    return {
        "status": "ok",
        "refreshed_at": _now_iso(),
        "bionet_records_raw": int(len(bionet_raw)),
        "inat_records": int(len(pd.read_parquet(inat_path))) if inat_path and inat_path.is_file() else 0,
        "cleaned_records": int(len(cleaned)),
        "threatened_cells": int(len(threat_grid)),
        "neighbours_season_n": int(roster["Scientific name"].nunique()) if not roster.empty else 0,
        "neighbours_season_records": int(roster["Public records"].sum()) if not roster.empty else 0,
        "top_neighbour": str(roster.iloc[0]["Common name"]) if not roster.empty else None,
        "season_months": season_months,
        "roster_csv": str(roster_path),
        "why": (
            "Public listed-species records near the remnant show the landscape is used as refuge. "
            "This is association with habitat — not proof the reserve caused every sighting."
        ),
    }


# ---------------------------------------------------------------------------
# 2) Greenness — Sentinel-2 via Planetary Computer
# ---------------------------------------------------------------------------


def _sign_pc_href(sign_url: str, href: str) -> str:
    r = requests.get(sign_url, params={"href": href}, timeout=60)
    r.raise_for_status()
    return r.json().get("href") or href


def _mean_ndvi_for_polygons(
    red_href: str,
    nir_href: str,
    polygons: gpd.GeoDataFrame,
    logger: logging.Logger,
) -> float | None:
    if polygons is None or polygons.empty:
        return None
    geoms = []
    for g in polygons.geometry:
        if g is None or g.is_empty:
            continue
        geoms.append(mapping(g))
    if not geoms:
        return None
    try:
        with rasterio.open(red_href) as red_ds, rasterio.open(nir_href) as nir_ds:
            # Reproject polygon to raster CRS if needed
            if str(polygons.crs) != str(red_ds.crs):
                geoms = [
                    transform_geom(str(polygons.crs), str(red_ds.crs), g, precision=6) for g in geoms
                ]
            red, _ = rio_mask(red_ds, geoms, crop=True, filled=True, nodata=0)
            nir, _ = rio_mask(nir_ds, geoms, crop=True, filled=True, nodata=0)
            red_a = red.astype("float32")
            nir_a = nir.astype("float32")
            if red_ds.scales and red_ds.scales[0] not in (None, 1.0):
                red_a *= float(red_ds.scales[0])
            if nir_ds.scales and nir_ds.scales[0] not in (None, 1.0):
                nir_a *= float(nir_ds.scales[0])
            # Sentinel-2 L2A often needs /10000
            if float(np.nanmax(red_a)) > 2:
                red_a /= 10000.0
                nir_a /= 10000.0
            denom = nir_a + red_a
            ndvi = np.where(denom > 0, (nir_a - red_a) / denom, np.nan)
            valid = np.isfinite(ndvi) & (red_a > 0) & (nir_a > 0)
            if not valid.any():
                return None
            return float(np.nanmean(ndvi[valid]))
    except Exception as exc:
        logger.warning("NDVI sample failed: %s", exc)
        return None


def refresh_greenness_feed(settings: dict, logger: logging.Logger) -> dict[str, Any]:
    """Monthly-style Sentinel-2 NDVI contrast: remnant rainforest vs cleared."""
    paths = settings["resolved_paths"]
    live = settings.get("living_feeds", {})
    dl = settings.get("downloads", {})
    master = paths["gpkg_dir"] / str(settings["outputs"]["master_gpkg"])
    if not master.is_file():
        return {"status": "error", "message": "master gpkg missing"}

    rf = gpd.read_file(master, layer="rainforest_extant").to_crs(4326)
    cleared = gpd.read_file(master, layer="cleared_or_non_native").to_crs(4326)
    # Simplify / sample for speed
    rf_s = rf.copy()
    rf_s["geometry"] = rf_s.geometry.simplify(0.0003, preserve_topology=True)
    cl_s = cleared.copy()
    cl_s["geometry"] = cl_s.geometry.simplify(0.0004, preserve_topology=True)
    # Cap cleared sample area via representative clip to study
    study = gpd.read_file(master, layer="study_area").to_crs(4326)
    minx, miny, maxx, maxy = map(float, study.total_bounds)
    bbox = [minx, miny, maxx, maxy]

    lookback = int(live.get("greenness_lookback_days", 420))
    cloud_max = int(live.get("greenness_cloud_max", 25))
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=lookback)
    stac = str(dl.get("planetary_computer_stac"))
    sign = str(dl.get("planetary_computer_sign"))

    body = {
        "collections": ["sentinel-2-l2a"],
        "bbox": bbox,
        "datetime": f"{start.date().isoformat()}/{end.date().isoformat()}",
        "query": {"eo:cloud_cover": {"lt": cloud_max}},
        "limit": 8,
        "sortby": [{"field": "datetime", "direction": "desc"}],
    }
    r = requests.post(stac, json=body, timeout=120)
    r.raise_for_status()
    feats = r.json().get("features") or []
    if not feats:
        return {
            "status": "empty",
            "message": "No low-cloud Sentinel-2 scenes found for AOI window",
            "refreshed_at": _now_iso(),
        }

    chosen = feats[0]
    props = chosen.get("properties") or {}
    assets = chosen.get("assets") or {}
    red_asset = assets.get("B04") or assets.get("visual")
    nir_asset = assets.get("B08")
    if not red_asset or not nir_asset:
        return {"status": "error", "message": "Scene missing B04/B08 assets", "refreshed_at": _now_iso()}

    red_href = _sign_pc_href(sign, red_asset["href"])
    nir_href = _sign_pc_href(sign, nir_asset["href"])
    logger.info("Greenness scene %s cloud=%s", chosen.get("id"), props.get("eo:cloud_cover"))

    # Use dissolved masks for sampling
    rf_u = gpd.GeoDataFrame(geometry=[unary_union(list(rf_s.geometry))], crs=4326)
    cl_u = gpd.GeoDataFrame(geometry=[unary_union(list(cl_s.geometry))], crs=4326)
    # Shrink cleared sample with intersection study to keep runtime reasonable
    cl_u = gpd.overlay(cl_u, study, how="intersection") if not cl_u.empty else cl_u

    ndvi_rf = _mean_ndvi_for_polygons(red_href, nir_href, rf_u, logger)
    ndvi_cl = _mean_ndvi_for_polygons(red_href, nir_href, cl_u, logger)
    delta = None
    if ndvi_rf is not None and ndvi_cl is not None:
        delta = float(ndvi_rf - ndvi_cl)

    twin = paths["twin_lakes_dir"]
    ensure_dirs(twin)
    summary = pd.DataFrame(
        [
            {"class": "rainforest_remnant", "mean_ndvi": ndvi_rf},
            {"class": "cleared_non_native", "mean_ndvi": ndvi_cl},
            {"class": "delta_remnant_minus_cleared", "mean_ndvi": delta},
        ]
    )
    summary_path = twin / "greenness_summary.csv"
    summary.to_csv(summary_path, index=False)

    return {
        "status": "ok" if delta is not None else "partial",
        "refreshed_at": _now_iso(),
        "scene_id": chosen.get("id"),
        "scene_datetime": props.get("datetime"),
        "cloud_cover": props.get("eo:cloud_cover"),
        "ndvi_rainforest": ndvi_rf,
        "ndvi_cleared": ndvi_cl,
        "ndvi_delta": delta,
        "summary_csv": str(summary_path),
        "why": (
            "Higher greenness in remnant rainforest than cleared land is a living signal that "
            "this small protected patch sits inside vegetation that still functions as forest — "
            "supporting the case that the remnant (and growing it) matters for the community."
        ),
    }


# ---------------------------------------------------------------------------
# 3) Fire / hotspot pressure — NSW RFS major incidents
# ---------------------------------------------------------------------------


def _fetch_rfs_incidents(url: str, logger: logging.Logger) -> gpd.GeoDataFrame:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json,text/plain,*/*",
    }
    r = requests.get(url, timeout=90, headers=headers)
    r.raise_for_status()
    payload = r.json()
    feats = payload.get("features") or []
    rows = []
    for f in feats:
        props = f.get("properties") or {}
        geom = f.get("geometry")
        if not geom:
            continue
        try:
            g = shape(geom)
        except Exception:
            continue
        rows.append(
            {
                "title": props.get("title") or props.get("name") or "RFS incident",
                "status": props.get("status") or props.get("alertLevel") or "",
                "guid": props.get("guid") or props.get("link") or "",
                "updated": props.get("updated") or props.get("pubDate") or "",
                "source": "nsw_rfs",
                "geometry": g,
            }
        )
    if not rows:
        return gpd.GeoDataFrame(columns=["title", "status", "geometry"], crs=4326)
    return gpd.GeoDataFrame(rows, crs=4326)


def _fetch_firms_hotspots(aoi_wgs84: gpd.GeoDataFrame, logger: logging.Logger) -> gpd.GeoDataFrame:
    """NASA FIRMS VIIRS 7-day Australia/NZ CSV (public, no key)."""
    urls = [
        "https://firms.modaps.eosdis.nasa.gov/data/active_fire/noaa-21-viirs-c2/csv/J1_VIIRS_C2_Australia_NewZealand_7d.csv",
        "https://firms.modaps.eosdis.nasa.gov/data/active_fire/suomi-npp-viirs-c2/csv/SUOMI_VIIRS_C2_Australia_NewZealand_7d.csv",
    ]
    minx, miny, maxx, maxy = map(float, aoi_wgs84.total_bounds)
    # pad envelope slightly
    pad = 0.15
    minx, miny, maxx, maxy = minx - pad, miny - pad, maxx + pad, maxy + pad
    frames = []
    for url in urls:
        try:
            df = pd.read_csv(url)
            logger.info("FIRMS rows from %s: %s", url.split("/")[-1], len(df))
        except Exception as exc:
            logger.warning("FIRMS fetch failed (%s): %s", url, exc)
            continue
        if df.empty or "latitude" not in df.columns:
            continue
        sub = df.loc[
            (df["latitude"] >= miny)
            & (df["latitude"] <= maxy)
            & (df["longitude"] >= minx)
            & (df["longitude"] <= maxx)
        ].copy()
        if sub.empty:
            continue
        gdf = gpd.GeoDataFrame(
            {
                "title": "VIIRS hotspot",
                "status": sub.get("confidence", pd.Series([""] * len(sub))).astype(str),
                "guid": sub.get("acq_date", pd.Series([""] * len(sub))).astype(str),
                "updated": sub.get("acq_date", pd.Series([""] * len(sub))).astype(str),
                "source": "nasa_firms_viirs",
            },
            geometry=gpd.points_from_xy(sub["longitude"], sub["latitude"]),
            crs=4326,
        )
        frames.append(gdf)
    if not frames:
        return gpd.GeoDataFrame(columns=["title", "status", "geometry"], crs=4326)
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=4326)


def refresh_fire_feed(settings: dict, logger: logging.Logger) -> dict[str, Any]:
    """Fire pressure near AOI: NSW RFS incidents if available, else NASA FIRMS VIIRS."""
    paths = settings["resolved_paths"]
    live = settings.get("living_feeds", {})
    dl = settings.get("downloads", {})
    crs = str(settings["study_area"]["crs_analysis"])
    buf_km = float(live.get("fire_buffer_km", 12.5))

    master = paths["gpkg_dir"] / str(settings["outputs"]["master_gpkg"])
    study = gpd.read_file(master, layer="study_area").to_crs(crs)
    aoi = study.to_crs(4326)
    watch = gpd.GeoDataFrame(geometry=[unary_union(list(study.geometry)).buffer(buf_km * 1000)], crs=crs)

    fire = gpd.GeoDataFrame(columns=["title", "status", "geometry"], crs=4326)
    source_used = None
    notes = []

    # 1) NSW RFS major incidents
    try:
        fire = _fetch_rfs_incidents(str(dl.get("rfs_major_incidents")), logger)
        if not fire.empty:
            fire = fire.to_crs(crs)
            fire = fire.loc[fire.intersects(watch.geometry.iloc[0])].copy()
            source_used = "nsw_rfs"
    except Exception as exc:
        notes.append(f"RFS unavailable ({exc})")
        logger.warning("RFS feed unavailable: %s", exc)

    # 2) NASA FIRMS VIIRS 7-day hotspots
    if fire.empty:
        try:
            fire = _fetch_firms_hotspots(aoi, logger)
            if not fire.empty:
                fire = fire.to_crs(crs)
                fire = fire.loc[fire.intersects(watch.geometry.iloc[0])].copy()
                source_used = "nasa_firms_viirs_7d"
        except Exception as exc:
            notes.append(f"FIRMS unavailable ({exc})")
            logger.warning("FIRMS feed unavailable: %s", exc)

    twin = paths["twin_lakes_dir"]
    ensure_dirs(twin)
    gpkg = twin / str(live.get("living_gpkg", "living_layers.gpkg"))
    if fire.empty:
        empty = gpd.GeoDataFrame(
            columns=["title", "status", "guid", "updated", "source", "geometry"], crs=crs
        )
        write_gdf(empty, gpkg, layer="fire_incidents_living")
    else:
        write_gdf(fire.to_crs(crs), gpkg, layer="fire_incidents_living")

    prone_ha = None
    try:
        prone = gpd.read_file(master, layer="bushfire_prone_land").to_crs(crs)
        prone_ha = float(prone.geometry.area.sum() / 10000.0)
    except Exception:
        pass

    return {
        "status": "ok",
        "refreshed_at": _now_iso(),
        "source": source_used or "none_active",
        "notes": notes,
        "incidents_in_watch": int(len(fire)),
        "watch_buffer_km": buf_km,
        "incident_titles": fire["title"].astype(str).head(8).tolist() if not fire.empty else [],
        "bushfire_prone_ha_in_master": prone_ha,
        "why": (
            "Fire is one reason a small rainforest remnant matters: it is a cool, moist refuge in a "
            "fire-prone landscape. Hotspots nearby are a caution — not a claim the reserve stops fire."
        ),
    }


# ---------------------------------------------------------------------------
# Package writer
# ---------------------------------------------------------------------------


def _hydrate_feed_from_disk(twin: Path, key: str) -> dict[str, Any] | None:
    """Rebuild a feed summary from on-disk Twin Lakes artifacts when a step was skipped."""
    if key == "species":
        roster_path = twin / "neighbours_season.csv"
        if not roster_path.is_file():
            return None
        roster = pd.read_csv(roster_path)
        top = None
        if not roster.empty and "Common name" in roster.columns:
            top = str(roster.iloc[0]["Common name"])
        n = int(roster["Scientific name"].nunique()) if not roster.empty and "Scientific name" in roster.columns else 0
        records = int(pd.to_numeric(roster.get("Public records"), errors="coerce").fillna(0).sum()) if not roster.empty else 0
        return {
            "status": "ok",
            "refreshed_at": None,
            "neighbours_season_n": n,
            "neighbours_season_records": records,
            "top_neighbour": top,
            "roster_csv": str(roster_path),
            "hydrated_from_disk": True,
            "why": (
                "Public listed-species records near the remnant show the landscape is used as refuge. "
                "This is association with habitat — not proof the reserve caused every sighting."
            ),
        }
    if key == "greenness":
        summary_path = twin / "greenness_summary.csv"
        if not summary_path.is_file():
            return None
        summary = pd.read_csv(summary_path)
        vals = {str(r["class"]): float(r["mean_ndvi"]) for _, r in summary.iterrows()}
        return {
            "status": "ok",
            "refreshed_at": None,
            "ndvi_rainforest": vals.get("rainforest_remnant"),
            "ndvi_cleared": vals.get("cleared_non_native"),
            "ndvi_delta": vals.get("delta_remnant_minus_cleared"),
            "summary_csv": str(summary_path),
            "hydrated_from_disk": True,
            "why": (
                "Higher greenness in remnant rainforest than cleared land is a living signal that this small "
                "protected patch sits inside vegetation that still functions as forest — supporting the case "
                "that the remnant (and growing it) matters for the community."
            ),
        }
    if key == "fire":
        gpkg = twin / "living_layers.gpkg"
        if not gpkg.is_file():
            return None
        try:
            fire = gpd.read_file(gpkg, layer="fire_incidents_living")
        except Exception:
            return None
        titles = [str(t) for t in fire["title"].head(8).tolist()] if "title" in fire.columns and not fire.empty else []
        return {
            "status": "ok",
            "refreshed_at": None,
            "incidents_in_watch": int(len(fire)),
            "incident_titles": titles,
            "hydrated_from_disk": True,
            "why": (
                "Fire is one reason a small rainforest remnant matters: it is a cool, moist refuge in a "
                "fire-prone landscape. Hotspots nearby are a caution — not a claim the reserve stops fire."
            ),
        }
    return None


def write_story_package(settings: dict, feeds: dict[str, Any], logger: logging.Logger) -> Path:
    paths = settings["resolved_paths"]
    live = settings.get("living_feeds", {})
    twin = paths["twin_lakes_dir"]
    ensure_dirs(twin)
    out = twin / str(live.get("package_json", "story_package.json"))

    prev_feeds: dict[str, Any] = {}
    if out.is_file():
        try:
            prev_feeds = dict(json.loads(out.read_text(encoding="utf-8")).get("feeds") or {})
        except Exception:
            prev_feeds = {}

    merged: dict[str, Any] = {}
    for key in ("species", "greenness", "fire"):
        incoming = feeds.get(key) or {}
        if incoming.get("status") == "skipped":
            keep = prev_feeds.get(key) if prev_feeds.get(key, {}).get("status") not in (None, "skipped") else None
            merged[key] = keep or _hydrate_feed_from_disk(twin, key) or incoming
        else:
            merged[key] = incoming

    master = paths["gpkg_dir"] / str(settings["outputs"]["master_gpkg"])
    baseline = {}
    if master.is_file():
        reserve = gpd.read_file(master, layer="robertson_nature_reserve").to_crs(settings["study_area"]["crs_analysis"])
        rf = gpd.read_file(master, layer="rainforest_extant").to_crs(settings["study_area"]["crs_analysis"])
        baseline = {
            "reserve_ha": float(reserve.geometry.area.sum() / 10000.0),
            "rainforest_ha": float(rf.geometry.area.sum() / 10000.0),
        }

    package = {
        "project": "The Ripple Effect",
        "hub": "Twin Lakes living story package",
        "generated_at": _now_iso(),
        "baseline": baseline,
        "feeds": merged,
        "evidence_ladder": {
            "place_facts": "Tiny gazetted reserve inside a larger rainforest remnant on volcanic/cool terrain.",
            "landscape_function": "Remnant core, nearby patches, streams and edges explain how life can persist and grow.",
            "living_association": "Public species records, greenness contrast, and fire context update why neighbours should care — without claiming the reserve caused every outcome.",
        },
        "paths": {
            "living_gpkg": str(twin / str(live.get("living_gpkg", "living_layers.gpkg"))),
            "neighbours_season_csv": str(twin / "neighbours_season.csv"),
            "greenness_summary_csv": str(twin / "greenness_summary.csv"),
        },
    }
    out.write_text(json.dumps(package, indent=2), encoding="utf-8")
    logger.info("Wrote Twin Lakes story package: %s", out)
    return out
