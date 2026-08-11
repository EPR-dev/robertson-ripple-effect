"""
Render art-forward StoryMap chapter plates for Bring Back the Brush.

Hybrid path: story chapters show these plates; Folium stays as craft map.

Usage:
  python src/09_render_story_plates.py
  python src/09_render_story_plates.py --chapter "This little patch"
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.transform import from_bounds
from rasterio.warp import reproject, transform_bounds
from shapely.geometry import Point, box, mapping
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(__file__).resolve().parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from config import load_settings  # noqa: E402
from utils import ensure_dirs, setup_logging  # noqa: E402

CRS_M = "EPSG:7856"
MASTER = ROOT / "outputs" / "geopackage" / "robertson_conservation.gpkg"
LIVING = ROOT / "outputs" / "twin_lakes" / "living_layers.gpkg"
DEM = ROOT / "outputs" / "raster" / "phase5" / "dem_clip.tif"
OUT_DIR = ROOT / "dashboard" / "assets" / "plates"

# Large StoryMap media plates (display fills the page column)
W, H = 2000, 1250

RECIPES = {
    "This little patch": {
        "slug": "01_this_little_patch",
        "fit": "close",
        "sentence": "At first glance — just a tiny patch of green beside a village.",
        "paint": "small_patch",
    },
    "The forest that was": {
        "slug": "02_the_forest_that_was",
        "fit": "aoi",
        "sentence": "THEN: a wider rainforest memory. NOW: a fragmented remnant.",
        "paint": "remains",
    },
    "What survived": {
        "slug": "03_what_survived",
        "fit": "aoi",
        "sentence": "Surviving fragments become a habitat system — not random green.",
        "paint": "network",
    },
    "Life in the fragments": {
        "slug": "04_life_in_the_fragments",
        "fit": "context",
        "sentence": "Listed life still gathers where the remnant holds.",
        "paint": "species",
    },
    "An island or a network?": {
        "slug": "05_island_or_network",
        "fit": "aoi",
        "sentence": "Patches, streams, and tears — is this an island or a lattice?",
        "paint": "network",
    },
    "Follow an animal": {
        "slug": "06_follow_an_animal",
        "fit": "context",
        "sentence": "Imagine a small forest mammal — every gap changes the journey.",
        "paint": "network",
    },
    "The missing pieces": {
        "slug": "07_the_missing_pieces",
        "fit": "aoi",
        "sentence": "These are places the network frays — candidates, not commitments.",
        "paint": "opportunity",
    },
    "What could 50 trees do?": {
        "slug": "08_what_could_50_trees_do",
        "fit": "context",
        "sentence": "Sometimes the most important hectare sits between two living places.",
        "paint": "opportunity",
    },
    "Restoration opportunity": {
        "slug": "09_restoration_opportunity",
        "fit": "aoi",
        "sentence": "Each colour is a separate ingredient — not a hidden score.",
        "paint": "opportunity",
    },
    "Beyond the park boundary": {
        "slug": "10_beyond_the_park_boundary",
        "fit": "aoi",
        "sentence": "Conservation can thread through many tenures — not only national parks.",
        "paint": "opportunity",
    },
    "People putting rainforest back": {
        "slug": "11_people_putting_rainforest_back",
        "fit": "context",
        "sentence": "People kept this remnant — people may reconnect it.",
        "paint": "small_patch",
    },
    "Why should Robertson care?": {
        "slug": "12_why_should_robertson_care",
        "fit": "aoi",
        "sentence": "Wildlife, water, character, community — reasons beyond a species list.",
        "paint": "setting",
    },
    "Rainforest village": {
        "slug": "13_rainforest_village",
        "fit": "close",
        "sentence": "A village identity woven with creeks and stepping stones — conceptual.",
        "paint": "small_patch",
    },
    "With and without the reserve": {
        "slug": "14_with_and_without_the_reserve",
        "fit": "aoi",
        "sentence": "A fair test: how does the network change if this seed is removed?",
        "paint": "network",
    },
    "Adding one more piece": {
        "slug": "15_adding_one_more_piece",
        "fit": "aoi",
        "sentence": "Where could a small addition reconnect more than its own hectares?",
        "paint": "opportunity",
    },
    "The 2040 landscape": {
        "slug": "16_the_2040_landscape",
        "fit": "aoi",
        "sentence": "A more connected network threaded through a working landscape.",
        "paint": "living",
    },
}


def _read_layer(layer: str) -> gpd.GeoDataFrame:
    g = gpd.read_file(MASTER, layer=layer)
    if g.empty:
        return g
    return g.to_crs(CRS_M)


def _fit_bounds(fit: str, reserve: gpd.GeoDataFrame, study: gpd.GeoDataFrame) -> tuple[float, float, float, float]:
    if fit == "aoi" and not study.empty:
        return tuple(study.total_bounds)
    metres = {"close": 700, "near": 2400, "context": 5500}.get(fit, 2400)
    buf = reserve.copy()
    buf["geometry"] = buf.geometry.buffer(metres)
    return tuple(buf.total_bounds)


def _xy_to_px(x: float, y: float, transform) -> tuple[float, float]:
    a, _, c, _, e, f = transform.a, transform.b, transform.c, transform.d, transform.e, transform.f
    return (x - c) / a, (y - f) / e


def _fonts():
    candidates = [
        ("C:/Windows/Fonts/georgia.ttf", "C:/Windows/Fonts/georgiab.ttf", "C:/Windows/Fonts/segoeui.ttf"),
        ("C:/Windows/Fonts/Georgia.ttf", "C:/Windows/Fonts/georgiab.ttf", "C:/Windows/Fonts/segoeuib.ttf"),
    ]
    for body, bold, ui in candidates:
        try:
            return (
                ImageFont.truetype(body, 20),
                ImageFont.truetype(body, 30),
                ImageFont.truetype(bold if Path(bold).is_file() else body, 42),
                ImageFont.truetype(ui if Path(ui).is_file() else body, 17),
            )
        except Exception:
            continue
    d = ImageFont.load_default()
    return d, d, d, d


def _influence_wash(base: Image.Image, center: Point, transform, radius_m: float = 3500, rgb=(255, 210, 120)) -> Image.Image:
    """Soft golden wash radiating from the reserve — the visual ‘why it matters’ ripple."""
    wash = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(wash)
    cx, cy = _xy_to_px(center.x, center.y, transform)
    m_per_px = abs(transform.a)
    r = radius_m / m_per_px
    for i, (frac, alpha) in enumerate(((1.0, 28), (0.7, 40), (0.4, 55), (0.18, 70))):
        rr = r * frac
        draw.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=(*rgb, alpha))
    wash = wash.filter(ImageFilter.GaussianBlur(radius=max(8, r * 0.08)))
    return Image.alpha_composite(base.convert("RGBA"), wash).convert("RGB")


def _draw_callouts(
    img: Image.Image,
    transform,
    center: Point,
    callouts: list[tuple[str, str]],
    *,
    anchor: str = "right",
) -> Image.Image:
    """
    Story callouts that explain scale / meaning.
    callouts: list of (big_stat, small_label)
    """
    out = img.convert("RGBA")
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font_kicker, font_body, font_stat, font_ui = _fonts()
    cx, cy = _xy_to_px(center.x, center.y, transform)

    # Card stack on the right (or left)
    card_w, card_h = 420, 78 + 72 * len(callouts)
    if anchor == "right":
        x0 = W - card_w - 36
    else:
        x0 = 36
    y0 = 36
    draw.rounded_rectangle([x0, y0, x0 + card_w, y0 + card_h], radius=16, fill=(248, 245, 238, 228))
    draw.text((x0 + 22, y0 + 16), "WHY THIS PATCH MATTERS", fill=(110, 120, 112, 255), font=font_ui)

    y = y0 + 48
    for stat, label in callouts:
        draw.text((x0 + 22, y), stat, fill=(30, 58, 40, 255), font=font_stat)
        draw.text((x0 + 22, y + 46), label, fill=(80, 90, 82, 255), font=font_body)
        y += 72

    # Leader to reserve
    tip_x = x0 if anchor == "right" else x0 + card_w
    tip_y = y0 + card_h * 0.45
    draw.line([(tip_x, tip_y), (cx, cy)], fill=(201, 162, 74, 200), width=2)
    draw.ellipse([cx - 7, cy - 7, cx + 7, cy + 7], fill=(255, 230, 140, 255), outline=(30, 58, 40, 255), width=2)

    return Image.alpha_composite(out, overlay).convert("RGB")


def _reserve_halo(img: Image.Image, ru, transform) -> Image.Image:
    """Bright outline + fill so the tiny reserve never disappears in the landscape."""
    core = _mask_geoms([ru], transform)
    ring = _mask_geoms([ru.buffer(90).difference(ru.buffer(20))], transform)
    img = _tint(img, core, (22, 70, 40), 0.78)
    img = _tint(img, ring, (255, 248, 220), 0.90)
    return img


def _hillshade(z: np.ndarray, azimuth: float = 315.0, altitude: float = 42.0) -> np.ndarray:
    x, y = np.gradient(z.astype("float64"))
    slope = np.pi / 2.0 - np.arctan(np.sqrt(x * x + y * y))
    aspect = np.arctan2(-x, y)
    az = math.radians(azimuth)
    alt = math.radians(altitude)
    shaded = np.sin(alt) * np.sin(slope) + np.cos(alt) * np.cos(slope) * np.cos(az - aspect)
    shaded = (shaded - shaded.min()) / (shaded.max() - shaded.min() + 1e-9)
    return shaded.astype("float32")


def _dem_canvas(bounds_m: tuple[float, float, float, float]) -> Image.Image:
    """Muted parchment terrain from DEM hillshade — Amazon-plate atmosphere."""
    minx, miny, maxx, maxy = bounds_m
    # Slight pad so edges don't clip hard
    pad = (maxx - minx) * 0.04
    minx, miny, maxx, maxy = minx - pad, miny - pad, maxx + pad, maxy + pad
    transform = from_bounds(minx, miny, maxx, maxy, W, H)

    parchment = np.zeros((H, W, 3), dtype="float32")
    parchment[..., 0] = 0.91
    parchment[..., 1] = 0.90
    parchment[..., 2] = 0.86

    if DEM.is_file():
        with rasterio.open(DEM) as src:
            dem = np.zeros((H, W), dtype="float32")
            reproject(
                source=rasterio.band(src, 1),
                destination=dem,
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=transform,
                dst_crs=CRS_M,
                resampling=Resampling.bilinear,
            )
            nodata = src.nodata
        if nodata is not None:
            dem = np.where(dem == nodata, np.nan, dem)
        if np.isfinite(dem).sum() > 100:
            fill = np.nanmedian(dem)
            dem = np.where(np.isfinite(dem), dem, fill)
            hs = _hillshade(dem)
            # Cool-grey terrain wash (desaturated, like the Amazon references)
            terrain = np.stack(
                [
                    0.72 + 0.18 * hs,
                    0.73 + 0.16 * hs,
                    0.70 + 0.14 * hs,
                ],
                axis=-1,
            )
            parchment = 0.35 * parchment + 0.65 * terrain

    rgb = np.clip(parchment * 255, 0, 255).astype("uint8")
    img = Image.fromarray(rgb, mode="RGB")
    # Soft grain
    rng = np.random.default_rng(42)
    noise = rng.integers(0, 18, size=(H, W), dtype="uint8")
    grain = Image.fromarray(noise, mode="L").convert("RGB")
    img = Image.blend(img, grain, 0.045)
    return img, transform, (minx, miny, maxx, maxy)


def _mask_geoms(geoms, transform, burn: int = 255) -> np.ndarray:
    shapes = [(mapping(g), burn) for g in geoms if g is not None and not g.is_empty]
    if not shapes:
        return np.zeros((H, W), dtype="uint8")
    return rasterize(
        shapes,
        out_shape=(H, W),
        transform=transform,
        fill=0,
        dtype="uint8",
        all_touched=True,
    )


def _tint(base: Image.Image, mask: np.ndarray, rgb: tuple[int, int, int], alpha: float) -> Image.Image:
    if mask.max() == 0:
        return base
    overlay = Image.new("RGBA", (W, H), (*rgb, 0))
    a = Image.fromarray((mask.astype("float32") / 255.0 * alpha * 255).astype("uint8"), mode="L")
    color = Image.new("RGBA", (W, H), (*rgb, 255))
    overlay = Image.composite(color, overlay, a)
    return Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")


def _soft_glow(
    base: Image.Image,
    points_xy: list[tuple[float, float]],
    transform,
    *,
    color: tuple[int, int, int] = (255, 196, 70),
    radius_px: float = 28,
    strength: float = 0.85,
) -> Image.Image:
    """Amazon-style ember glows at metric point locations."""
    if not points_xy:
        return base
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow)
    a, b, c, d, e, f = transform.a, transform.b, transform.c, transform.d, transform.e, transform.f
    # transform: x = c + col*a ; y = f + row*e  (e negative usually)
    for x, y in points_xy:
        col = (x - c) / a
        row = (y - f) / e
        r = radius_px
        bbox = [col - r, row - r, col + r, row + r]
        draw.ellipse(bbox, fill=(*color, int(210 * strength)))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=radius_px * 0.55))
    # Second softer halo
    halo = glow.filter(ImageFilter.GaussianBlur(radius=radius_px * 1.1))
    out = Image.alpha_composite(base.convert("RGBA"), halo)
    out = Image.alpha_composite(out, glow)
    return out.convert("RGB")


def _rings(base: Image.Image, center: Point, transform, radii_m: list[float], color=(180, 120, 40)) -> Image.Image:
    draw_img = base.convert("RGBA")
    ring_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ring_layer)
    a, _, c, _, e, f = transform.a, transform.b, transform.c, transform.d, transform.e, transform.f
    cx = (center.x - c) / a
    cy = (center.y - f) / e
    m_per_px_x = abs(a)
    m_per_px_y = abs(e)
    for i, rm in enumerate(radii_m):
        rx = rm / m_per_px_x
        ry = rm / m_per_px_y
        alpha = 90 - i * 18
        draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], outline=(*color, max(30, alpha)), width=2)
    ring_layer = ring_layer.filter(ImageFilter.GaussianBlur(0.6))
    return Image.alpha_composite(draw_img, ring_layer).convert("RGB")


def _vignette(base: Image.Image, strength: float = 0.42) -> Image.Image:
    yy, xx = np.mgrid[0:H, 0:W]
    cx, cy = W / 2, H / 2
    dist = np.sqrt(((xx - cx) / (W * 0.55)) ** 2 + ((yy - cy) / (H * 0.55)) ** 2)
    shade = np.clip(dist, 0, 1) ** 1.35
    alpha = (shade * strength * 255).astype("uint8")
    veil = Image.new("RGBA", (W, H), (28, 32, 30, 0))
    veil.putalpha(Image.fromarray(alpha, mode="L"))
    return Image.alpha_composite(base.convert("RGBA"), veil).convert("RGB")


def _aoi_focus(base: Image.Image, study: gpd.GeoDataFrame, transform, wash=(120, 130, 95)) -> Image.Image:
    if study.empty:
        return base
    mask = _mask_geoms(list(study.geometry), transform)
    # Soften AOI edge
    mimg = Image.fromarray(mask, mode="L").filter(ImageFilter.GaussianBlur(8))
    mask = np.array(mimg)
    # Outside AOI slightly desaturated / lifted
    arr = np.array(base).astype("float32")
    outside = mask < 40
    arr[outside] = arr[outside] * 0.78 + np.array([235, 235, 232]) * 0.22
    base = Image.fromarray(np.clip(arr, 0, 255).astype("uint8"))
    return _tint(base, mask, wash, alpha=0.14)


def _dissolve(gdf: gpd.GeoDataFrame):
    if gdf is None or gdf.empty:
        return None
    return unary_union(list(gdf.geometry))


def _centroids(gdf: gpd.GeoDataFrame, weight_col: str | None = None, max_n: int = 180) -> list[tuple[float, float]]:
    if gdf is None or gdf.empty:
        return []
    g = gdf.copy()
    if weight_col and weight_col in g.columns:
        g["_w"] = np.sqrt(pd_to_num(g[weight_col]).clip(lower=0) + 1)
        g = g.sort_values("_w", ascending=False).head(max_n)
    else:
        g = g.head(max_n)
    pts = []
    for geom in g.geometry:
        if geom is None or geom.is_empty:
            continue
        c = geom.centroid
        pts.append((c.x, c.y))
    return pts


def pd_to_num(s):
    import pandas as pd

    return pd.to_numeric(s, errors="coerce").fillna(0)


def _line_mask(gdf: gpd.GeoDataFrame, transform, width_m: float = 40) -> np.ndarray:
    if gdf is None or gdf.empty:
        return np.zeros((H, W), dtype="uint8")
    buf = gdf.copy()
    buf["geometry"] = buf.geometry.buffer(width_m)
    return _mask_geoms(list(buf.geometry), transform)


def _ha(geom) -> float:
    if geom is None or geom.is_empty:
        return 0.0
    return float(geom.area) / 10000.0


def _draw_connectors(img: Image.Image, center: Point, patches: gpd.GeoDataFrame, transform, max_n: int = 14) -> Image.Image:
    """Thin dashed links from reserve to nearby habitat — network as story."""
    if patches is None or patches.empty:
        return img
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    cx, cy = _xy_to_px(center.x, center.y, transform)
    g = patches.copy()
    g["_d"] = g.geometry.centroid.distance(center)
    g = g.sort_values("_d").head(max_n)
    for geom in g.geometry:
        if geom is None or geom.is_empty:
            continue
        c = geom.centroid
        px, py = _xy_to_px(c.x, c.y, transform)
        # dashed feel via short segments
        steps = 18
        for i in range(0, steps, 2):
            t0, t1 = i / steps, min(1.0, (i + 1) / steps)
            x0, y0 = cx + (px - cx) * t0, cy + (py - cy) * t0
            x1, y1 = cx + (px - cx) * t1, cy + (py - cy) * t1
            draw.line([(x0, y0), (x1, y1)], fill=(201, 162, 74, 160), width=2)
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def paint_plate(name: str, recipe: dict, layers: dict) -> Image.Image:
    reserve, study = layers["reserve"], layers["study"]
    bounds = _fit_bounds(recipe["fit"], reserve, study)
    img, transform, _ = _dem_canvas(bounds)
    img = _aoi_focus(img, study, transform)

    ru = unary_union(list(reserve.geometry))
    center = ru.centroid
    mode = recipe["paint"]
    reserve_ha = _ha(ru)

    rf = layers["rainforest"]
    preclear = layers["preclear"]
    cleared = layers["cleared"]
    core = layers["core"]
    roads = layers["roads"]
    basalt = layers["basalt"]
    hydro = layers["hydro"]
    riparian = layers["riparian"]
    threat = layers["threat"]
    fire = layers["fire"]
    comps = layers["comps"]

    rf_ha = _ha(_dissolve(rf)) if not rf.empty else 0.0
    pre_ha = _ha(_dissolve(preclear)) if not preclear.empty else 0.0
    near_rf = 0.0
    if not rf.empty:
        # Area of rainforest intersecting a walkable ring around the reserve
        walk = ru.buffer(1000)
        try:
            near_rf = float(rf.geometry.intersection(walk).area.sum() / 10000.0)
        except Exception:
            near_rf = 0.0

    # Shared: influence wash so the small patch radiates meaning into the landscape
    img = _influence_wash(img, center, transform, radius_m=4200 if recipe["fit"] != "aoi" else 7000)

    if mode == "small_patch":
        if not rf.empty:
            img = _tint(img, _mask_geoms([_dissolve(rf)], transform), (62, 102, 68), 0.42)
        img = _rings(img, center, transform, [500, 1000, 2000, 5000], color=(170, 120, 45))
        img = _reserve_halo(img, ru, transform)
        img = _soft_glow(img, [(center.x, center.y)], transform, color=(255, 220, 120), radius_px=42, strength=1.0)
        img = _draw_callouts(
            img,
            transform,
            center,
            [
                (f"{reserve_ha:.1f} ha", "legally protected here"),
                (f"{near_rf:,.0f} ha", "rainforest within a short walk"),
                (f"{rf_ha:,.0f} ha", "remnant still in this landscape"),
            ],
        )

    elif mode == "remains":
        if not cleared.empty:
            img = _tint(img, _mask_geoms([_dissolve(cleared)], transform), (230, 224, 214), 0.30)
        if not preclear.empty:
            img = _tint(img, _mask_geoms([_dissolve(preclear)], transform), (196, 165, 116), 0.24)
        if not rf.empty:
            img = _tint(img, _mask_geoms([_dissolve(rf)], transform), (48, 96, 62), 0.58)
        img = _reserve_halo(img, ru, transform)
        img = _soft_glow(img, [(center.x, center.y)], transform, color=(255, 225, 140), radius_px=34, strength=0.95)
        lost = max(0.0, pre_ha - rf_ha)
        img = _draw_callouts(
            img,
            transform,
            center,
            [
                (f"{rf_ha:,.0f} ha", "rainforest that remains"),
                (f"{lost:,.0f} ha", "modelled cover already gone"),
                (f"{reserve_ha:.1f} ha", "protected heart of the remnant"),
            ],
            anchor="left",
        )

    elif mode == "species":
        if not rf.empty:
            img = _tint(img, _mask_geoms([_dissolve(rf)], transform), (75, 108, 82), 0.28)
        # Emphasize records near the reserve more than far ones
        if not threat.empty:
            t = threat.copy()
            t["_d"] = t.geometry.centroid.distance(center)
            near = t.loc[t["_d"] <= 3000]
            far = t.loc[t["_d"] > 3000]
            img = _soft_glow(img, _centroids(far, "threat_n_species", 80), transform, color=(255, 170, 130), radius_px=14, strength=0.35)
            img = _soft_glow(img, _centroids(near, "threat_n_species", 160), transform, color=(255, 120, 70), radius_px=26, strength=0.85)
            hot = near
            if "threat_n_species" in hot.columns:
                hot = hot.loc[pd_to_num(hot["threat_n_species"]) >= 2]
                img = _soft_glow(img, _centroids(hot, "threat_n_species", 60), transform, color=(255, 70, 30), radius_px=32, strength=0.95)
        img = _reserve_halo(img, ru, transform)
        n_cells = int(len(threat)) if not threat.empty else 0
        img = _draw_callouts(
            img,
            transform,
            center,
            [
                ("Refuge", "listed life gathers near this remnant"),
                (f"{n_cells}", "public aggregate cells nearby"),
                (f"{reserve_ha:.1f} ha", "the protected foothold"),
            ],
        )

    elif mode == "network":
        if not core.empty:
            img = _tint(img, _mask_geoms(list(core.geometry), transform), (42, 92, 55), 0.52)
            img = _draw_connectors(img, center, core, transform, max_n=16)
        if not roads.empty:
            hi = roads.loc[roads["barrier_class"] == "high"] if "barrier_class" in roads.columns else roads.iloc[0:0]
            med = roads.loc[roads["barrier_class"] == "medium"] if "barrier_class" in roads.columns else roads.iloc[0:0]
            img = _tint(img, _line_mask(med, transform, 28), (194, 85, 45), 0.40)
            img = _tint(img, _line_mask(hi, transform, 38), (140, 30, 50), 0.52)
        img = _rings(img, center, transform, [1000, 2000, 5000], color=(160, 110, 40))
        img = _reserve_halo(img, ru, transform)
        img = _soft_glow(img, [(center.x, center.y)], transform, color=(255, 215, 120), radius_px=30, strength=0.9)
        n_core = int(len(core)) if not core.empty else 0
        img = _draw_callouts(
            img,
            transform,
            center,
            [
                (f"{n_core}", "habitat patches in the lattice"),
                ("Node", "the reserve holds a place in the network"),
                ("Tears", "roads that may interrupt movement"),
            ],
            anchor="left",
        )

    elif mode == "setting":
        if not basalt.empty:
            b = basalt
            if "is_basalt_or_volcanic" in b.columns:
                b = b.loc[b["is_basalt_or_volcanic"]]
            img = _tint(img, _mask_geoms([_dissolve(b)], transform), (110, 85, 60), 0.42)
        if not riparian.empty:
            r = riparian
            if "buffer_m" in r.columns:
                r = r.loc[r["buffer_m"] == 100]
            img = _tint(img, _mask_geoms([_dissolve(r)], transform), (120, 175, 190), 0.24)
        if not hydro.empty:
            img = _tint(img, _line_mask(hydro, transform, 22), (55, 105, 135), 0.65)
        img = _reserve_halo(img, ru, transform)
        img = _soft_glow(img, [(center.x, center.y)], transform, color=(255, 230, 170), radius_px=26, strength=0.8)
        img = _draw_callouts(
            img,
            transform,
            center,
            [
                ("Basalt", "volcanic ground that can hold rainforest"),
                ("Streams", "moisture lines through the remnant"),
                (f"{reserve_ha:.1f} ha", "protected on that stage"),
            ],
        )

    elif mode == "opportunity":
        if not rf.empty:
            img = _tint(img, _mask_geoms([_dissolve(rf)], transform), (65, 100, 72), 0.28)
        if not comps.empty and "component" in comps.columns:
            for comp, color, a in (
                ("isolated_patch_context", (251, 133, 0), 0.38),
                ("riparian_gap", (255, 77, 109), 0.45),
                ("patch_gap_edge", (255, 183, 3), 0.52),
            ):
                sub = comps.loc[comps["component"] == comp]
                if sub.empty:
                    continue
                geom = _dissolve(sub)
                if geom is not None:
                    soft = geom.buffer(90).buffer(-50)
                    img = _tint(img, _mask_geoms([soft], transform), color, a)
        img = _reserve_halo(img, ru, transform)
        img = _soft_glow(img, [(center.x, center.y)], transform, color=(255, 220, 140), radius_px=28, strength=0.9)
        img = _draw_callouts(
            img,
            transform,
            center,
            [
                ("Grow out", "plant where remnant already touches cleared edges"),
                ("Heal streams", "close gaps along moisture lines"),
                (f"{reserve_ha:.1f} ha", "start from what is already kept"),
            ],
            anchor="left",
        )

    elif mode == "living":
        if not rf.empty:
            img = _tint(img, _mask_geoms([_dissolve(rf)], transform), (60, 98, 68), 0.32)
        pts = _centroids(threat, "threat_n_species", 200)
        img = _soft_glow(img, pts, transform, color=(255, 150, 95), radius_px=22, strength=0.72)
        if not fire.empty:
            fpts = [(g.x, g.y) for g in fire.geometry if g is not None and not g.is_empty]
            img = _soft_glow(img, fpts, transform, color=(255, 60, 40), radius_px=38, strength=1.0)
        img = _reserve_halo(img, ru, transform)
        img = _soft_glow(img, [(center.x, center.y)], transform, color=(255, 230, 150), radius_px=28, strength=0.9)
        img = _draw_callouts(
            img,
            transform,
            center,
            [
                ("Living", "refuge blooms + greenness + fire watch"),
                ("Association", "signals near the remnant — not causation"),
                (f"{reserve_ha:.1f} ha", "still the protected anchor"),
            ],
        )

    img = _vignette(img, 0.34)
    img = ImageEnhance.Contrast(img).enhance(1.08)
    img = ImageEnhance.Color(img).enhance(0.90)
    return img


def _caption_strip(img: Image.Image, title: str, sentence: str) -> Image.Image:
    """Bottom thesis caption — StoryMap media feel."""
    out = img.convert("RGBA")
    bar = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(bar)
    font_kicker, font_body, _, _ = _fonts()
    box_w = 720
    draw.rounded_rectangle([32, H - 132, 32 + box_w, H - 32], radius=16, fill=(248, 245, 238, 230))
    draw.text((54, H - 116), title.upper(), fill=(100, 110, 105, 255), font=font_kicker)
    words = sentence.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font_body) < box_w - 50:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    y = H - 88
    for line in lines[:2]:
        draw.text((54, y), line, fill=(30, 58, 40, 255), font=font_body)
        y += 32
    return Image.alpha_composite(out, bar).convert("RGB")


def load_layers() -> dict:
    reserve = _read_layer("robertson_nature_reserve")
    study = _read_layer("study_area")
    rainforest = _read_layer("rainforest_extant")
    preclear = _read_layer("rainforest_preclear_modelled")
    cleared = _read_layer("cleared_or_non_native")
    core = _read_layer("core_habitat_patches")
    roads = _read_layer("roads_barriers")
    basalt = _read_layer("geology_rock_units")
    hydro = _read_layer("hydro_lines")
    riparian = _read_layer("riparian_buffers")
    try:
        comps = _read_layer("component_polygons")
    except Exception:
        comps = gpd.GeoDataFrame(geometry=[], crs=CRS_M)

    if LIVING.is_file():
        try:
            threat = gpd.read_file(LIVING, layer="threatened_species_living").to_crs(CRS_M)
        except Exception:
            threat = _read_layer("threatened_species_aggregated")
        try:
            fire = gpd.read_file(LIVING, layer="fire_incidents_living").to_crs(CRS_M)
        except Exception:
            fire = gpd.GeoDataFrame(geometry=[], crs=CRS_M)
    else:
        threat = _read_layer("threatened_species_aggregated")
        fire = gpd.GeoDataFrame(geometry=[], crs=CRS_M)

    return {
        "reserve": reserve,
        "study": study,
        "rainforest": rainforest,
        "preclear": preclear,
        "cleared": cleared,
        "core": core,
        "roads": roads,
        "basalt": basalt,
        "hydro": hydro,
        "riparian": riparian,
        "threat": threat,
        "fire": fire,
        "comps": comps,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Render art-forward story plates")
    parser.add_argument("--chapter", default=None, help="Single chapter title to render")
    parser.add_argument("--no-caption", action="store_true", help="Skip baked caption strip")
    args = parser.parse_args()

    settings = load_settings()
    paths = settings["resolved_paths"]
    logger = setup_logging(paths["logs_dir"], name="story_plates", level="INFO")
    ensure_dirs(OUT_DIR)

    if not MASTER.is_file():
        raise SystemExit(f"Master GPKG missing: {MASTER}")

    logger.info("Loading layers…")
    layers = load_layers()
    chapters = RECIPES
    if args.chapter:
        if args.chapter not in RECIPES:
            raise SystemExit(f"Unknown chapter: {args.chapter}")
        chapters = {args.chapter: RECIPES[args.chapter]}

    for title, recipe in chapters.items():
        logger.info("Rendering plate: %s", title)
        img = paint_plate(title, recipe, layers)
        if not args.no_caption:
            img = _caption_strip(img, title, recipe["sentence"])
        out = OUT_DIR / f"{recipe['slug']}.png"
        img.save(out, "PNG", optimize=True)
        logger.info("Wrote %s", out)

    logger.info("Done. Plates in %s", OUT_DIR)


if __name__ == "__main__":
    main()
