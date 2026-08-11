"""
Phase 1 (revised) — Robertson Nature Reserve ecological profile.

Computes transparent reserve metrics from existing analysis layers,
attempts CEEC/TEC indicative download, and exports:
  - outputs/reports/reserve_ecological_profile.md
  - outputs/csv/reserve_ecological_profile.csv
  - outputs/csv/reserve_ecological_profile.json
  - data/interim/phase1_reserve_profile.gpkg
  - optional CEEC raw cache under data/raw/vegetation/

No composite importance scores. Metrics are listed separately.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
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
from utils import (  # noqa: E402
    append_qa_rows,
    arcgis_query_geojson,
    basic_vector_qa,
    ensure_dirs,
    setup_logging,
    to_analysis_crs,
    write_gdf,
)


PROFILE_VERSION = "1.0.0"

# Published listing context (not invented scores)
TEC_PUBLISHED = {
    "tec_name": "Robertson Rainforest in the Sydney Basin Bioregion",
    "nsw_status": "Endangered Ecological Community",
    "epbc_status": "Critically Endangered",
    "nsw_determination_url": (
        "https://www.environment.nsw.gov.au/topics/animals-and-plants/threatened-species/"
        "nsw-threatened-species-scientific-committee/determinations/final-determinations/"
        "2000-2003/robertson-rainforest-sydney-basin-bioregion-endangered-ecological-community-listing"
    ),
    "bionet_profile_url": "https://threatenedspecies.bionet.nsw.gov.au/profile?id=20393",
    "associated_pct_primary": "3047 Sydney Montane Basalt Rainforest",
    "evidence_tag": "PUBLISHED",
}


def _area_ha(geom) -> float:
    return float(geom.area) / 10000.0


def _safe_intersect_area_ha(left: gpd.GeoDataFrame, mask_geom, crs: str) -> float:
    if left is None or left.empty:
        return 0.0
    g = to_analysis_crs(left, crs)
    try:
        clipped = gpd.clip(g, mask_geom)
    except Exception:
        clipped = g[g.intersects(mask_geom)].copy()
        if clipped.empty:
            return 0.0
        clipped["geometry"] = clipped.geometry.intersection(mask_geom)
    if clipped.empty:
        return 0.0
    return float(clipped.geometry.area.sum()) / 10000.0


def _majority_attr(gdf: gpd.GeoDataFrame, field: str, mask_geom, crs: str) -> str:
    if gdf is None or gdf.empty or field not in gdf.columns:
        return "unknown"
    g = to_analysis_crs(gdf, crs)
    try:
        clipped = gpd.clip(g, mask_geom)
    except Exception:
        clipped = g[g.intersects(mask_geom)].copy()
    if clipped.empty:
        return "unknown"
    clipped = clipped.copy()
    clipped["_a"] = clipped.geometry.area
    top = clipped.groupby(field, dropna=False)["_a"].sum().sort_values(ascending=False)
    if top.empty:
        return "unknown"
    return str(top.index[0])


def download_ceec_labels(
    settings: dict[str, Any],
    study_area: gpd.GeoDataFrame,
    logger,
) -> gpd.GeoDataFrame:
    """Download CEEC label polygons for AOI (EPSG:4283 service)."""
    paths = settings["resolved_paths"]
    dl = settings["downloads"]
    out_path = paths["raw_dir"] / "vegetation" / "ceec_labels_aoi_raw.gpkg"
    layer_name = "ceec_labels"
    ensure_dirs(out_path.parent)

    if out_path.is_file() and out_path.stat().st_size > 0:
        logger.info("CEEC cache hit: %s", out_path)
        return gpd.read_file(out_path, layer=layer_name)

    query_url = str(dl.get("ceec_labels_query") or "")
    if not query_url:
        logger.warning("No ceec_labels_query configured")
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4283")

    aoi_4283 = study_area.to_crs("EPSG:4283")
    geom = unary_union(list(aoi_4283.geometry))
    try:
        gdf = arcgis_query_geojson(
            query_url,
            where="1=1",
            out_fields="OBJECTID,VIS_ID,CEEC_NSW,CEEC_EPBC,CEEC_NSW_N,CEEC_EPBC_,Comments,VERDATE",
            geometry=geom,
            in_sr=4283,
            out_sr=4283,
            page_size=500,
            logger=logger,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("CEEC download failed: %s", exc)
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4283")

    if gdf.empty:
        logger.warning("CEEC query returned 0 features for AOI")
        write_gdf(gdf, out_path, layer=layer_name)
        return gdf

    gdf["interpretation"] = (
        "Indicative CEEC mapping from NSW VIS/CEEC_NSW labels — "
        "confirm against listing determination; not a cadastral TEC boundary."
    )
    write_gdf(gdf, out_path, layer=layer_name)
    logger.info("Saved CEEC labels: %s features -> %s", len(gdf), out_path)

    # Update data_sources.csv status
    csv_path = paths["data_sources_csv"]
    if csv_path.is_file():
        src = pd.read_csv(csv_path)
        mask = src["dataset_id"] == "tec_nsw"
        src.loc[mask, "status"] = "Downloaded"
        src.loc[mask, "download_date"] = date.today().isoformat()
        src.to_csv(csv_path, index=False)
    return gdf


def _species_buffer_stats(
    species: gpd.GeoDataFrame,
    reserve_geom,
    buffer_m: float,
    crs: str,
) -> dict[str, Any]:
    if species is None or species.empty:
        return {
            "n_records": 0,
            "n_species": 0,
            "n_threatened_records": 0,
            "n_threatened_species": 0,
            "n_flora_species": 0,
            "n_fauna_species": 0,
        }
    g = to_analysis_crs(species, crs)
    buf = reserve_geom.buffer(buffer_m)
    hit = g[g.intersects(buf)].copy()
    if hit.empty:
        return {
            "n_records": 0,
            "n_species": 0,
            "n_threatened_records": 0,
            "n_threatened_species": 0,
            "n_flora_species": 0,
            "n_fauna_species": 0,
        }
    sci = "scientificName" if "scientificName" in hit.columns else None
    n_species = int(hit[sci].nunique()) if sci else 0
    threatened = hit
    if "is_threatened" in hit.columns:
        threatened = hit[hit["is_threatened"] == True]  # noqa: E712
    elif "stateConservation" in hit.columns:
        threatened = hit[
            hit["stateConservation"].isin(
                ["Critically Endangered", "Endangered", "Vulnerable"]
            )
        ]
    n_thr_sp = int(threatened[sci].nunique()) if sci and not threatened.empty else 0
    flora = hit
    if "taxon_group" in hit.columns:
        flora = hit[hit["taxon_group"].astype(str).str.contains("Flora|Plant", case=False, na=False)]
    elif "kingdom" in hit.columns:
        flora = hit[hit["kingdom"].astype(str).str.contains("Plant", case=False, na=False)]
    n_flora = int(flora[sci].nunique()) if sci and not flora.empty else 0
    n_fauna = max(n_species - n_flora, 0)
    return {
        "n_records": int(len(hit)),
        "n_species": n_species,
        "n_threatened_records": int(len(threatened)),
        "n_threatened_species": n_thr_sp,
        "n_flora_species": n_flora,
        "n_fauna_species": n_fauna,
    }


def _zonal_raster_mean(raster_path: Path, geom, crs: str) -> float | None:
    if not raster_path.is_file():
        return None
    try:
        import rasterio
        from rasterio.mask import mask as rio_mask
        from shapely.geometry import mapping
    except ImportError:
        return None

    with rasterio.open(raster_path) as src:
        gdf = gpd.GeoDataFrame(geometry=[geom], crs=crs)
        gdf = gdf.to_crs(src.crs)
        try:
            out_img, _ = rio_mask(src, [mapping(gdf.geometry.iloc[0])], crop=True, filled=True)
        except ValueError:
            return None
        data = out_img[0].astype("float64")
        nodata = src.nodata
        if nodata is not None:
            data = np.where(data == nodata, np.nan, data)
        if np.all(np.isnan(data)):
            return None
        return float(np.nanmean(data))


def build_profile(settings: dict[str, Any], logger) -> tuple[dict[str, Any], gpd.GeoDataFrame, gpd.GeoDataFrame]:
    paths = settings["resolved_paths"]
    crs = str(settings["study_area"]["crs_analysis"])
    master = paths["gpkg_dir"] / str(settings.get("outputs", {}).get("master_gpkg", "robertson_conservation.gpkg"))
    if not master.is_file():
        master = paths["processed_dir"] / master.name
    if not master.is_file():
        raise FileNotFoundError(f"Master GPKG not found: {master}")

    logger.info("Loading master layers from %s", master)
    reserve = gpd.read_file(master, layer="robertson_nature_reserve")
    study_area = gpd.read_file(master, layer="study_area")
    rainforest = gpd.read_file(master, layer="rainforest_extant")
    native = gpd.read_file(master, layer="native_vegetation")
    rainforest_patches = gpd.read_file(master, layer="rainforest_patches")
    core_patches = gpd.read_file(master, layer="core_habitat_patches")
    hydro = gpd.read_file(master, layer="hydro_lines")
    soils = gpd.read_file(master, layer="soil_landscapes")
    geology = gpd.read_file(master, layer="geology_rock_units")
    species = gpd.read_file(master, layer="species_observations_clean")
    cleared = gpd.read_file(master, layer="cleared_or_non_native")

    reserve = to_analysis_crs(reserve, crs)
    rgeom = unary_union(list(reserve.geometry))
    area_ha = _area_ha(rgeom)
    gaz = float(reserve.iloc[0].get("gaz_area_ha") or np.nan)
    gis_src = float(reserve.iloc[0].get("gis_area_ha") or np.nan)

    # Vegetation inside reserve
    rf_in_reserve_ha = _safe_intersect_area_ha(rainforest, rgeom, crs)
    native_in_reserve_ha = _safe_intersect_area_ha(native, rgeom, crs)
    pct_majority = _majority_attr(rainforest if not rainforest.empty else native, "pct_name", rgeom, crs)
    veg_class = _majority_attr(rainforest if not rainforest.empty else native, "veg_class", rgeom, crs)
    veg_form = _majority_attr(rainforest if not rainforest.empty else native, "veg_form", rgeom, crs)

    # List PCTs intersecting reserve
    veg_src = rainforest if not rainforest.empty else native
    pct_list = []
    if not veg_src.empty:
        vg = to_analysis_crs(veg_src, crs)
        try:
            hit = gpd.clip(vg, rgeom)
        except Exception:
            hit = vg[vg.intersects(rgeom)]
        if not hit.empty and "pct_name" in hit.columns:
            tmp = hit.copy()
            tmp["_a"] = tmp.geometry.area / 10000.0
            pct_list = (
                tmp.groupby(["pct_id", "pct_name"], dropna=False)["_a"]
                .sum()
                .reset_index()
                .sort_values("_a", ascending=False)
                .to_dict("records")
            )

    # Surrounding native vegetation rings
    rings = {}
    for dist_m in (500, 1000, 2000):
        ring = rgeom.buffer(dist_m)
        rings[f"native_veg_ha_within_{dist_m}m"] = round(_safe_intersect_area_ha(native, ring, crs), 3)
        rings[f"rainforest_ha_within_{dist_m}m"] = round(_safe_intersect_area_ha(rainforest, ring, crs), 3)
        cleared_ha = _safe_intersect_area_ha(cleared, ring, crs)
        rings[f"cleared_contrast_ha_within_{dist_m}m"] = round(cleared_ha, 3)

    # Nearest waterway
    hydro = to_analysis_crs(hydro, crs)
    if hydro.empty:
        dist_water_m = None
    else:
        dist_water_m = float(hydro.distance(rgeom).min())

    # Rainforest patches near reserve
    rp = to_analysis_crs(rainforest_patches, crs)
    # Exclude patches that are essentially the reserve itself (touch)
    if not rp.empty:
        rp = rp.copy()
        rp["dist_to_reserve_edge_m"] = rp.geometry.distance(rgeom)
        rp["touches_reserve"] = rp.geometry.intersects(rgeom.buffer(1.0))
        nearby = rp[~rp["touches_reserve"]].copy()
        n_rf_within_1km = int((nearby["dist_to_reserve_edge_m"] <= 1000).sum())
        n_rf_within_2km = int((nearby["dist_to_reserve_edge_m"] <= 2000).sum())
        nearest_rf_m = float(nearby["dist_to_reserve_edge_m"].min()) if not nearby.empty else None
        nearest_rf_ha = (
            float(nearby.loc[nearby["dist_to_reserve_edge_m"].idxmin(), "area_ha"])
            if not nearby.empty and "area_ha" in nearby.columns
            else None
        )
    else:
        n_rf_within_1km = n_rf_within_2km = 0
        nearest_rf_m = nearest_rf_ha = None

    # Nearest significant core patch (not touching reserve)
    cp = to_analysis_crs(core_patches, crs)
    if not cp.empty:
        cp = cp.copy()
        cp["dist_to_reserve_edge_m"] = cp.geometry.distance(rgeom)
        cp["touches_reserve"] = cp.geometry.intersects(rgeom.buffer(1.0))
        other = cp[~cp["touches_reserve"]]
        if not other.empty:
            idx = other["dist_to_reserve_edge_m"].idxmin()
            nearest_core_m = float(other.loc[idx, "dist_to_reserve_edge_m"])
            nearest_core_ha = float(other.loc[idx, "area_ha"]) if "area_ha" in other.columns else None
        else:
            nearest_core_m = nearest_core_ha = None
    else:
        nearest_core_m = nearest_core_ha = None

    # Terrain
    dem = paths["raster_dir"] / "phase5" / "dem_clip.tif"
    slope = paths["raster_dir"] / "phase5" / "slope_deg.tif"
    elev_mean = _zonal_raster_mean(dem, rgeom, crs)
    slope_mean = _zonal_raster_mean(slope, rgeom, crs)

    soil_name = _majority_attr(soils, "SOIL_LANDSCAPE" if "SOIL_LANDSCAPE" in soils.columns else soils.columns[0], rgeom, crs)
    # Prefer common soil name fields
    for cand in ("SOIL_LANDSCAPE", "soil_landscape", "NAME", "Landscape", "LANDSCAPE"):
        if cand in soils.columns:
            soil_name = _majority_attr(soils, cand, rgeom, crs)
            break

    geo_name = "unknown"
    for cand in (
        "Unit_Name",
        "UNITNAME",
        "unitname",
        "NAME",
        "RockUnit",
        "DESCRIP",
        "geology_unit",
        "Dominant_Lithology",
    ):
        if cand in geology.columns:
            geo_name = _majority_attr(geology, cand, rgeom, crs)
            break
    is_basalt = False
    if "is_basalt_or_volcanic" in geology.columns:
        ggeo = to_analysis_crs(geology, crs)
        try:
            ghit = gpd.clip(ggeo, rgeom)
        except Exception:
            ghit = ggeo[ggeo.intersects(rgeom)]
        if not ghit.empty:
            is_basalt = bool(ghit["is_basalt_or_volcanic"].astype(bool).any())
    # Robertson plateau basalt soils often sit above mapped sedimentary units in PTB
    # seamless geology — flag soil-name association separately (not rock-unit causation).
    soil_basalt_assoc = "robertson" in str(soil_name).lower()

    # Species within 1 km / 2 km (public clean layer — already sensitivity-filtered for points)
    spp_1k = _species_buffer_stats(species, rgeom, 1000, crs)
    spp_2k = _species_buffer_stats(species, rgeom, 2000, crs)

    # CEEC indicative
    ceec_raw = download_ceec_labels(settings, study_area, logger)
    ceec = to_analysis_crs(ceec_raw, crs) if not ceec_raw.empty else ceec_raw
    ceec_in_aoi_n = int(len(ceec)) if ceec is not None and not ceec.empty else 0
    ceec_intersects_reserve = False
    ceec_names_reserve: list[str] = []
    ceec_names_aoi: list[str] = []
    if ceec is not None and not ceec.empty:
        name_col = "CEEC_EPBC_" if "CEEC_EPBC_" in ceec.columns else ("CEEC_NSW_N" if "CEEC_NSW_N" in ceec.columns else None)
        if name_col:
            ceec_names_aoi = sorted({str(x) for x in ceec[name_col].dropna().unique() if str(x).strip()})
        try:
            chit = gpd.clip(ceec, rgeom)
        except Exception:
            chit = ceec[ceec.intersects(rgeom)]
        ceec_intersects_reserve = not chit.empty
        if name_col and not chit.empty:
            ceec_names_reserve = sorted({str(x) for x in chit[name_col].dropna().unique() if str(x).strip()})

    # Canopy / greenness proxy from living feed summary (AOI-class contrast, not reserve-only LiDAR)
    green_csv = paths["twin_lakes_dir"] / "greenness_summary.csv"
    canopy_proxy = {
        "method": "NDVI class contrast (Planetary Computer living feed) — NOT LiDAR canopy percent",
        "evidence_tag": "MODELLED",
        "ndvi_rainforest_remnant_aoi": None,
        "ndvi_cleared_aoi": None,
        "ndvi_delta": None,
        "reserve_canopy_percent": None,
        "note": (
            "Formal % canopy inside the reserve requires DEA Fractional Cover or LiDAR. "
            "Until enabled, report AOI remnant vs cleared NDVI contrast only."
        ),
    }
    if green_csv.is_file():
        gsum = pd.read_csv(green_csv)
        lookup = {str(r["class"]): float(r["mean_ndvi"]) for _, r in gsum.iterrows() if "class" in gsum.columns}
        canopy_proxy["ndvi_rainforest_remnant_aoi"] = lookup.get("rainforest_remnant")
        canopy_proxy["ndvi_cleared_aoi"] = lookup.get("cleared_non_native")
        canopy_proxy["ndvi_delta"] = lookup.get("delta_remnant_minus_cleared")

    # Surrounding land-use proxy until NSW Landuse download enabled
    landuse = {
        "source": "SVTM cleared_or_non_native contrast (proxy) — NSW Landuse not yet enabled",
        "evidence_tag": "CALCULATED",
        "within_1km": {
            "native_veg_ha": rings["native_veg_ha_within_1000m"],
            "rainforest_ha": rings["rainforest_ha_within_1000m"],
            "cleared_contrast_ha": rings["cleared_contrast_ha_within_1000m"],
        },
        "within_2km": {
            "native_veg_ha": rings["native_veg_ha_within_2000m"],
            "rainforest_ha": rings["rainforest_ha_within_2000m"],
            "cleared_contrast_ha": rings["cleared_contrast_ha_within_2000m"],
        },
    }

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    profile: dict[str, Any] = {
        "profile_version": PROFILE_VERSION,
        "generated_at_utc": generated_at,
        "project": settings.get("project", {}).get("name"),
        "guiding_question": settings.get("project", {}).get("question"),
        "crs_analysis": crs,
        "geometry_type": "Polygon",
        "reserve": {
            "name": str(reserve.iloc[0].get("reserve_name") or "Robertson Nature Reserve"),
            "reserve_no": str(reserve.iloc[0].get("reserve_no") or ""),
            "reserve_type": str(reserve.iloc[0].get("reserve_type") or ""),
            "iucn": str(reserve.iloc[0].get("iucn") or ""),
            "area_ha_calculated": round(area_ha, 3),
            "gaz_area_ha": gaz,
            "gis_area_ha_source": gis_src,
            "evidence_tag": "OBSERVED",
        },
        "threatened_ecological_community": {
            **TEC_PUBLISHED,
            "ceec_indicative_features_in_aoi": ceec_in_aoi_n,
            "ceec_indicative_intersects_reserve": ceec_intersects_reserve,
            "ceec_names_on_reserve": ceec_names_reserve,
            "ceec_names_in_aoi_sample": ceec_names_aoi[:20],
            "ceec_mapping_note": (
                "CEEC_NSW label polygons are indicative. Listing status above is from "
                "NSW Scientific Committee / EPBC published determinations."
            ),
        },
        "vegetation_in_reserve": {
            "majority_pct_name": pct_majority,
            "majority_veg_class": veg_class,
            "majority_veg_form": veg_form,
            "rainforest_ha_intersect": round(rf_in_reserve_ha, 3),
            "native_veg_ha_intersect": round(native_in_reserve_ha, 3),
            "pct_area_ha_list": [
                {
                    "pct_id": r.get("pct_id"),
                    "pct_name": r.get("pct_name"),
                    "area_ha": round(float(r.get("_a", 0)), 3),
                }
                for r in pct_list
            ],
            "evidence_tag": "CALCULATED",
            "source": "SVTM extant PCT clipped to reserve",
        },
        "landscape_rings": {**rings, "evidence_tag": "CALCULATED"},
        "water": {
            "distance_to_nearest_waterway_m": None if dist_water_m is None else round(dist_water_m, 1),
            "evidence_tag": "CALCULATED",
            "source": "NSW HydroLine",
        },
        "nearby_habitat": {
            "rainforest_patches_within_1km_excl_touching": n_rf_within_1km,
            "rainforest_patches_within_2km_excl_touching": n_rf_within_2km,
            "nearest_rainforest_patch_m": None if nearest_rf_m is None else round(nearest_rf_m, 1),
            "nearest_rainforest_patch_ha": None if nearest_rf_ha is None else round(nearest_rf_ha, 3),
            "nearest_core_habitat_patch_m": None if nearest_core_m is None else round(nearest_core_m, 1),
            "nearest_core_habitat_patch_ha": None if nearest_core_ha is None else round(nearest_core_ha, 3),
            "evidence_tag": "CALCULATED",
        },
        "terrain_soils_geology": {
            "elev_mean_m": None if elev_mean is None else round(elev_mean, 1),
            "slope_mean_deg": None if slope_mean is None else round(slope_mean, 1),
            "majority_soil_landscape": soil_name,
            "majority_geology_unit": geo_name,
            "intersects_basalt_or_volcanic_rock_unit": is_basalt,
            "soil_landscape_suggests_robertson_basalt": soil_basalt_assoc,
            "evidence_tag": "CALCULATED",
            "geology_note": (
                "PTB seamless geology may map sedimentary rock units under the plateau; "
                "Robertson soil landscape + published TEC text support basalt-soil association. "
                "Do not treat rock-unit flag alone as proof of Tertiary basalt outcrop."
            ),
        },
        "biodiversity_nearby": {
            "within_1km": spp_1k,
            "within_2km": spp_2k,
            "evidence_tag": "OBSERVED",
            "caveat": (
                "BioNet public observations; effort-biased; sensitive taxa denatured/aggregated. "
                "Absence of records is not absence of species."
            ),
        },
        "canopy_proxy": canopy_proxy,
        "surrounding_land_use": landuse,
        "limitations": [
            "No composite ecological importance score is calculated.",
            "SVTM is regional vegetation mapping — edges are not field-survey cadastre.",
            "CEEC polygons are indicative if present.",
            "Canopy percent inside reserve not yet available without DEA FC / LiDAR.",
            "NSW Landuse layer not enabled — cleared/native contrast used as proxy.",
            "Yarrawa Brush historic surveyed boundary is not fabricated.",
        ],
        "living_atlas": {
            "enabled": bool(settings.get("project", {}).get("living_atlas", True)),
            "refresh_this_profile_by": "python src/10_build_reserve_profile.py",
            "related_feeds": ["outputs/twin_lakes/story_package.json", "greenness_summary.csv"],
        },
        "cartographic_art": {
            "standard": "docs/CARTOGRAPHIC_ART_STANDARD.md",
            "chapter_use": "01 The Little Reserve — soft reserve pulse, moss remnant wash, quiet metric callouts",
        },
    }

    # Single-row metrics table for CSV / ArcGIS
    flat = {
        "reserve_name": profile["reserve"]["name"],
        "area_ha_calculated": profile["reserve"]["area_ha_calculated"],
        "gaz_area_ha": profile["reserve"]["gaz_area_ha"],
        "majority_pct_name": pct_majority,
        "majority_veg_class": veg_class,
        "majority_veg_form": veg_form,
        "rainforest_ha_in_reserve": round(rf_in_reserve_ha, 3),
        "native_veg_ha_in_reserve": round(native_in_reserve_ha, 3),
        "dist_nearest_waterway_m": profile["water"]["distance_to_nearest_waterway_m"],
        "native_veg_ha_500m": rings["native_veg_ha_within_500m"],
        "native_veg_ha_1km": rings["native_veg_ha_within_1000m"],
        "native_veg_ha_2km": rings["native_veg_ha_within_2000m"],
        "rainforest_ha_500m": rings["rainforest_ha_within_500m"],
        "rainforest_ha_1km": rings["rainforest_ha_within_1000m"],
        "rainforest_ha_2km": rings["rainforest_ha_within_2000m"],
        "rf_patches_1km": n_rf_within_1km,
        "rf_patches_2km": n_rf_within_2km,
        "nearest_rf_patch_m": profile["nearby_habitat"]["nearest_rainforest_patch_m"],
        "nearest_core_patch_m": profile["nearby_habitat"]["nearest_core_habitat_patch_m"],
        "elev_mean_m": profile["terrain_soils_geology"]["elev_mean_m"],
        "slope_mean_deg": profile["terrain_soils_geology"]["slope_mean_deg"],
        "soil_landscape": soil_name,
        "geology_unit": geo_name,
        "basalt_volcanic_rock_unit": is_basalt,
        "soil_robertson_basalt_assoc": soil_basalt_assoc,
        "spp_records_1km": spp_1k["n_records"],
        "spp_species_1km": spp_1k["n_species"],
        "threatened_species_1km": spp_1k["n_threatened_species"],
        "flora_species_1km": spp_1k["n_flora_species"],
        "ceec_intersects_reserve": ceec_intersects_reserve,
        "ceec_features_aoi": ceec_in_aoi_n,
        "nsw_tec_status_published": TEC_PUBLISHED["nsw_status"],
        "epbc_tec_status_published": TEC_PUBLISHED["epbc_status"],
        "profile_version": PROFILE_VERSION,
        "generated_at_utc": generated_at,
    }
    profile_gdf = reserve.copy()
    for k, v in flat.items():
        profile_gdf[k] = v

    return profile, profile_gdf, ceec if ceec is not None else gpd.GeoDataFrame(geometry=[], crs=crs)


def write_profile_markdown(profile: dict[str, Any], path: Path) -> None:
    r = profile["reserve"]
    v = profile["vegetation_in_reserve"]
    t = profile["threatened_ecological_community"]
    n = profile["nearby_habitat"]
    b1 = profile["biodiversity_nearby"]["within_1km"]
    rings = profile["landscape_rings"]
    terr = profile["terrain_soils_geology"]
    lines = [
        "# Robertson Nature Reserve — Ecological Profile",
        "",
        f"**Generated:** {profile['generated_at_utc']}  ",
        f"**Profile version:** {profile['profile_version']}  ",
        f"**Analysis CRS:** {profile['crs_analysis']} (metres)  ",
        f"**Geometry:** {profile['geometry_type']}",
        "",
        "> Transparent metrics only — no composite importance score.",
        "",
        "## Reserve identity",
        "",
        f"| Metric | Value | Evidence |",
        f"|--------|-------|----------|",
        f"| Name | {r['name']} | OBSERVED |",
        f"| Reserve number | {r['reserve_no']} | OBSERVED |",
        f"| Type / IUCN | {r['reserve_type']} / {r['iucn']} | OBSERVED |",
        f"| Area (calculated) | **{r['area_ha_calculated']} ha** | CALCULATED |",
        f"| Gazetted area | {r['gaz_area_ha']} ha | OBSERVED |",
        "",
        "## Threatened ecological community",
        "",
        f"| Item | Value | Evidence |",
        f"|------|-------|----------|",
        f"| Community | {t['tec_name']} | PUBLISHED |",
        f"| NSW status | {t['nsw_status']} | PUBLISHED |",
        f"| EPBC status | {t['epbc_status']} | PUBLISHED |",
        f"| Primary associated PCT | {t['associated_pct_primary']} | PUBLISHED |",
        f"| CEEC indicative intersects reserve | {t['ceec_indicative_intersects_reserve']} | OBSERVED/indicative |",
        f"| CEEC features in AOI | {t['ceec_indicative_features_in_aoi']} | OBSERVED/indicative |",
        "",
        f"NSW determination: {t['nsw_determination_url']}",
        "",
        "## Vegetation inside the reserve",
        "",
        f"- Majority PCT: **{v['majority_pct_name']}**",
        f"- Veg class / form: {v['majority_veg_class']} / {v['majority_veg_form']}",
        f"- Rainforest intersect: {v['rainforest_ha_intersect']} ha",
        f"- Native vegetation intersect: {v['native_veg_ha_intersect']} ha",
        "",
        "## Surrounding native vegetation",
        "",
        f"| Ring | Native veg (ha) | Rainforest (ha) | Cleared contrast (ha) |",
        f"|------|-----------------|-----------------|------------------------|",
        f"| 500 m | {rings['native_veg_ha_within_500m']} | {rings['rainforest_ha_within_500m']} | {rings['cleared_contrast_ha_within_500m']} |",
        f"| 1 km | {rings['native_veg_ha_within_1000m']} | {rings['rainforest_ha_within_1000m']} | {rings['cleared_contrast_ha_within_1000m']} |",
        f"| 2 km | {rings['native_veg_ha_within_2000m']} | {rings['rainforest_ha_within_2000m']} | {rings['cleared_contrast_ha_within_2000m']} |",
        "",
        "## Water, habitat neighbours, terrain",
        "",
        f"- Distance to nearest waterway: **{profile['water']['distance_to_nearest_waterway_m']} m**",
        f"- Rainforest patches within 1 km (excl. touching): **{n['rainforest_patches_within_1km_excl_touching']}**",
        f"- Nearest other rainforest patch: **{n['nearest_rainforest_patch_m']} m** ({n['nearest_rainforest_patch_ha']} ha)",
        f"- Nearest other core habitat patch: **{n['nearest_core_habitat_patch_m']} m** ({n['nearest_core_habitat_patch_ha']} ha)",
        f"- Mean elevation: {terr['elev_mean_m']} m; mean slope: {terr['slope_mean_deg']}°",
        f"- Soil landscape (majority): {terr['majority_soil_landscape']}",
        f"- Geology unit (majority): {terr['majority_geology_unit']}",
        f"- Basalt/volcanic rock-unit flag: {terr['intersects_basalt_or_volcanic_rock_unit']}",
        f"- Robertson basalt soil association: {terr['soil_landscape_suggests_robertson_basalt']}",
        f"- Note: {terr['geology_note']}",
        "",
        "## Biodiversity nearby (BioNet public)",
        "",
        f"| Buffer | Records | Species | Threatened spp. | Flora spp. |",
        f"|--------|---------|---------|-----------------|------------|",
        f"| 1 km | {b1['n_records']} | {b1['n_species']} | {b1['n_threatened_species']} | {b1['n_flora_species']} |",
        f"| 2 km | {profile['biodiversity_nearby']['within_2km']['n_records']} | {profile['biodiversity_nearby']['within_2km']['n_species']} | {profile['biodiversity_nearby']['within_2km']['n_threatened_species']} | {profile['biodiversity_nearby']['within_2km']['n_flora_species']} |",
        "",
        f"*Caveat:* {profile['biodiversity_nearby']['caveat']}",
        "",
        "## Canopy proxy",
        "",
        f"- Method: {profile['canopy_proxy']['method']}",
        f"- NDVI rainforest remnant (AOI): {profile['canopy_proxy']['ndvi_rainforest_remnant_aoi']}",
        f"- NDVI cleared (AOI): {profile['canopy_proxy']['ndvi_cleared_aoi']}",
        f"- Delta: {profile['canopy_proxy']['ndvi_delta']}",
        f"- Reserve % canopy: {profile['canopy_proxy']['reserve_canopy_percent']} (pending DEA FC/LiDAR)",
        "",
        "## Limitations",
        "",
    ]
    for lim in profile["limitations"]:
        lines.append(f"- {lim}")
    lines += [
        "",
        "## Cartographic use",
        "",
        "Present these metrics as quiet callouts on an artful reserve map — not as a dashboard scorecard.",
        "See `docs/CARTOGRAPHIC_ART_STANDARD.md`.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    settings = load_settings()
    paths = settings["resolved_paths"]
    logger = setup_logging(
        paths["logs_dir"],
        name="phase1_reserve_profile",
        level=str(settings.get("logging", {}).get("level", "INFO")),
    )
    ensure_dirs(
        paths["interim_dir"],
        paths["reports_dir"],
        paths["csv_dir"],
        paths["geojson_dir"],
        paths["raw_dir"] / "vegetation",
    )

    logger.info("=== Phase 1 revised: Reserve ecological profile ===")
    profile, profile_gdf, ceec = build_profile(settings, logger)

    # Exports
    json_path = paths["csv_dir"] / "reserve_ecological_profile.json"
    csv_path = paths["csv_dir"] / "reserve_ecological_profile.csv"
    md_path = paths["reports_dir"] / "reserve_ecological_profile.md"
    gpkg_path = paths["interim_dir"] / "phase1_reserve_profile.gpkg"

    json_path.write_text(json.dumps(profile, indent=2, default=str), encoding="utf-8")
    # Flat CSV from geometry row attrs
    flat_cols = [c for c in profile_gdf.columns if c != "geometry"]
    profile_gdf[flat_cols].to_csv(csv_path, index=False)
    write_profile_markdown(profile, md_path)

    write_gdf(profile_gdf, gpkg_path, layer="reserve_ecological_profile")
    if ceec is not None and not ceec.empty:
        write_gdf(ceec, gpkg_path, layer="ceec_indicative_aoi")
        # Also geojson for StoryMap art layer (simplified)
        try:
            ceec_out = ceec.copy()
            ceec_out["geometry"] = ceec_out.geometry.simplify(5)
            ceec_out.to_crs("EPSG:4326").to_file(
                paths["geojson_dir"] / "ceec_indicative_aoi.geojson",
                driver="GeoJSON",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("CEEC GeoJSON export failed: %s", exc)

    profile_gdf.to_crs("EPSG:4326").to_file(
        paths["geojson_dir"] / "reserve_ecological_profile.geojson",
        driver="GeoJSON",
    )

    qa_rows = basic_vector_qa(profile_gdf, "reserve_ecological_profile")
    if ceec is not None and not ceec.empty:
        qa_rows.extend(basic_vector_qa(ceec, "ceec_indicative_aoi"))
    qa_rows.append(
        {
            "layer": "reserve_ecological_profile",
            "check": "area_vs_gazetted_ha",
            "value": abs(float(profile["reserve"]["area_ha_calculated"]) - float(profile["reserve"]["gaz_area_ha"] or 0)),
            "status": "OK"
            if abs(float(profile["reserve"]["area_ha_calculated"]) - float(profile["reserve"]["gaz_area_ha"] or 0)) < 0.5
            else "WARN",
        }
    )
    append_qa_rows(qa_rows, paths["reports_dir"] / "data_quality_report.csv")

    # Append key layers into master GPKG without full Phase 7 rebuild
    master = paths["gpkg_dir"] / str(settings.get("outputs", {}).get("master_gpkg", "robertson_conservation.gpkg"))
    if master.is_file():
        write_gdf(profile_gdf, master, layer="reserve_ecological_profile")
        if ceec is not None and not ceec.empty:
            write_gdf(ceec, master, layer="ceec_indicative_aoi")
        processed = paths["processed_dir"] / master.name
        if processed.is_file():
            write_gdf(profile_gdf, processed, layer="reserve_ecological_profile")
            if ceec is not None and not ceec.empty:
                write_gdf(ceec, processed, layer="ceec_indicative_aoi")
        logger.info("Updated master GPKG with profile (+ CEEC if present)")

    logger.info("Wrote %s", md_path)
    logger.info("Wrote %s", json_path)
    logger.info("Wrote %s", csv_path)
    logger.info(
        "Profile complete: %.3f ha | PCT=%s | spp_1km=%s | ceec_aoi=%s",
        profile["reserve"]["area_ha_calculated"],
        profile["vegetation_in_reserve"]["majority_pct_name"],
        profile["biodiversity_nearby"]["within_1km"]["n_species"],
        profile["threatened_ecological_community"]["ceec_indicative_features_in_aoi"],
    )


if __name__ == "__main__":
    main()
