"""
PYTHON DATA PREP — controlled downloads from official ArcGIS REST services.

Phase 1 sources:
  - NSW NPWS Estate (DCCEEW EDP/Estate) — reserve-first, then AOI envelope
  - NSW LGA boundaries (Spatial Services / SIX)
  - NSW road segments (Spatial Services Transport Theme), clipped to AOI
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import geopandas as gpd
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(__file__).resolve().parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from config import load_settings  # noqa: E402
from utils import arcgis_query_geojson, ensure_dirs, setup_logging, write_gdf  # noqa: E402


def download_reserve(
    settings: dict,
    logger: logging.Logger,
) -> Path:
    """Download Robertson Nature Reserve feature only."""
    paths = settings["resolved_paths"]
    out = paths["raw_dir"] / "npws" / "robertson_nature_reserve_raw.gpkg"
    ensure_dirs(out.parent)
    if out.is_file() and out.stat().st_size > 0:
        logger.info("Reserve cache hit: %s", out)
        return out
    url = settings["downloads"]["npws_estate_query"]
    name = str(settings["study_area"]["primary_reserve_name"]).replace("'", "''")
    gdf = arcgis_query_geojson(
        url,
        where=f"NAME = '{name}'",
        logger=logger,
    )
    if gdf.empty:
        raise RuntimeError(f"Reserve not found via REST: {name}")
    write_gdf(gdf, out, layer="robertson_nature_reserve")
    logger.info("Saved reserve: %s features -> %s", len(gdf), out)
    return out


def download_npws_estate_for_aoi(
    settings: dict,
    aoi_wgs84: gpd.GeoDataFrame,
    logger: logging.Logger,
) -> Path:
    """Download NPWS Estate features intersecting the AOI envelope."""
    paths = settings["resolved_paths"]
    out = paths["raw_dir"] / "npws" / "npws_estate_aoi_raw.gpkg"
    ensure_dirs(out.parent)
    url = settings["downloads"]["npws_estate_query"]
    geom = unary_union(list(aoi_wgs84.geometry))
    gdf = arcgis_query_geojson(
        url,
        where="1=1",
        geometry=geom,
        in_sr=4326,
        out_sr=4326,
        logger=logger,
    )
    if gdf.empty:
        raise RuntimeError("NPWS Estate AOI query returned zero features")
    write_gdf(gdf, out, layer="npws_estate")
    logger.info("Saved NPWS Estate in AOI: %s features -> %s", len(gdf), out)
    return out


def download_lga_for_aoi(
    settings: dict,
    aoi_wgs84: gpd.GeoDataFrame,
    logger: logging.Logger,
) -> Path:
    """Download LGAs intersecting the AOI."""
    paths = settings["resolved_paths"]
    out = paths["raw_dir"] / "admin" / "lga_aoi_raw.gpkg"
    ensure_dirs(out.parent)
    url = settings["downloads"]["lga_query"]
    geom = unary_union(list(aoi_wgs84.geometry))
    gdf = arcgis_query_geojson(
        url,
        where="1=1",
        geometry=geom,
        in_sr=4326,
        out_sr=4326,
        logger=logger,
    )
    if gdf.empty:
        raise RuntimeError("LGA query returned zero features for AOI")
    write_gdf(gdf, out, layer="lga")
    logger.info("Saved LGAs intersecting AOI: %s -> %s", len(gdf), out)
    return out


def download_roads_for_aoi(
    settings: dict,
    aoi_wgs84: gpd.GeoDataFrame,
    logger: logging.Logger,
) -> Path:
    """
    Download road segments intersecting the AOI.

    Prefers NSW Transport Theme REST. If that service errors (common outage),
    falls back to OpenStreetMap Overpass extract labelled as community data.
    """
    paths = settings["resolved_paths"]
    out = paths["raw_dir"] / "transport" / "roads_aoi_raw.gpkg"
    ensure_dirs(out.parent)
    geom = unary_union(list(aoi_wgs84.geometry))
    url = settings["downloads"]["roads_query"]
    gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    source = "nsw_transport_theme"
    try:
        gdf = arcgis_query_geojson(
            url,
            where="1=1",
            geometry=geom,
            in_sr=4326,
            out_sr=4326,
            page_size=1000,
            logger=logger,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("NSW Transport REST failed (%s). Falling back to OSM Overpass.", exc)
        gdf = _download_roads_overpass(geom, logger)
        source = "openstreetmap_overpass"
    if gdf.empty:
        logger.warning("Road download returned zero features — continuing without roads")
    else:
        gdf = gdf.copy()
        gdf["source"] = source
    write_gdf(gdf, out, layer="roads")
    logger.info("Saved roads intersecting AOI: %s (%s) -> %s", len(gdf), source, out)
    return out


def _download_roads_overpass(aoi_geom, logger: logging.Logger) -> gpd.GeoDataFrame:
    """Temporary roads fallback via Overpass API (ODbL)."""
    import json
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen

    minx, miny, maxx, maxy = aoi_geom.bounds
    # Overpass bbox: south,west,north,east
    query = f"""
    [out:json][timeout:180];
    (
      way["highway"~"^(motorway|trunk|primary|secondary|tertiary|unclassified|residential|service|track)$"]({miny},{minx},{maxy},{maxx});
    );
    out geom;
    """
    endpoint = "https://overpass-api.de/api/interpreter"
    req = Request(
        endpoint,
        data=query.encode("utf-8"),
        headers={"User-Agent": "robertson-ripple-effect/0.1 (portfolio GIS)"},
        method="POST",
    )
    logger.info("Overpass roads query bbox=(%.4f,%.4f,%.4f,%.4f)", minx, miny, maxx, maxy)
    with urlopen(req, timeout=240) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    from shapely.geometry import LineString

    rows = []
    for el in payload.get("elements", []):
        if el.get("type") != "way" or "geometry" not in el:
            continue
        coords = [(pt["lon"], pt["lat"]) for pt in el["geometry"]]
        if len(coords) < 2:
            continue
        tags = el.get("tags") or {}
        rows.append(
            {
                "osm_id": el.get("id"),
                "highway": tags.get("highway"),
                "name": tags.get("name"),
                "ref": tags.get("ref"),
                "geometry": LineString(coords),
            }
        )
    if not rows:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    gdf = gpd.GeoDataFrame(rows, crs="EPSG:4326")
    logger.info("Overpass returned %s highway ways", len(gdf))
    return gdf


def download_bionet_sightings(
    settings: dict,
    aoi_wgs84: gpd.GeoDataFrame,
    logger: logging.Logger,
    *,
    force: bool = False,
) -> Path:
    """
    Page BioNet SpeciesSightings_CoreData for the AOI envelope (public view).
    Caches raw records as parquet under data/raw/species/.
    Set force=True to ignore cache (weekly / living-feed refresh).
    """
    import json
    import time
    from urllib.error import HTTPError, URLError
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen

    import pandas as pd

    from clean_species_data import BIONET_SELECT

    paths = settings["resolved_paths"]
    sp = settings.get("species", {})
    dl = settings["downloads"]
    out = paths["raw_dir"] / "species" / "bionet_sightings_aoi.parquet"
    ensure_dirs(out.parent)
    if not force and out.is_file() and out.stat().st_size > 0:
        logger.info("BioNet cache hit: %s", out)
        return out
    if force and out.is_file():
        logger.info("BioNet force refresh — replacing %s", out)

    minx, miny, maxx, maxy = map(float, aoi_wgs84.total_bounds)
    filt = (
        f"decimalLatitude ge {miny} and decimalLatitude le {maxy} "
        f"and decimalLongitude ge {minx} and decimalLongitude le {maxx}"
    )
    base = str(dl["bionet_odata_base"]).rstrip("/")
    entity = str(dl.get("bionet_entity", "SpeciesSightings_CoreData"))
    page_size = int(sp.get("bionet_page_size", 1000))
    select = ",".join(BIONET_SELECT)

    records: list[dict] = []
    skip = 0
    while True:
        params = {
            "$filter": filt,
            "$top": str(page_size),
            "$skip": str(skip),
            # Note: $orderby is rejected by this BioNet endpoint (HTTP 400).
            "$select": select,
        }
        url = f"{base}/{entity}?{urlencode(params)}"
        payload = None
        for attempt in range(5):
            try:
                req = Request(
                    url,
                    headers={
                        "User-Agent": "robertson-ripple-effect/0.1 (portfolio GIS)",
                        "Accept": "application/json",
                    },
                )
                with urlopen(req, timeout=180) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                break
            except (HTTPError, URLError, TimeoutError) as exc:
                if attempt == 4:
                    raise
                wait = 2**attempt
                logger.warning("BioNet retry in %ss after error: %s", wait, exc)
                time.sleep(wait)
        assert payload is not None
        batch = payload.get("value") or []
        records.extend(batch)
        logger.info("BioNet offset=%s +%s (total %s)", skip, len(batch), len(records))
        if len(batch) < page_size:
            break
        skip += page_size

    pd.DataFrame(records).to_parquet(out, index=False)
    logger.info("Saved BioNet sightings: %s -> %s", len(records), out)
    return out


def download_ala_occurrences(
    settings: dict,
    aoi_wgs84: gpd.GeoDataFrame,
    logger: logging.Logger,
) -> Path | None:
    """
    Optional ALA biocache occurrence pull for the AOI envelope.
    Returns None when ala_enabled is false.
    """
    import json
    import time
    from urllib.error import HTTPError, URLError
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen

    import pandas as pd

    if not bool(settings.get("downloads", {}).get("ala_enabled", False)):
        logger.info("ALA disabled in settings (downloads.ala_enabled=false)")
        return None

    paths = settings["resolved_paths"]
    sp = settings.get("species", {})
    out = paths["raw_dir"] / "species" / "ala_occurrences_aoi.parquet"
    ensure_dirs(out.parent)
    if out.is_file() and out.stat().st_size > 0:
        logger.info("ALA cache hit: %s", out)
        return out

    minx, miny, maxx, maxy = map(float, aoi_wgs84.total_bounds)
    page_size = int(sp.get("ala_page_size", 500))
    endpoint = str(settings["downloads"]["ala_occurrences_search"])
    # Envelope filter + NSW
    fqs = [
        "state:\"New South Wales\"",
        f"longitude:[{minx} TO {maxx}]",
        f"latitude:[{miny} TO {maxy}]",
    ]
    records: list[dict] = []
    start = 0
    total = None
    while True:
        params = {
            "q": "*:*",
            "fq": fqs,
            "start": str(start),
            "pageSize": str(page_size),
            "fl": ",".join(
                [
                    "id",
                    "uuid",
                    "occurrenceID",
                    "scientificName",
                    "raw_scientificName",
                    "vernacularName",
                    "decimalLatitude",
                    "decimalLongitude",
                    "eventDate",
                    "kingdom",
                    "classs",
                    "family",
                    "order",
                    "genus",
                    "taxonRank",
                    "stateConservation",
                    "countryConservation",
                    "sensitive",
                    "coordinateUncertaintyInMeters",
                    "dataGeneralizations",
                    "informationWithheld",
                    "occurrenceStatus",
                    "basisOfRecord",
                    "establishmentMeans",
                    "raw_catalogNumber",
                    "catalogNumber",
                ]
            ),
        }
        # urlencode doesn't handle list fq well — build manually
        q = urlencode({"q": "*:*", "start": start, "pageSize": page_size, "fl": params["fl"]})
        for fq in fqs:
            q += "&" + urlencode({"fq": fq})
        url = f"{endpoint}?{q}"
        payload = None
        for attempt in range(5):
            try:
                req = Request(
                    url,
                    headers={
                        "User-Agent": "robertson-ripple-effect/0.1 (portfolio GIS)",
                        "Accept": "application/json",
                    },
                )
                with urlopen(req, timeout=180) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                break
            except (HTTPError, URLError, TimeoutError) as exc:
                if attempt == 4:
                    raise
                wait = 2**attempt
                logger.warning("ALA retry in %ss after error: %s", wait, exc)
                time.sleep(wait)
        assert payload is not None
        if total is None:
            total = int(payload.get("totalRecords") or 0)
            logger.info("ALA totalRecords in envelope: %s", total)
        batch = payload.get("occurrences") or []
        records.extend(batch)
        logger.info("ALA start=%s +%s (total %s / %s)", start, len(batch), len(records), total)
        if not batch or len(records) >= total:
            break
        start += page_size

    pd.DataFrame(records).to_parquet(out, index=False)
    logger.info("Saved ALA occurrences: %s -> %s", len(records), out)
    return out


def main() -> None:
    settings = load_settings()
    logger = setup_logging(
        settings["resolved_paths"]["logs_dir"],
        name="download_data",
        level=str(settings.get("logging", {}).get("level", "INFO")),
    )
    download_reserve(settings, logger)
    logger.info("Reserve download complete. Run 01_build_foundation.py next.")


if __name__ == "__main__":
    main()
