"""
PYTHON DATA PREP — DEM clip, soils, geology, fire context; optional DEA later.

Slope/aspect derived in Python for prep; ArcGIS can refine cartography.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.ops import unary_union

ASSOCIATION_NOTE = (
    "Landscape context (terrain/soils/geology/fire). Association / potential "
    "function only — not reserve causation or reserve-driven climate change."
)


def tag_association(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    out = gdf.copy()
    out["interpretation"] = ASSOCIATION_NOTE
    return out


def clip_polygons(
    gdf: gpd.GeoDataFrame,
    study_area: gpd.GeoDataFrame,
    *,
    crs_analysis: str,
) -> gpd.GeoDataFrame:
    if gdf.empty:
        return gdf.to_crs(crs_analysis) if gdf.crs else gdf
    left = gdf.to_crs(crs_analysis)
    sa = study_area.to_crs(crs_analysis)
    try:
        out = gpd.clip(left, sa)
    except Exception:
        union = unary_union(list(sa.geometry))
        out = left.loc[left.intersects(union)].copy()
    if out.empty:
        return out
    out = tag_association(out)
    out["area_ha"] = out.geometry.area / 10000.0
    return out.reset_index(drop=True)


def flag_basalt_units(geology: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Flag units mentioning basalt/volcanic for rainforest association narrative."""
    if geology.empty:
        return geology
    out = geology.copy()
    text_cols = [
        c
        for c in [
            "Unit_Name",
            "Dominant_Lithology",
            "Description",
            "Group_Suite",
            "Formation_Pluton",
        ]
        if c in out.columns
    ]
    if not text_cols:
        out["is_basalt_or_volcanic"] = False
        return out
    blob = out[text_cols].fillna("").astype(str).agg(" ".join, axis=1)
    out["is_basalt_or_volcanic"] = blob.str.contains(
        r"basalt|volcanic|latite|dolerite|trachyte|igneous",
        case=False,
        na=False,
        regex=True,
    )
    return out


def copernicus_tile_names(bounds_wgs84: tuple[float, float, float, float]) -> list[tuple[str, str]]:
    """Return Copernicus GLO-30 tile (lat, lon) name parts covering a WGS84 envelope."""
    minx, miny, maxx, maxy = bounds_wgs84
    # Tile S35 covers -35..-34; E150 covers 150..151
    lat_starts = range(math.floor(miny), math.ceil(maxy))
    lon_starts = range(math.floor(minx), math.ceil(maxx))
    tiles = []
    for lat0 in lat_starts:
        for lon0 in lon_starts:
            # Copernicus south tiles use absolute south index = ceil(|lat|) for negative?
            # Tile S35_00 covers latitudes [-35, -34).
            if lat0 < 0:
                lat_name = f"S{abs(lat0):02d}_00"
            else:
                lat_name = f"N{lat0:02d}_00"
            if lon0 < 0:
                lon_name = f"W{abs(lon0):03d}_00"
            else:
                lon_name = f"E{lon0:03d}_00"
            tiles.append((lat_name, lon_name))
    return tiles


def download_copernicus_dem(
    study_area_wgs84: gpd.GeoDataFrame,
    *,
    url_template: str,
    out_path: Path,
    logger: Any | None = None,
) -> Path:
    """Download Copernicus GLO-30 COG tile(s) covering the AOI (cached)."""
    import rasterio
    from rasterio.merge import merge
    from rasterio.io import MemoryFile

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.is_file() and out_path.stat().st_size > 0:
        if logger:
            logger.info("DEM cache hit: %s", out_path)
        return out_path

    bounds = tuple(map(float, study_area_wgs84.total_bounds))
    tiles = copernicus_tile_names(bounds)
    if logger:
        logger.info("Copernicus DEM tiles: %s", tiles)

    datasets = []
    memfiles = []
    try:
        for lat_name, lon_name in tiles:
            url = url_template.format(lat=lat_name, lon=lon_name)
            if logger:
                logger.info("Downloading DEM %s", url)
            req = Request(url, headers={"User-Agent": "robertson-ripple-effect/0.1 (portfolio GIS)"})
            with urlopen(req, timeout=300) as resp:
                data = resp.read()
            mem = MemoryFile(data)
            memfiles.append(mem)
            datasets.append(mem.open())
        if len(datasets) == 1:
            arr = datasets[0].read()
            meta = datasets[0].meta.copy()
        else:
            arr, transform = merge(datasets)
            meta = datasets[0].meta.copy()
            meta.update({"height": arr.shape[1], "width": arr.shape[2], "transform": transform})
        meta.update({"driver": "GTiff", "compress": "lzw"})
        with rasterio.open(out_path, "w", **meta) as dst:
            dst.write(arr)
    finally:
        for ds in datasets:
            ds.close()
        for mem in memfiles:
            mem.close()

    if logger:
        logger.info("Wrote DEM mosaic %s", out_path)
    return out_path


