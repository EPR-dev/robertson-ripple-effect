"""
Shared helpers: logging, downloads, ArcGIS REST paging, CRS, GeoPackage IO.
"""

from __future__ import annotations

import json
import logging
import time
import zipfile
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import geopandas as gpd
import pandas as pd
from shapely.geometry import mapping, shape


def setup_logging(log_dir: Path, name: str = "ripple_effect", level: str = "INFO") -> logging.Logger:
    """Configure file + console logging."""
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    logger.handlers.clear()
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s — %(message)s")
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    logger.addHandler(stream)
    file_handler = logging.FileHandler(log_dir / f"{name}.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.propagate = False
    return logger


def ensure_dirs(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def download_file(url: str, dest: Path, *, logger: logging.Logger | None = None, timeout: int = 180) -> Path:
    """Download a URL to dest if missing or empty."""
    ensure_dirs(dest.parent)
    if dest.is_file() and dest.stat().st_size > 0:
        if logger:
            logger.info("Using cached download: %s", dest)
        return dest
    if logger:
        logger.info("Downloading %s", url)
    req = Request(url, headers={"User-Agent": "robertson-ripple-effect/0.1 (portfolio GIS)"})
    with urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    dest.write_bytes(data)
    if logger:
        logger.info("Wrote %s (%.1f KB)", dest, dest.stat().st_size / 1024)
    return dest


def unzip_archive(zip_path: Path, out_dir: Path, *, logger: logging.Logger | None = None) -> Path:
    ensure_dirs(out_dir)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(out_dir)
    if logger:
        logger.info("Extracted %s -> %s", zip_path.name, out_dir)
    return out_dir


def find_shapefile(root: Path) -> Path:
    matches = sorted(root.rglob("*.shp"))
    if not matches:
        raise FileNotFoundError(f"No shapefile under {root}")
    return matches[0]


def http_json(url: str, *, timeout: int = 120) -> dict[str, Any]:
    req = Request(url, headers={"User-Agent": "robertson-ripple-effect/0.1 (portfolio GIS)"})
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def arcgis_query_geojson(
    query_url: str,
    *,
    where: str = "1=1",
    out_fields: str = "*",
    geometry: Any | None = None,
    geometry_type: str = "esriGeometryEnvelope",
    in_sr: int | None = None,
    out_sr: int = 4326,
    spatial_rel: str = "esriSpatialRelIntersects",
    page_size: int = 500,
    logger: logging.Logger | None = None,
    use_envelope: bool = True,
) -> gpd.GeoDataFrame:
    """
    Page through an ArcGIS MapServer/FeatureServer query endpoint and return a GeoDataFrame.
    Prefer envelope filters (more stable than full statewide pulls on some NSW services).
    """
    features: list[dict[str, Any]] = []
    offset = 0
    while True:
        params: dict[str, Any] = {
            "where": where,
            "outFields": out_fields,
            "returnGeometry": "true",
            "outSR": str(out_sr),
            "f": "geojson",
            "resultOffset": str(offset),
            "resultRecordCount": str(page_size),
        }
        if geometry is not None:
            if use_envelope:
                minx, miny, maxx, maxy = geometry.bounds
                params["geometry"] = json.dumps(
                    {"xmin": minx, "ymin": miny, "xmax": maxx, "ymax": maxy, "spatialReference": {"wkid": in_sr or out_sr}}
                )
                params["geometryType"] = "esriGeometryEnvelope"
            else:
                params["geometry"] = json.dumps(_shapely_to_esri_polygon(geometry, wkid=in_sr or out_sr))
                params["geometryType"] = geometry_type
            params["spatialRel"] = spatial_rel
            if in_sr is not None:
                params["inSR"] = str(in_sr)
        url = f"{query_url}?{urlencode(params)}"
        payload: dict[str, Any] | None = None
        for attempt in range(5):
            try:
                payload = http_json(url, timeout=180)
                # Some services return 200 with error object
                if isinstance(payload, dict) and payload.get("error"):
                    raise URLError(str(payload["error"]))
                break
            except (HTTPError, URLError, TimeoutError, TimeoutError) as exc:
                if attempt == 4:
                    raise
                wait = 2 ** attempt
                if logger:
                    logger.warning("REST retry in %ss after error: %s", wait, exc)
                time.sleep(wait)
        assert payload is not None
        batch = payload.get("features") or []
        features.extend(batch)
        if logger:
            logger.info(
                "REST %s offset=%s +%s (total %s)",
                query_url.split("/services/")[-1],
                offset,
                len(batch),
                len(features),
            )
        exceeded = bool(payload.get("exceededTransferLimit"))
        if len(batch) < page_size and not exceeded:
            break
        if not batch:
            break
        offset += page_size
    if not features:
        return gpd.GeoDataFrame(geometry=[], crs=f"EPSG:{out_sr}")
    fc = {"type": "FeatureCollection", "features": features}
    return gpd.GeoDataFrame.from_features(fc, crs=f"EPSG:{out_sr}")


def _shapely_to_esri_polygon(geom: Any, wkid: int = 4326) -> dict[str, Any]:
    """Convert shapely polygon/multipolygon to Esri JSON polygon rings."""
    if geom.geom_type == "Polygon":
        polys = [geom]
    elif geom.geom_type == "MultiPolygon":
        polys = list(geom.geoms)
    else:
        polys = [geom.convex_hull]
    rings: list[list[list[float]]] = []
    for poly in polys:
        exterior = [[float(x), float(y)] for x, y in poly.exterior.coords]
        rings.append(exterior)
        for interior in poly.interiors:
            rings.append([[float(x), float(y)] for x, y in interior.coords])
    return {"rings": rings, "spatialReference": {"wkid": int(wkid)}}


def to_analysis_crs(gdf: gpd.GeoDataFrame, crs: str) -> gpd.GeoDataFrame:
    if gdf.empty:
        return gdf.set_crs(crs, allow_override=True) if gdf.crs is None else gdf.to_crs(crs)
    if gdf.crs is None:
        raise ValueError("GeoDataFrame has no CRS")
    if str(gdf.crs) == crs or gdf.crs == crs:
        return gdf.copy()
    return gdf.to_crs(crs)


def write_gdf(gdf: gpd.GeoDataFrame, path: Path, layer: str | None = None) -> None:
    ensure_dirs(path.parent)
    if path.suffix.lower() == ".gpkg":
        gdf.to_file(path, layer=layer or path.stem, driver="GPKG")
    else:
        gdf.to_file(path)


def append_qa_rows(rows: list[dict[str, Any]], path: Path) -> pd.DataFrame:
    ensure_dirs(path.parent)
    frame = pd.DataFrame(rows)
    if path.is_file():
        prev = pd.read_csv(path)
        frame = pd.concat([prev, frame], ignore_index=True)
    frame.to_csv(path, index=False)
    return frame


def basic_vector_qa(gdf: gpd.GeoDataFrame, layer_name: str) -> list[dict[str, Any]]:
    """Return validation rows for a vector layer."""
    rows: list[dict[str, Any]] = []
    n = len(gdf)
    rows.append({"layer": layer_name, "check": "feature_count", "value": n, "status": "OK" if n else "WARN"})
    if gdf.empty:
        return rows
    rows.append(
        {
            "layer": layer_name,
            "check": "crs",
            "value": str(gdf.crs),
            "status": "OK" if gdf.crs is not None else "FAIL",
        }
    )
    null_geom = int(gdf.geometry.isna().sum())
    rows.append(
        {
            "layer": layer_name,
            "check": "null_geometry",
            "value": null_geom,
            "status": "OK" if null_geom == 0 else "FAIL",
        }
    )
    try:
        invalid = int((~gdf.geometry.is_valid).sum())
    except Exception:
        invalid = -1
    rows.append(
        {
            "layer": layer_name,
            "check": "invalid_geometry",
            "value": invalid,
            "status": "OK" if invalid == 0 else "WARN",
        }
    )
    return rows