def clip_dem_and_derivatives(
    dem_path: Path,
    study_area: gpd.GeoDataFrame,
    *,
    crs_analysis: str,
    out_dir: Path,
    logger: Any | None = None,
) -> dict[str, Path]:
    """Clip DEM to study area; write elevation / slope_deg / aspect_deg GeoTIFFs."""
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.mask import mask
    from rasterio.warp import calculate_default_transform, reproject

    out_dir.mkdir(parents=True, exist_ok=True)
    elev_path = out_dir / "dem_clip.tif"
    slope_path = out_dir / "slope_deg.tif"
    aspect_path = out_dir / "aspect_deg.tif"

    sa = study_area.to_crs(crs_analysis)
    geoms = [g.__geo_interface__ for g in sa.geometry]

    with rasterio.open(dem_path) as src:
        sa_dem = study_area.to_crs(src.crs)
        geoms_dem = [g.__geo_interface__ for g in sa_dem.geometry]
        out_img, out_transform = mask(src, geoms_dem, crop=True, filled=True)
        out_meta = src.meta.copy()
        out_meta.update(
            {
                "height": out_img.shape[1],
                "width": out_img.shape[2],
                "transform": out_transform,
                "compress": "lzw",
            }
        )

    tmp = out_dir / "_dem_src_clip.tif"
    with rasterio.open(tmp, "w", **out_meta) as dst:
        dst.write(out_img)

    with rasterio.open(tmp) as src:
        transform, width, height = calculate_default_transform(
            src.crs, crs_analysis, src.width, src.height, *src.bounds
        )
        kwargs = src.meta.copy()
        kwargs.update(
            {
                "crs": crs_analysis,
                "transform": transform,
                "width": width,
                "height": height,
                "compress": "lzw",
                "dtype": "float32",
                "nodata": -9999,
            }
        )
        with rasterio.open(elev_path, "w", **kwargs) as dst:
            dest = np.empty((height, width), dtype="float32")
            reproject(
                source=rasterio.band(src, 1),
                destination=dest,
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=transform,
                dst_crs=crs_analysis,
                resampling=Resampling.bilinear,
                dst_nodata=-9999,
            )
            dst.write(dest, 1)
    try:
        tmp.unlink()
    except OSError:
        pass

    # Mask to study polygon in analysis CRS, then derive slope/aspect
    with rasterio.open(elev_path) as src:
        elev_masked, transform = mask(src, geoms, crop=True, nodata=-9999)
        meta = src.meta.copy()
        meta.update(
            {
                "height": elev_masked.shape[1],
                "width": elev_masked.shape[2],
                "transform": transform,
                "dtype": "float32",
                "nodata": -9999,
                "compress": "lzw",
            }
        )

    elev = elev_masked[0].astype("float64")
    elev = np.where(elev == -9999, np.nan, elev)
    elev = np.where(elev < -100, np.nan, elev)
    res_x = abs(transform.a)
    res_y = abs(transform.e)
    dy, dx = np.gradient(elev, res_y, res_x)
    slope = np.degrees(np.arctan(np.sqrt(dx * dx + dy * dy)))
    aspect = np.degrees(np.arctan2(-dx, dy))
    aspect = np.where(aspect < 0, aspect + 360.0, aspect)
    aspect = np.where(slope < 0.5, np.nan, aspect)

    elev_out = np.where(np.isnan(elev), -9999, elev).astype("float32")
    with rasterio.open(elev_path, "w", **meta) as dst:
        dst.write(elev_out, 1)
    for path, arr in ((slope_path, slope), (aspect_path, aspect)):
        data = np.where(np.isnan(arr), -9999, arr).astype("float32")
        with rasterio.open(path, "w", **meta) as dst:
            dst.write(data, 1)

    if logger:
        logger.info("Wrote DEM derivatives under %s", out_dir)
    return {"dem": elev_path, "slope": slope_path, "aspect": aspect_path}


def sample_raster_at_points(
    raster_path: Path,
    points: gpd.GeoDataFrame,
    *,
    value_name: str,
) -> pd.Series:
    import rasterio

    pts = points.to_crs(open_crs(raster_path))
    coords = [(g.x, g.y) for g in pts.geometry]
    with rasterio.open(raster_path) as src:
        vals = np.array([v[0] for v in src.sample(coords)], dtype="float64")
        nodata = src.nodata
    if nodata is not None:
        vals = np.where(vals == nodata, np.nan, vals)
    vals = np.where(vals < -100, np.nan, vals)
    return pd.Series(vals, index=points.index, name=value_name)


def open_crs(raster_path: Path):
    import rasterio

    with rasterio.open(raster_path) as src:
        return src.crs


def dominant_polygon_attribute(
    grid: gpd.GeoDataFrame,
    polygons: gpd.GeoDataFrame,
    *,
    attr: str,
    out_col: str,
    crs_analysis: str,
) -> gpd.GeoDataFrame:
    """Assign dominant intersecting polygon attribute to each grid cell (by overlap area)."""
    out = grid.to_crs(crs_analysis).copy()
    if polygons.empty or attr not in polygons.columns:
        out[out_col] = pd.NA
        return out
    poly = polygons.to_crs(crs_analysis)[["geometry", attr]].copy()
    poly = poly.rename(columns={attr: out_col})
    inter = gpd.overlay(
        out[["cell_id", "geometry"]].copy(),
        poly,
        how="intersection",
        keep_geom_type=False,
    )
    if inter.empty:
        out[out_col] = pd.NA
        return out
    inter["_a"] = inter.geometry.area
    top = (
        inter.sort_values("_a", ascending=False)
        .drop_duplicates("cell_id", keep="first")[["cell_id", out_col]]
    )
    out = out.drop(columns=[out_col], errors="ignore").merge(top, on="cell_id", how="left")
    return out


def landscape_summaries(
    soils: gpd.GeoDataFrame,
    geology: gpd.GeoDataFrame,
    fire: gpd.GeoDataFrame,
) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    if not soils.empty and "NAME" in soils.columns:
        out["soils"] = (
            soils.assign(area_ha=soils.geometry.area / 10000.0)
            .groupby("NAME", dropna=False)["area_ha"]
            .sum()
            .sort_values(ascending=False)
            .reset_index()
        )
    if not geology.empty:
        key = "Unit_Name" if "Unit_Name" in geology.columns else geology.columns[0]
        out["geology"] = (
            geology.assign(area_ha=geology.geometry.area / 10000.0)
            .groupby(key, dropna=False)["area_ha"]
            .sum()
            .sort_values(ascending=False)
            .reset_index()
        )
        if "is_basalt_or_volcanic" in geology.columns:
            out["geology_basalt_flag"] = pd.DataFrame(
                [
                    {
                        "basalt_volcanic_area_ha": round(
                            float(geology.loc[geology["is_basalt_or_volcanic"], "area_ha"].sum()),
                            2,
                        ),
                        "other_area_ha": round(
                            float(geology.loc[~geology["is_basalt_or_volcanic"], "area_ha"].sum()),
                            2,
                        ),
                    }
                ]
            )
    if not fire.empty:
        cat = "d_category" if "d_category" in fire.columns else "category"
        out["fire"] = (
            fire.assign(area_ha=fire.geometry.area / 10000.0)
            .groupby(cat, dropna=False)["area_ha"]
            .sum()
            .sort_values(ascending=False)
            .reset_index()
        )
    return out


def main() -> None:
    raise SystemExit("Run src/05_prepare_ripple.py for Phase 5.")


if __name__ == "__main__":
    main()
