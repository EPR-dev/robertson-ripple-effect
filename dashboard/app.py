"""
Robertson Rainforest — community StoryMap (Streamlit).

A shareable story for the people of Robertson: maps evolve with the chapters;
numbers stay honest. Not a GIS product page.

Run: .\\start-dashboard.ps1
"""

from __future__ import annotations

import base64
import json
from io import BytesIO
from pathlib import Path

import folium
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import streamlit as st
from branca.element import MacroElement, Template
from PIL import Image
from rasterio.enums import Resampling
from rasterio.warp import transform_bounds
from shapely.geometry import LineString
from shapely.ops import nearest_points, unary_union
from streamlit_folium import st_folium

from story_v1 import (
    ACKNOWLEDGEMENT_OF_COUNTRY,
    ACTION_STEPS,
    BRAND,
    BRAND_ALT,
    BRAND_SUBTITLE,
    BRAND_TAGLINE,
    CHAPTER_LAYER_DEFAULTS,
    CHAPTER_MAP_RECIPES,
    CHAPTER_PLATE_SLUGS,
    CHAPTERS,
    EVIDENCE_HELP,
    FLOW_STEPS,
    GUILD_CARE_HINTS,
    LAND_CARE_DEFAULT_ID,
    LAND_CARE_INTEGRITY,
    LAND_CARE_LIFE_LINKS,
    LAND_MANAGEMENT_WORK,
    LAND_MANAGEMENT_BY_ID,
    LIFE_WORTH_INTEGRITY,
    STORY_SPINE,
    build_story_slides,
    land_care_count,
    land_care_work,
)

ROOT = Path(__file__).resolve().parents[1]
MASTER_GPKG = ROOT / "outputs" / "geopackage" / "robertson_conservation.gpkg"
TWIN_DIR = ROOT / "outputs" / "twin_lakes"
STORY_PACKAGE = TWIN_DIR / "story_package.json"
LIVING_GPKG = TWIN_DIR / "living_layers.gpkg"
NEIGHBOURS_SEASON_CSV = TWIN_DIR / "neighbours_season.csv"
GREENNESS_SUMMARY_CSV = TWIN_DIR / "greenness_summary.csv"
PROFILE_JSON = ROOT / "outputs" / "csv" / "reserve_ecological_profile.json"
WILDLIFE_JSON = ROOT / "outputs" / "csv" / "wildlife_plants_story.json"
GAPS_SUMMARY_JSON = ROOT / "outputs" / "csv" / "habitat_gaps_summary.json"
PARCEL_EXPLORER_JSON = ROOT / "outputs" / "csv" / "parcel_explorer.json"
HABITAT_SUMMARY_JSON = ROOT / "outputs" / "csv" / "habitat_network_summary.json"
PLATES_DIR = ROOT / "dashboard" / "assets" / "plates"
THEN_NOW_DIR = ROOT / "dashboard" / "assets" / "then_now"
DEM_PATH = ROOT / "outputs" / "raster" / "phase5" / "dem_clip.tif"
CRS_M = "EPSG:7856"

# Two visual languages:
#   land   = canopy / remnant / restore (moss + gold)  → positive land influence
#   species = refuge blooms (rose–copper, organic)     → living systems, not land cover
#   setting = topo / geology / water (umber + steel)
#   barrier = muted rust
#   cue    = ripple / study frame
BASEMAPS = {
    "Soft paper": {
        "tiles": "CartoDB positron",
        "attr": "© OpenStreetMap © CARTO",
    },
    "Topographic": {
        "tiles": "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
        "attr": "© OpenStreetMap contributors, SRTM | © OpenTopoMap (CC-BY-SA)",
        "subdomains": "abc",
        "max_zoom": 17,
    },
    "Esri terrain": {
        "tiles": (
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Topo_Map/MapServer/tile/{z}/{y}/{x}"
        ),
        "attr": "Tiles © Esri — Esri, USGS, NOAA",
        "max_zoom": 18,
    },
    "Satellite + labels": {
        # Esri World Imagery — path order is z/y/x (ArcGIS row/col), not OSM z/x/y
        "tiles": (
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/{z}/{y}/{x}"
        ),
        "attr": "Tiles © Esri — Esri, Maxar, Earthstar Geographics",
        "max_zoom": 19,
        "labels": (
            "https://services.arcgisonline.com/ArcGIS/rest/services/"
            "Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}"
        ),
    },
}

LAYERS = {
    "hillshade": {
        "label": "Terrain hillshade",
        "plain": "Relief from Copernicus DEM — cartographic underlay",
        "color": "#78716c",
        "kind": "raster",
        "family": "setting",
        "source": None,
    },
    "elev": {
        "label": "Elevation wash",
        "plain": "Hypsometric tint from analysis grid (higher = cooler)",
        "color": "#a8a29e",
        "kind": "elev",
        "family": "setting",
        "source": "analysis_grid_metrics",
    },
    "reserve": {
        "label": "Robertson Nature Reserve",
        "plain": "The small protected rainforest anchor",
        "color": "#1a3c2a",
        "kind": "poly",
        "family": "land",
        "source": "robertson_nature_reserve",
    },
    "study": {
        "label": "Study area",
        "plain": "12.5 km landscape used for analysis",
        "color": "#78716c",
        "kind": "poly",
        "family": "cue",
        "source": "study_area",
    },
    "rainforest": {
        "label": "Rainforest that remains",
        "plain": "Mapped extant rainforest — positive land remnant",
        "color": "#3f6f4a",
        "kind": "poly",
        "family": "land",
        "source": "rainforest_extant",
    },
    "preclear": {
        "label": "Modelled historic rainforest",
        "plain": "SVTM pre-clear estimate (not Yarrawa Brush boundary)",
        "color": "#c4a574",
        "kind": "poly",
        "family": "land",
        "source": "rainforest_preclear_modelled",
    },
    "cleared": {
        "label": "Cleared / non-native",
        "plain": "Contrast mask where native PCT is absent",
        "color": "#e7e0d6",
        "kind": "poly",
        "family": "land",
        "source": "cleared_or_non_native",
    },
    "core": {
        "label": "Core habitat patches",
        "plain": "Rainforest + wet sclerophyll network units",
        "color": "#2f5d3a",
        "kind": "poly",
        "family": "land",
        "source": "core_habitat_patches",
    },
    "roads_high": {
        "label": "Stronger road barriers",
        "plain": "Higher-order roads (barrier candidates)",
        "color": "#9f1239",
        "kind": "line",
        "family": "barrier",
        "source": "roads_barriers",
    },
    "roads_med": {
        "label": "Moderate road barriers",
        "plain": "Arterial / collector candidates",
        "color": "#c2410c",
        "kind": "line",
        "family": "barrier",
        "source": "roads_barriers",
    },
    "hydro": {
        "label": "Streams",
        "plain": "Mapped watercourses",
        "color": "#3b6d8c",
        "kind": "line",
        "family": "setting",
        "source": "hydro_lines",
    },
    "riparian": {
        "label": "Riparian zone (100 m)",
        "plain": "Land within 100 m of streams",
        "color": "#7eb8c9",
        "kind": "poly",
        "family": "setting",
        "source": "riparian_buffers",
    },
    "basalt": {
        "label": "Basalt / latite soils setting",
        "plain": "Volcanic geology associated with local rainforest",
        "color": "#6b4f3a",
        "kind": "poly",
        "family": "setting",
        "source": "geology_rock_units",
    },
    "threat_grid": {
        "label": "Listed-species hexes",
        "plain": "Hex intensity of public listed-species records (aggregated — never dens)",
        "color": "#e76f51",
        "kind": "grid",
        "family": "species",
        "source": "threatened_species_aggregated",
    },
    "fire_hotspots": {
        "label": "Fire / hotspot watch",
        "plain": "Recent hotspots in the study window (FIRMS / RFS)",
        "color": "#c1121f",
        "kind": "points",
        "family": "barrier",
        "source": "fire_incidents_living",
    },
    "ripple": {
        "label": "Ripple distance bands",
        "plain": "0.5 / 1 / 2 / 5 km rings from the reserve",
        "color": "#b45309",
        "kind": "ripple",
        "family": "cue",
        "source": None,
    },
    "opp_edge": {
        "label": "Cleared edges next to habitat",
        "plain": "Bright gold — plant here to grow remnants",
        "color": "#ffb703",
        "kind": "opp",
        "family": "land",
        "source": "component_polygons",
        "component": "patch_gap_edge",
    },
    "opp_riparian": {
        "label": "Cleared gaps along streams",
        "plain": "Hot coral — stream-side places to heal",
        "color": "#ff4d6d",
        "kind": "opp",
        "family": "land",
        "source": "component_polygons",
        "component": "riparian_gap",
    },
    "opp_isolated": {
        "label": "Near isolated patches",
        "plain": "Amber — gaps around lonelier habitat",
        "color": "#fb8500",
        "kind": "opp",
        "family": "land",
        "source": "component_polygons",
        "component": "isolated_patch_context",
    },
    "opp_public": {
        "label": "Public / Crown land",
        "plain": "Lime — tenure that may be easier to act on",
        "color": "#8ac926",
        "kind": "opp",
        "family": "land",
        "source": "component_polygons",
        "component": "on_public_land",
    },
}

# Chapter recipes / plate slugs live in story_v1.py (Bring Back the Brush V1).

FAMILY_LABELS = {
    "land": ("Land influence", "Moss & gold — remnant habitat and places to grow it"),
    "species": ("Species refuge", "Rose–copper blooms — where listed life gathers"),
    "setting": ("Landscape setting", "Umber & steel — terrain, geology, water"),
    "barrier": ("Barriers", "Muted rust — roads that may fragment movement"),
    "cue": ("Story cues", "Amber rings & study frame"),
}

# What the geometry is, why it matters to the story, what hover can share, what not to infer.
LAYER_GUIDE = {
    "hillshade": {
        "what": "A shaded picture of hills and valleys from the DEM (not a vegetation layer).",
        "why": "Gives topographic context so remnant rainforest and the reserve sit in real terrain.",
        "hover": "No feature hover — it is a continuous underlay.",
        "not": "Does not show habitat quality or reserve ‘impact’.",
    },
    "elev": {
        "what": "Bands of similar elevation from the 250 m analysis grid.",
        "why": "Robertson rainforest is tied to cool, elevated basalt landscapes — elevation is setting.",
        "hover": "Elevation class (quantile band).",
        "not": "Not a climate projection or suitability score.",
    },
    "reserve": {
        "what": "The gazetted NPWS estate polygon for Robertson Nature Reserve.",
        "why": "The protected legal seed — tiny in area, central to Bring Back the Brush.",
        "hover": "Reserve name, type, gazetted area, IUCN category.",
        "not": "The reserve boundary is not the same as all rainforest remnant.",
    },
    "study": {
        "what": "A 12.5 km analysis landscape around the reserve.",
        "why": "Defines how far we look for remnant, refuge, and restore ingredients.",
        "hover": "Study-area frame only.",
        "not": "Not a planning zone or statutory buffer.",
    },
    "rainforest": {
        "what": "Mapped patches of extant rainforest plant community types (SVTM).",
        "why": "Shows where rainforest land cover still exists — the physical remnant the reserve sits in.",
        "hover": "PCT name/class, patch area (ha), short meaning.",
        "not": "Not cadastral parcels; not proof the reserve created that remnant.",
    },
    "preclear": {
        "what": "Modelled pre-1750 rainforest extent from SVTM (estimated historic cover).",
        "why": "Contrast: how much rainforest land was once present vs what remains.",
        "hover": "Modelled historic patch / area context.",
        "not": "Not a surveyed Yarrawa Brush cadastral boundary.",
    },
    "cleared": {
        "what": "Land in the study area without classified native SVTM vegetation.",
        "why": "Shows the matrix where restoration or edges may matter.",
        "hover": "Cleared / non-native contrast mask.",
        "not": "Not a land-use zoning map; some native areas may be misclassified.",
    },
    "core": {
        "what": "Dissolved rainforest + wet sclerophyll patches after gap-close rules.",
        "why": "These are the network building blocks animals and plants can use across the landscape.",
        "hover": "Patch area, distance to reserve, gap to nearest patch, touches reserve?",
        "not": "Not a least-cost corridor; not field-validated habitat boundaries.",
    },
    "roads_high": {
        "what": "Higher-order roads classed as stronger movement barriers.",
        "why": "Helps explain where the habitat network may be severed.",
        "hover": "Road name, hierarchy, barrier class.",
        "not": "Not traffic volume or a species-specific resistance model.",
    },
    "roads_med": {
        "what": "Arterial/collector roads classed as moderate barriers.",
        "why": "Secondary friction in the habitat network story.",
        "hover": "Road name, hierarchy, barrier class.",
        "not": "Not proven wildlife mortality hotspots.",
    },
    "hydro": {
        "what": "Mapped watercourse lines.",
        "why": "Streams structure moisture, movement, and riparian restore opportunities.",
        "hover": "Stream geometry (line).",
        "not": "Not flow volume or water quality.",
    },
    "riparian": {
        "what": "Land within 100 m of mapped streams.",
        "why": "Riparian land often links patches and is a practical restore strip.",
        "hover": "100 m riparian zone.",
        "not": "Not a statutory vegetated buffer prescription.",
    },
    "basalt": {
        "what": "Geology units flagged as basalt / latite / volcanic.",
        "why": "Explains why rainforest can persist here (soils & landform setting).",
        "hover": "Unit name, lithology, short meaning.",
        "not": "Not a soil fertility score or reserve effect.",
    },
    "threat_grid": {
        "what": "Hex bins of public listed-species intensity near the reserve (aggregated from grid cells).",
        "why": "Shows where remnant landscape use is recorded more strongly — without dens or nest pins.",
        "hover": "Listed taxa count, public records, intensity class.",
        "not": "Empty hex ≠ absence. Effort-biased. Not reserve causation. Not exact locations.",
    },
    "fire_hotspots": {
        "what": "Recent fire incidents or satellite hotspots inside the study watch window.",
        "why": "Fire pressure is one reason cool rainforest remnant matters as refuge.",
        "hover": "Title, status, source.",
        "not": "Not proof the reserve stops fire. Not a full bushfire risk model.",
    },
    "ripple": {
        "what": "Distance rings measured from the reserve boundary (0.5 → 5 km).",
        "why": "A visual ruler for ‘how far from the protected node’ themes sit.",
        "hover": "Distance band label.",
        "not": "Not a measured ecological process or impact radius.",
    },
    "opp_edge": {
        "what": "Cleared land touching habitat — edge restore zone.",
        "why": "Planting here can enlarge living remnants.",
        "hover": "Cells, area (ha).",
        "not": "Not a ranked score or delivery plan.",
    },
    "opp_riparian": {
        "what": "Cleared land along streams — riparian restore zone.",
        "why": "Heal moisture corridors that link the landscape.",
        "hover": "Cells, area (ha).",
        "not": "Not a single opportunity index.",
    },
    "opp_isolated": {
        "what": "Cleared land near lonelier habitat patches.",
        "why": "Stepping-stone plantings may reconnect life.",
        "hover": "Cells, area (ha).",
        "not": "Not proof a corridor will succeed.",
    },
    "opp_public": {
        "what": "Crown / public land in the analysis grid.",
        "why": "Often easier for community programs to act on.",
        "hover": "Cells, area (ha).",
        "not": "Not permission to plant — verify tenure.",
    },
}

# Association cues for named threatened taxa (public records) — not reserve causation.
SPECIES_LANDSCAPE_WHY = {
    "Phascolarctos cinereus": (
        "Koalas need connected tree canopy and forage eucalypts in the wider remnant mosaic. "
        "Records near the reserve show the surrounding forest landscape is used."
    ),
    "Petauroides volans": (
        "Southern Greater Gliders rely on tall hollow-bearing trees and glide paths between patches — "
        "core habitat size and road barriers matter more than the reserve fence line alone."
    ),
    "Dasyurus maculatus": (
        "Spotted-tailed Quolls range across forest and edge habitats; remnant networks and lower road "
        "friction support their landscape use."
    ),
    "Pteropus poliocephalus": (
        "Grey-headed Flying-foxes forage widely on native blossom and fruit; rainforest and wet forest "
        "remnants are part of a much larger nightly range."
    ),
    "Potorous tridactylus trisulcatus": (
        "Long-nosed potoroos use dense ground cover in moist forest — remnant understorey and linked patches help."
    ),
    "Cercartetus nanus": (
        "Eastern Pygmy-possums use flowering shrubs and banksia/heath–forest edges in the remnant mosaic."
    ),
    "Petaurus norfolcensis": (
        "Squirrel Gliders need hollows and linked canopy; patch gaps and roads interrupt movement."
    ),
    "Miniopterus orianae oceanensis": (
        "Bent-winged bats roost in caves/structures and forage over forest and edges in the wider landscape."
    ),
    "Miniopterus australis": (
        "Little Bent-winged bats forage over forest mosaics; remnant cover supports insect prey habitat."
    ),
    "Chalinolobus dwyeri": (
        "Large-eared Pied Bats use caves and forage in forested valleys — terrain + remnant cover are the setting."
    ),
    "Falsistrellus tasmaniensis": (
        "Eastern False Pipistrelles forage in tall forest; hollow trees in core patches matter."
    ),
    "Scoteanax rueppellii": (
        "Greater Broad-nosed Bats hunt along forest edges and clearings — edge structure is part of the story."
    ),
    "Saccolaimus flaviventris": (
        "Yellow-bellied Sheathtail-bats forage high over woodland and forest mosaics."
    ),
    "Botaurus poiciloptilus": (
        "Australasian Bitterns need wetlands/reed habitats in the broader landscape, not rainforest alone."
    ),
    "Petroica phoenicea": (
        "Flame Robins use open forest and clearings seasonally — remnant edges and paddock trees matter."
    ),
    "Petroica boodang": (
        "Scarlet Robins use open forest and woodland edges in the remnant agricultural mosaic."
    ),
    "Daphoenositta chrysoptera": (
        "Varied Sittellas forage on rough-barked trees in connected woodland/forest patches."
    ),
    "Pycnoptilus floccosus": (
        "Pilotbirds favour dense wet forest understorey — moist remnant cores are the relevant land."
    ),
    "Persicaria elatior": (
        "Tall Knotweed is a moist-site plant; riparian and damp forest edges are the relevant setting."
    ),
}


def species_why_text(scientific: str, vernacular: str, taxon_group: str) -> str:
    if scientific in SPECIES_LANDSCAPE_WHY:
        return SPECIES_LANDSCAPE_WHY[scientific]
    group = (taxon_group or "").lower()
    name = vernacular or scientific
    if "mammal" in group:
        return (
            f"{name}: forest mammals in this dataset generally depend on remnant cover, hollows, "
            "and linked patches in the wider landscape — not the reserve polygon alone."
        )
    if group in {"aves", "bird"} or "aves" in group:
        return (
            f"{name}: forest/woodland birds use remnant vegetation structure across the mosaic; "
            "records indicate landscape use near the reserve."
        )
    if "flora" in group or "plant" in group:
        return (
            f"{name}: listed plants are tied to specific moist or forest site conditions in the remnant landscape."
        )
    return (
        f"{name}: public threatened records near the reserve indicate the remnant landscape is used. "
        "Treat as association with habitat, not proof the reserve caused the records."
    )


HERO_IMG = Path(__file__).resolve().parent / "assets" / "ripple_hero_rainforest.jpg"
ACK_PHOTO = Path(__file__).resolve().parent / "assets" / "acknowledgement" / "country_art.jpg"
LOGOS_DIR = Path(__file__).resolve().parent / "assets" / "logos"
LAND_CARE_DIR = Path(__file__).resolve().parent / "assets" / "land_care"

# Data providers used in this StoryMap (wordmarks / logos on the Respect page).
DATA_SOURCE_CREDITS = [
    {"file": "nsw_bionet.svg", "name": "NSW BioNet", "used_for": "Species observations"},
    {"file": "nsw_svtm.svg", "name": "NSW SVTM", "used_for": "Rainforest & vegetation maps"},
    {"file": "npws_raw.svg", "name": "NPWS NSW", "used_for": "Nature Reserve estate"},
    {"file": "spatial_nsw.svg", "name": "Spatial Services NSW", "used_for": "Roads, water, boundaries"},
    {"file": "esri.svg", "name": "Esri", "used_for": "Satellite basemap"},
    {"file": "openstreetmap.svg", "name": "OpenStreetMap", "used_for": "Soft paper basemap"},
    {"file": "copernicus.svg", "name": "Copernicus", "used_for": "Elevation / hillshade"},
]


def _image_data_uri(path: Path) -> str:
    """Return a data URI for a local image, or empty string if missing."""
    if not path.is_file():
        return ""
    raw = path.read_bytes()
    # Prefer magic bytes — Cursor-exported assets may use a .png name with JPEG content
    if raw[:2] == b"\xff\xd8":
        mime = "image/jpeg"
    elif raw[:8].startswith(b"\x89PNG"):
        mime = "image/png"
    elif raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        mime = "image/webp"
    else:
        mime = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".gif": "image/gif",
        }.get(path.suffix.lower(), "image/jpeg")
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


@st.cache_data(show_spinner=False)
def hero_image_b64() -> str:
    """Homepage hero artwork (data URI)."""
    return _image_data_uri(HERO_IMG)


@st.cache_data(show_spinner=False)
def acknowledgement_photo_b64() -> str:
    """Acknowledgement page Country artwork (data URI)."""
    return _image_data_uri(ACK_PHOTO)


@st.cache_data(show_spinner=False)
def logo_b64(filename: str, mtime_ns: int = 0) -> str:
    """Base64 for a logo file. Pass mtime_ns so Streamlit refreshes when assets change."""
    del mtime_ns
    path = LOGOS_DIR / filename
    if not path.is_file():
        return ""
    return base64.b64encode(path.read_bytes()).decode("ascii")


def logo_data_uri(filename: str) -> str:
    """data: URI for a logo, with correct MIME and cache-busting mtime."""
    path = LOGOS_DIR / filename
    if not path.is_file():
        return ""
    mtime = path.stat().st_mtime_ns
    b64 = logo_b64(filename, mtime)
    if not b64:
        return ""
    suffix = path.suffix.lower()
    mime = {
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(suffix, "image/png")
    return f"data:{mime};base64,{b64}"


@st.cache_data(show_spinner=False)
def land_care_photo_b64(filename: str) -> str:
    path = LAND_CARE_DIR / filename
    if not path.is_file():
        return ""
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _style_page() -> None:
    st.set_page_config(
        page_title="Robertson Rainforest · Lost · Kept · Life · Respect",
        page_icon="◈",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    # IMPORTANT: use st.html (not st.markdown) so CSS is never shown as page text.
    # Markdown treats [data-testid=...] as links and breaks <style> blocks.
    st.html(
        """
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,650;9..144,700&family=Outfit:wght@300;400;500;600&display=swap');
:root {
  --canopy: #1e3a28;
  --moss: #3f6f4a;
  --mist: #d7e2d4;
  --paper: #e4ebe3;
  --ink: #1c241c;
  --muted: #4d5a4f;
  --dawn: #c9a24a;
  --ember: #e76f51;
  --spark: #ff4d6d;
}
.stApp {
  font-family: "Outfit", sans-serif;
  background:
    radial-gradient(1200px 600px at 10% -10%, rgba(63,111,74,0.18), transparent 55%),
    radial-gradient(900px 500px at 90% 0%, rgba(201,162,74,0.12), transparent 50%),
    linear-gradient(180deg, #dfe8dc 0%, #e4ebe3 40%, #edf2ea 100%);
}
#MainMenu, footer { visibility: hidden; height: 0; }
header { visibility: hidden; height: 0; }
.block-container { padding-top: 0.35rem !important; padding-bottom: 2.5rem; max-width: 1400px; }
h1, h2, h3, .hero-brand, .chapter-title, .stat-plain, .sm-title, .sm-beat-val {
  font-family: "Fraunces", Georgia, serif;
  letter-spacing: -0.03em;
  color: var(--canopy);
}
.hero {
  position: relative; min-height: min(86vh, 760px);
  width: 100vw; margin-left: calc(50% - 50vw); margin-right: calc(50% - 50vw);
  overflow: hidden; color: #f4f7f2;
  animation: heroIn 1.1s ease-out both;
}
.hero-media {
  position: absolute; inset: 0;
  background-size: cover; background-position: center 40%;
  transform: scale(1.04);
  animation: heroDrift 28s ease-in-out infinite alternate;
}
.hero-veil {
  position: absolute; inset: 0;
  background:
    linear-gradient(180deg, rgba(14,28,18,0.22) 0%, rgba(14,28,18,0.38) 45%, rgba(14,28,18,0.82) 100%),
    radial-gradient(circle at 50% 70%, rgba(201,162,74,0.14), transparent 55%);
}
.hero-copy {
  position: relative; z-index: 2;
  min-height: min(86vh, 760px);
  display: flex; flex-direction: column; justify-content: flex-end;
  padding: 2.5rem clamp(1.2rem, 5vw, 4.5rem) 3rem;
  max-width: 52rem;
}
.hero-brand {
  font-size: clamp(3rem, 8vw, 5.6rem); font-weight: 700; line-height: 0.95;
  margin: 0 0 0.85rem; color: #f7faf5;
  text-shadow: 0 2px 28px rgba(0,0,0,0.35);
  animation: riseIn 1.2s 0.15s ease-out both;
}
.hero-line {
  font-family: "Outfit", sans-serif; font-weight: 300;
  font-size: clamp(1.2rem, 2.2vw, 1.55rem);
  line-height: 1.35; max-width: 28rem; margin: 0 0 0.55rem; color: #e8f0e4;
  animation: riseIn 1.2s 0.35s ease-out both;
}
.hero-sub {
  font-size: 0.95rem; letter-spacing: 0.08em; text-transform: uppercase;
  color: rgba(232,240,228,0.78); margin: 0;
  animation: riseIn 1.2s 0.5s ease-out both;
}
.hero-ripple-mark {
  position: absolute; z-index: 2; top: 18%; right: 12%;
  width: 120px; height: 120px; border-radius: 50%;
  background:
    radial-gradient(circle, rgba(247,250,245,0.95) 0 10%, transparent 11%),
    radial-gradient(circle, transparent 0 28%, rgba(201,162,74,0.55) 29% 31%, transparent 32%),
    radial-gradient(circle, transparent 0 48%, rgba(247,250,245,0.35) 49% 51%, transparent 52%),
    radial-gradient(circle, transparent 0 68%, rgba(247,250,245,0.2) 69% 71%, transparent 72%);
  animation: pulseMark 4.5s ease-out infinite;
  opacity: 0.85;
}
@keyframes heroIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes heroDrift { from { transform: scale(1.04) translateY(0); } to { transform: scale(1.08) translateY(-1.5%); } }
@keyframes riseIn { from { opacity: 0; transform: translateY(18px); } to { opacity: 1; transform: none; } }
@keyframes pulseMark {
  0% { transform: scale(0.92); opacity: 0.55; }
  40% { opacity: 0.9; }
  100% { transform: scale(1.12); opacity: 0.35; }
}
.caveat, .oknote {
  background: transparent; border: none; border-left: 2px solid var(--dawn);
  padding: 0.35rem 0 0.35rem 0.9rem; margin: 0.4rem 0 1rem;
  font-size: 0.95rem; color: var(--muted); font-weight: 300; max-width: 46rem;
}
.oknote { border-left-color: var(--moss); color: var(--canopy); }
.legend-row { display:flex; align-items:center; gap:0.55rem; margin:0.28rem 0; font-size:0.88rem; color:var(--ink); font-weight:300; }
.swatch { width:14px; height:14px; border-radius:2px; border:1px solid rgba(0,0,0,0.12); flex:0 0 14px; }
.filter-help { font-size:0.84rem; color:var(--muted); margin:0 0 0.55rem; font-weight:300; }
.map-sentence-bar {
  margin: 0 0 0.55rem;
  padding: 0.65rem 0.9rem 0.75rem;
  background: rgba(248,245,238,0.92);
  border: 1px solid rgba(30,58,40,0.12);
  border-radius: 0.55rem 0.2rem 0.65rem 0.25rem;
}
.map-sentence-bar .ms-kicker {
  font-family: "Outfit", sans-serif;
  font-size: 0.66rem; font-weight: 600;
  letter-spacing: 0.1em; text-transform: uppercase;
  color: #6b7280; margin: 0 0 0.2rem;
}
.map-sentence-bar .ms-line {
  font-family: "Fraunces", Georgia, serif;
  font-size: 1.15rem; font-weight: 550; font-style: italic;
  line-height: 1.25; color: var(--canopy); margin: 0;
}
.media-stage {
  width: 100%;
  border-radius: 1.15rem 0.35rem 1.05rem 0.45rem;
  border: 1px solid rgba(30,58,40,0.12);
  box-shadow: 0 18px 40px rgba(30,40,30,0.12);
  overflow: hidden;
  background: #e8e4dc;
}
.media-stage .craft-wrap {
  min-height: min(62vh, 680px);
}
.map-thesis-bar {
  margin: 0 0 0.65rem;
  padding: 0.85rem 1rem 0.9rem;
  border-radius: 14px;
  background: linear-gradient(180deg, rgba(252,250,246,0.98), rgba(244,240,232,0.96));
  border: 1px solid rgba(30,58,40,0.12);
  box-shadow: 0 8px 22px rgba(30,40,30,0.06);
}
.map-thesis-bar .mt-kicker {
  font-size: 0.62rem; letter-spacing: 0.12em; text-transform: uppercase;
  color: #78716c; margin: 0 0 0.3rem; font-weight: 700;
}
.map-thesis-bar .mt-line {
  font-family: "Fraunces", Georgia, serif;
  font-size: 1.12rem; font-weight: 550; font-style: italic;
  line-height: 1.32; color: var(--canopy); margin: 0 0 0.7rem;
}
.map-thesis-bar .mt-legend {
  display: flex; flex-wrap: wrap; gap: 0.55rem 1rem;
}
.map-thesis-bar .mt-leg-item {
  display: flex; align-items: center; gap: 0.4rem;
  font-size: 0.82rem; color: #3f4a40; font-weight: 450;
}
.map-thesis-bar .mt-swatch {
  width: 0.95rem; height: 0.95rem; border-radius: 3px;
  flex: 0 0 auto; border: 1px solid rgba(30,58,40,0.16);
  box-shadow: inset 0 0 0 1px rgba(255,255,255,0.25);
}
.explore-toggle {
  display: flex; align-items: center; gap: 0.55rem;
  padding: 0.35rem 0;
  border-bottom: 1px solid rgba(30,58,40,0.08);
  font-size: 0.92rem; color: var(--ink);
}
/* Keep Streamlit checkboxes readable inside narrow narrative column */
div[data-testid="stExpander"] label p {
  white-space: normal !important;
  overflow-wrap: anywhere;
  line-height: 1.3 !important;
}
.palette-key { display:grid; gap:0.4rem; margin:0.3rem 0 0.7rem; font-size:0.82rem; color:var(--muted); font-weight:300; }
.palette-chip {
  display:flex; gap:0.55rem; align-items:flex-start;
  padding:0.35rem 0; border:none; background:transparent;
  border-bottom: 1px solid rgba(30,58,40,0.08);
}
.palette-bar { width:4px; min-height:2rem; border-radius:1px; flex:0 0 4px; }
.vision {
  margin: 1.1rem 0 0.3rem; padding: 0.9rem 0 0;
  border-top: 1px solid rgba(30,58,40,0.14);
  max-width: 36rem;
}
.vision h3 { margin: 0 0 0.35rem; font-size: 1.35rem; }
.vision p { color: var(--muted); font-weight: 300; line-height: 1.55; font-size: 1.05rem; margin: 0; }
.leaflet-container { background: #d9e2d6 !important; }

.block-container { padding-left: 1.25rem !important; padding-right: 1.25rem !important; }
.sm-progress { display: flex; gap: 0.5rem; align-items: center; margin: 0 0 0.65rem; }
.sm-dot {
  width: 8px; height: 8px; border-radius: 60% 40% 55% 45%;
  background: rgba(30,58,40,0.18);
}
.sm-dot.on {
  background: var(--ember);
  box-shadow: 0 0 0 3px rgba(231,111,81,0.16);
  transform: scale(1.2);
}
.sm-kicker {
  font-size: 0.7rem; letter-spacing: 0.16em; text-transform: uppercase;
  color: var(--muted); margin: 0 0 0.2rem; font-weight: 500;
}
.sm-title {
  font-size: clamp(1.7rem, 2.8vw, 2.35rem);
  font-weight: 700; line-height: 1.05; color: var(--canopy);
  margin: 0 0 0.25rem;
  font-style: italic;
}
.sm-title-rule {
  width: 3.5rem; height: 2px; margin: 0 0 0.7rem;
  border-radius: 999px;
  background: linear-gradient(90deg, var(--ember), rgba(255,183,3,0.2));
}
.sm-body {
  font-size: 1.02rem; font-weight: 300; line-height: 1.48;
  color: var(--ink); margin: 0 0 0.65rem; max-width: 26rem;
}
.sm-beat {
  display: grid;
  grid-template-columns: 4.8rem 1fr;
  column-gap: 0.7rem;
  align-items: baseline;
  padding: 0.35rem 0;
  border-top: 1px solid rgba(30,58,40,0.1);
}
.sm-beat-val {
  font-size: 1.25rem; font-weight: 650; color: var(--canopy);
  margin: 0; line-height: 1.1;
}
.sm-beat-label {
  font-size: 0.9rem; color: var(--muted); font-weight: 300;
  margin: 0; line-height: 1.3;
}
.sm-footer-note {
  font-size: 0.82rem; color: var(--muted); font-weight: 300;
  margin: 0.55rem 0 0.35rem; line-height: 1.4; max-width: 26rem;
  padding: 0.45rem 0.65rem;
  border-radius: 1rem 0.35rem 0.9rem 0.45rem;
  background: rgba(231,111,81,0.08);
}
.sm-flourish {
  font-family: "Fraunces", serif; font-style: italic; font-size: 0.88rem;
  color: var(--ember); margin: 0 0 0.25rem;
}
.evidence-row {
  display: flex; flex-wrap: wrap; gap: 0.35rem;
  margin: 0.15rem 0 0.65rem;
}
.evidence-chip {
  font-size: 0.62rem; letter-spacing: 0.08em; text-transform: uppercase;
  font-weight: 600; color: var(--canopy);
  background: rgba(63,111,74,0.12);
  border: 1px solid rgba(30,58,40,0.14);
  border-radius: 999px; padding: 0.22rem 0.55rem;
}
.evidence-chip.modelled { background: rgba(201,162,74,0.16); color: #7a5a12; }
.evidence-chip.published { background: rgba(59,109,140,0.12); color: #2a4f66; }
.evidence-chip.calculated { background: rgba(231,111,81,0.12); color: #8a3a28; }
.placeholder-card {
  margin: 0.75rem 0 0.2rem; padding: 0.85rem 0.95rem;
  border-radius: 1.1rem 0.4rem 1rem 0.55rem;
  background: linear-gradient(160deg, rgba(248,245,238,0.95), rgba(231,236,228,0.9));
  border: 1px solid rgba(30,58,40,0.12);
  max-width: 26rem;
}
.placeholder-card h4 {
  font-family: "Fraunces", serif; font-style: italic;
  margin: 0 0 0.35rem; font-size: 1.05rem; color: var(--canopy);
}
.placeholder-card p {
  margin: 0 0 0.4rem; font-size: 0.9rem; font-weight: 300;
  color: var(--muted); line-height: 1.45;
}
.placeholder-card .tag {
  font-size: 0.62rem; letter-spacing: 0.1em; text-transform: uppercase;
  color: #7a5a12; font-weight: 600;
}
.hero-tagline {
  font-family: "Fraunces", serif; font-style: italic;
  font-size: clamp(1.05rem, 1.8vw, 1.35rem);
  color: rgba(255, 230, 170, 0.95); margin: 0 0 0.65rem;
  max-width: 28rem; line-height: 1.3;
  animation: riseIn 1.2s 0.28s ease-out both;
}
.sm-map-sentence {
  font-family: "Fraunces", serif; font-style: italic;
  font-size: 0.95rem; color: var(--canopy);
  margin: 0.15rem 0 0.55rem; line-height: 1.35; max-width: 26rem;
}
/* Style the Folium iframe directly — do NOT wrap it in empty HTML shells */
iframe[title="streamlit_folium.st_folium"],
iframe[srcdoc] {
  border-radius: 1.35rem 0.45rem 1.2rem 0.65rem !important;
  border: 1px solid rgba(30,58,40,0.14) !important;
}
div[data-testid="stVerticalBlockBorderWrapper"]:has(iframe) {
  border: none !important;
}
.sm-nav {
  display: flex; gap: 0.65rem; align-items: center;
  margin-top: 0.75rem; padding-top: 0.65rem;
  border-top: 1px solid rgba(30,58,40,0.1);
}
.stButton > button {
  background: transparent !important; color: var(--canopy) !important;
  border: 1px solid rgba(30,58,40,0.28) !important;
  border-radius: 999px !important; padding: 0.45rem 1.1rem !important;
  font-family: "Outfit", sans-serif !important; font-weight: 500 !important;
  letter-spacing: 0.02em !important; min-height: 2.4rem !important;
}
.stButton > button:hover {
  background: rgba(30,58,40,0.06) !important;
  border-color: var(--canopy) !important;
}
.stButton > button[kind="primary"],
.stButton > button[data-testid="baseButton-primary"] {
  background: var(--canopy) !important; color: #f4f7f2 !important;
  border-color: var(--canopy) !important;
}
</style>
"""
    )


def _family_opacity(family: str, emphasis: str, base: float) -> float:
    """Boost the active story colour language; soften the other."""
    if emphasis == "Balanced":
        return base
    if emphasis == "Land influence":
        if family == "land":
            return min(0.92, base * 1.25)
        if family == "species":
            return base * 0.35
        if family == "setting":
            return base * 0.7
    if emphasis == "Species refuge":
        if family == "species":
            return min(0.85, base * 1.2)
        if family == "land":
            return base * 0.4
        if family == "setting":
            return base * 0.55
    return base


@st.cache_data(show_spinner="Loading map layer…")
def load_layer(layer: str, simplify_m: float | None = 20.0) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(MASTER_GPKG, layer=layer)
    if gdf.empty:
        return gdf
    gdf = gdf.to_crs(4326)
    if simplify_m and str(gdf.geom_type.iloc[0]) != "Point":
        tol = simplify_m / 111_000.0
        gdf = gdf.copy()
        gdf["geometry"] = gdf.geometry.simplify(tol, preserve_topology=True)
    return gdf


def _dissolve_story(gdf: gpd.GeoDataFrame, simplify_m: float = 80.0) -> gpd.GeoDataFrame:
    """
    One soft silhouette for story maps.
    CRITICAL: simplify parts BEFORE union. Buffer morphs on full-detail multipolygons
    can take minutes and freeze Streamlit.
    """
    if gdf is None or gdf.empty:
        return gpd.GeoDataFrame(geometry=[], crs=4326)
    g = gdf.to_crs(CRS_M) if gdf.crs and str(gdf.crs) != CRS_M else gdf.copy()
    try:
        g = g[g.geometry.notna() & ~g.geometry.is_empty].copy()
        if g.empty:
            return gpd.GeoDataFrame(geometry=[], crs=4326)
        # Pre-simplify — turns a multi-minute union into <1s
        g["geometry"] = g.geometry.simplify(max(simplify_m, 80.0), preserve_topology=True)
        geom = unary_union(list(g.geometry))
        if geom is None or geom.is_empty:
            return gpd.GeoDataFrame(geometry=[], crs=4326)
        soft = geom.simplify(max(simplify_m * 1.5, 120.0), preserve_topology=True)
        out = gpd.GeoDataFrame({"hover_line": ["On this map"], "geometry": [soft]}, crs=CRS_M)
        return out.to_crs(4326)
    except Exception:
        return gpd.GeoDataFrame(geometry=[], crs=4326)


def _story_patches(
    gdf: gpd.GeoDataFrame,
    *,
    tip: str,
    simplify_m: float = 40.0,
    max_parts: int = 180,
) -> gpd.GeoDataFrame:
    """
    Keep separate habitat islands readable (the fragmentation story).
    Simplify + cap count so Folium stays fast — do NOT dissolve to one blob.
    """
    if gdf is None or gdf.empty:
        return gpd.GeoDataFrame(geometry=[], crs=4326)
    g = gdf.to_crs(CRS_M) if gdf.crs and str(gdf.crs) != CRS_M else gdf.copy()
    g = g[g.geometry.notna() & ~g.geometry.is_empty].copy()
    if g.empty:
        return gpd.GeoDataFrame(geometry=[], crs=4326)
    g["geometry"] = g.geometry.simplify(simplify_m, preserve_topology=True)
    g["__area"] = g.geometry.area
    g = g.sort_values("__area", ascending=False).drop(columns="__area")
    if len(g) > max_parts:
        g = g.head(max_parts)
    return _with_story_tip(g.to_crs(4326), tip)


def _near_reserve_mask(gdf: gpd.GeoDataFrame, reserve_union, metres: float) -> gpd.GeoDataFrame:
    """Keep features that intersect a buffer of the reserve (metric CRS)."""
    if gdf is None or gdf.empty:
        return gdf
    g = gdf.to_crs(CRS_M) if gdf.crs and str(gdf.crs) != CRS_M else gdf.copy()
    buf = reserve_union.buffer(metres)
    return g.loc[g.intersects(buf)].copy()


@st.cache_data(show_spinner="Preparing the story map…")
def story_layer_pack() -> dict[str, gpd.GeoDataFrame]:
    """
    Soft-paper story layers — silhouettes OK for teaching the idea.
    Do NOT use dissolved opportunity megablobs for Action/satellite decisions.
    """
    pack: dict[str, gpd.GeoDataFrame] = {}
    reserve = gpd.read_file(MASTER_GPKG, layer="robertson_nature_reserve")
    pack["reserve"] = _with_story_tip(
        reserve.to_crs(4326) if not reserve.empty else reserve,
        "Robertson Nature Reserve — the tiny protected seed",
    )

    # Past cover: one soft wash is fine on soft paper (MODELLED — not current canopy)
    try:
        preclear = gpd.read_file(MASTER_GPKG, layer="rainforest_preclear_modelled")
        pack["preclear"] = _with_story_tip(
            _dissolve_story(preclear, simplify_m=120),
            "MODELLED past rainforest — not what you see on satellite today",
        )
    except Exception:
        pack["preclear"] = gpd.GeoDataFrame(geometry=[], crs=4326)

    try:
        rf = gpd.read_file(MASTER_GPKG, layer="rainforest_extant")
        pack["rainforest"] = _story_patches(rf, tip="Mapped rainforest remnant (PCT)", simplify_m=45, max_parts=120)
    except Exception:
        pack["rainforest"] = gpd.GeoDataFrame(geometry=[], crs=4326)

    try:
        core = gpd.read_file(MASTER_GPKG, layer="core_habitat_patches")
        pack["core"] = _story_patches(
            core,
            tip="Habitat patch (rainforest + wet sclerophyll network)",
            simplify_m=50,
            max_parts=100,
        )
    except Exception:
        pack["core"] = gpd.GeoDataFrame(geometry=[], crs=4326)

    try:
        roads = gpd.read_file(MASTER_GPKG, layer="roads_barriers").to_crs(CRS_M)
        if not roads.empty and "barrier_class" in roads.columns:
            hi = roads.loc[roads["barrier_class"] == "high"].copy()
            hi["geometry"] = hi.geometry.simplify(60, preserve_topology=True)
            if len(hi) > 400:
                hi = hi.iloc[:400]
            pack["roads_high"] = _with_story_tip(hi.to_crs(4326), "Major road — can separate habitat")
        else:
            pack["roads_high"] = gpd.GeoDataFrame(geometry=[], crs=4326)
    except Exception:
        pack["roads_high"] = gpd.GeoDataFrame(geometry=[], crs=4326)

    try:
        hydro = gpd.read_file(MASTER_GPKG, layer="hydro_lines").to_crs(CRS_M)
        hydro["geometry"] = hydro.geometry.simplify(50, preserve_topology=True)
        if len(hydro) > 500:
            if "shape_length" in hydro.columns or "Shape_Length" in hydro.columns:
                col = "shape_length" if "shape_length" in hydro.columns else "Shape_Length"
                hydro = hydro.sort_values(col, ascending=False).head(500)
            else:
                hydro = hydro.iloc[:500]
        pack["hydro"] = _with_story_tip(hydro.to_crs(4326), "Creek / stream")
    except Exception:
        pack["hydro"] = gpd.GeoDataFrame(geometry=[], crs=4326)

    # Story mode: soft dissolved opportunity washes (teaching only — not site design)
    try:
        comps = gpd.read_file(MASTER_GPKG, layer="component_polygons").to_crs(CRS_M)
        tips = {
            "patch_gap_edge": "STORY WASH — cleared edges near habitat (whole landscape pattern)",
            "riparian_gap": "STORY WASH — cleared gaps along streams (whole landscape pattern)",
            "isolated_patch_context": "STORY WASH — near lonelier habitat patches",
            "on_public_land": "STORY WASH — public/Crown land context (broad)",
        }
        key_map = {
            "patch_gap_edge": "opp_edge",
            "riparian_gap": "opp_riparian",
            "isolated_patch_context": "opp_isolated",
            "on_public_land": "opp_public",
        }
        for comp, skey in key_map.items():
            sub = comps.loc[comps["component"] == comp] if not comps.empty else comps
            if sub.empty:
                pack[skey] = gpd.GeoDataFrame(geometry=[], crs=4326)
                continue
            soft = sub.copy()
            soft["geometry"] = soft.geometry.simplify(80, preserve_topology=True)
            pack[skey] = _with_story_tip(soft.to_crs(4326), tips[comp])
    except Exception:
        for skey in ("opp_edge", "opp_riparian", "opp_isolated", "opp_public"):
            pack[skey] = gpd.GeoDataFrame(geometry=[], crs=4326)

    return pack


@st.cache_data(show_spinner="Preparing satellite action layers…")
def action_layer_pack(near_m: float = 3500.0) -> dict[str, gpd.GeoDataFrame]:
    """
    Ground-checkable layers for Action / satellite view.

    - Keep reserve + remnant boundaries faithful (light simplify only)
    - Opportunity = individual 250 m candidate cells near the reserve
      (NOT the study-wide dissolved component megablobs)
    - Hide preclear (modelled history looks 'wrong' on today's imagery)
    """
    pack: dict[str, gpd.GeoDataFrame] = {}
    reserve = gpd.read_file(MASTER_GPKG, layer="robertson_nature_reserve").to_crs(CRS_M)
    ru = reserve.union_all() if hasattr(reserve, "union_all") else unary_union(list(reserve.geometry))
    pack["reserve"] = _with_story_tip(
        reserve.to_crs(4326),
        "Robertson Nature Reserve boundary (gazetted)",
    )
    # Never show modelled past cover on satellite — it overlays paddocks and looks false
    pack["preclear"] = gpd.GeoDataFrame(geometry=[], crs=4326)

    try:
        rf = gpd.read_file(MASTER_GPKG, layer="rainforest_extant").to_crs(CRS_M)
        rf = _near_reserve_mask(rf, ru, near_m * 1.4)
        rf["geometry"] = rf.geometry.simplify(8, preserve_topology=True)
        rf["__d"] = rf.geometry.centroid.distance(ru)
        rf = rf.sort_values("__d").drop(columns="__d")
        if len(rf) > 350:
            rf = rf.head(350)
        pack["rainforest"] = _with_story_tip(
            rf.to_crs(4326),
            "Mapped rainforest remnant — compare with canopy on the photo",
        )
    except Exception:
        pack["rainforest"] = gpd.GeoDataFrame(geometry=[], crs=4326)

    try:
        core = gpd.read_file(MASTER_GPKG, layer="core_habitat_patches").to_crs(CRS_M)
        core = _near_reserve_mask(core, ru, near_m * 1.4)
        core["geometry"] = core.geometry.simplify(10, preserve_topology=True)
        core["__d"] = core.geometry.centroid.distance(ru)
        core = core.sort_values("__d").drop(columns="__d")
        if len(core) > 220:
            core = core.head(220)
        pack["core"] = _with_story_tip(
            core.to_crs(4326),
            "Habitat network patch (rainforest + wet sclerophyll) — not rainforest-only",
        )
    except Exception:
        pack["core"] = gpd.GeoDataFrame(geometry=[], crs=4326)

    try:
        roads = gpd.read_file(MASTER_GPKG, layer="roads_barriers").to_crs(CRS_M)
        if not roads.empty and "barrier_class" in roads.columns:
            hi = roads.loc[roads["barrier_class"] == "high"].copy()
            hi = _near_reserve_mask(hi, ru, near_m * 1.2)
            hi["geometry"] = hi.geometry.simplify(15, preserve_topology=True)
            pack["roads_high"] = _with_story_tip(hi.to_crs(4326), "Major road")
        else:
            pack["roads_high"] = gpd.GeoDataFrame(geometry=[], crs=4326)
    except Exception:
        pack["roads_high"] = gpd.GeoDataFrame(geometry=[], crs=4326)

    try:
        hydro = gpd.read_file(MASTER_GPKG, layer="hydro_lines").to_crs(CRS_M)
        hydro = _near_reserve_mask(hydro, ru, near_m)
        hydro["geometry"] = hydro.geometry.simplify(12, preserve_topology=True)
        if len(hydro) > 400:
            hydro = hydro.head(400)
        pack["hydro"] = _with_story_tip(hydro.to_crs(4326), "Mapped stream line")
    except Exception:
        pack["hydro"] = gpd.GeoDataFrame(geometry=[], crs=4326)

    # Opportunity: real 250 m cells near the seed — actionable, checkable on imagery
    tips = {
        "patch_gap_edge": "250 m candidate cell — cleared edge next to habitat (check on ground)",
        "riparian_gap": "250 m candidate cell — cleared gap along a stream (check on ground)",
        "isolated_patch_context": "250 m cell near a lonelier habitat patch (check on ground)",
        "on_public_land": "250 m cell intersecting public/Crown land context (check tenure)",
    }
    key_map = {
        "patch_gap_edge": "opp_edge",
        "riparian_gap": "opp_riparian",
        "isolated_patch_context": "opp_isolated",
        "on_public_land": "opp_public",
    }
    try:
        grid = gpd.read_file(MASTER_GPKG, layer="analysis_grid_metrics").to_crs(CRS_M)
        grid["__d"] = grid.geometry.centroid.distance(ru)
        near = grid.loc[grid["__d"] <= near_m].copy()
        for col, skey in key_map.items():
            if col not in near.columns:
                pack[skey] = gpd.GeoDataFrame(geometry=[], crs=4326)
                continue
            cells = near.loc[near[col].fillna(False).astype(bool)].copy()
            # Prefer closest cells if still many
            if len(cells) > 180:
                cells = cells.sort_values("__d").head(180)
            cells = cells.drop(columns="__d", errors="ignore")
            pack[skey] = _with_story_tip(cells.to_crs(4326), tips[col])
    except Exception:
        for skey in key_map.values():
            pack[skey] = gpd.GeoDataFrame(geometry=[], crs=4326)

    return pack


@st.cache_data(show_spinner="Rendering terrain hillshade…")
def hillshade_overlay() -> dict | None:
    """Downsampled DEM hillshade as a data-URI ImageOverlay (cartographic underlay)."""
    if not DEM_PATH.is_file():
        return None
    with rasterio.open(DEM_PATH) as src:
        scale = max(src.width, src.height) / 960.0
        out_h = max(64, int(src.height / scale))
        out_w = max(64, int(src.width / scale))
        elev = src.read(1, out_shape=(out_h, out_w), resampling=Resampling.bilinear).astype("float64")
        nodata = src.nodata
        west, south, east, north = transform_bounds(src.crs, "EPSG:4326", *src.bounds)

    mask = np.isfinite(elev)
    if nodata is not None:
        mask &= elev != nodata
    if not mask.any():
        return None

    # Approximate cell size in metres for gradient (analysis DEM is metric CRS)
    with rasterio.open(DEM_PATH) as src:
        res_x = abs(src.transform.a) * (src.width / out_w)
        res_y = abs(src.transform.e) * (src.height / out_h)

    filled = elev.copy()
    filled[~mask] = float(np.nanmedian(elev[mask]))
    dy, dx = np.gradient(filled, res_y, res_x)
    slope = np.pi / 2.0 - np.arctan(np.hypot(dx, dy))
    aspect = np.arctan2(-dx, dy)
    az = np.deg2rad(315.0)
    alt = np.deg2rad(42.0)
    shade = np.sin(alt) * np.sin(slope) + np.cos(alt) * np.cos(slope) * np.cos(az - aspect)
    shade = np.clip((shade + 1.0) / 2.0, 0, 1)
    # Warm parchment hillshade (not pure grey) for map-art feel
    r = (shade * 228 + (1 - shade) * 120).astype(np.uint8)
    g = (shade * 222 + (1 - shade) * 112).astype(np.uint8)
    b = (shade * 208 + (1 - shade) * 96).astype(np.uint8)
    alpha = np.where(mask, 170, 0).astype(np.uint8)
    rgba = np.dstack([r, g, b, alpha])
    img = Image.fromarray(rgba, mode="RGBA")
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    return {
        "uri": uri,
        "bounds": [[south, west], [north, east]],
    }


@st.cache_data(show_spinner="Building elevation wash…")
def elevation_wash() -> gpd.GeoDataFrame:
    """Soft contour-like hypsometric bands from the 250 m analysis grid."""
    g = gpd.read_file(MASTER_GPKG, layer="analysis_grid_metrics")[["elev_m", "geometry"]].to_crs(CRS_M)
    g = g.dropna(subset=["elev_m"])
    if g.empty:
        return gpd.GeoDataFrame(columns=["band", "elev_mid", "geometry"], crs=4326)
    try:
        g["band"] = pd.qcut(g["elev_m"], q=5, duplicates="drop")
    except ValueError:
        g["band"] = pd.cut(g["elev_m"], bins=5)
    g["elev_mid"] = g["elev_m"]
    dissolved = g.dissolve(by="band", aggfunc={"elev_mid": "mean"}).reset_index()
    dissolved["band"] = dissolved["band"].astype(str)
    dissolved = _organicize_geoms(dissolved, grow_m=70, shrink_m=45, simplify_m=35)
    return dissolved.to_crs(4326)


@st.cache_data(show_spinner="Building ripple bands…")
def ripple_bands() -> gpd.GeoDataFrame:
    """Annular bands 0–0.5, 0.5–1, 1–2, 2–5 km from reserve edge."""
    reserve = gpd.read_file(MASTER_GPKG, layer="robertson_nature_reserve").to_crs(CRS_M)
    ru = unary_union(list(reserve.geometry))
    cuts = [0, 500, 1000, 2000, 5000]
    labels = ["0–0.5 km", "0.5–1 km", "1–2 km", "2–5 km"]
    rows = []
    for i, label in enumerate(labels):
        outer = ru.buffer(cuts[i + 1])
        inner = ru.buffer(cuts[i]) if cuts[i] > 0 else ru
        ring = outer.difference(inner)
        rows.append({"band": label, "order": i, "radius_m": cuts[i + 1], "geometry": ring})
    return gpd.GeoDataFrame(rows, crs=CRS_M).to_crs(4326)


@st.cache_data(show_spinner="Calculating influence metrics…")
def influence_metrics() -> dict:
    reserve = gpd.read_file(MASTER_GPKG, layer="robertson_nature_reserve").to_crs(CRS_M)
    study = gpd.read_file(MASTER_GPKG, layer="study_area").to_crs(CRS_M)
    rf = gpd.read_file(MASTER_GPKG, layer="rainforest_extant").to_crs(CRS_M)
    preclear = gpd.read_file(MASTER_GPKG, layer="rainforest_preclear_modelled").to_crs(CRS_M)
    core = gpd.read_file(MASTER_GPKG, layer="core_habitat_patches").to_crs(CRS_M)
    try:
        rf_patches = gpd.read_file(MASTER_GPKG, layer="rainforest_patches").to_crs(CRS_M)
        n_rf_patches = len(rf_patches)
    except Exception:
        n_rf_patches = len(core)
    grid = gpd.read_file(MASTER_GPKG, layer="analysis_grid_metrics").to_crs(CRS_M)
    cleared = gpd.read_file(MASTER_GPKG, layer="cleared_or_non_native").to_crs(CRS_M)
    ru = unary_union(list(reserve.geometry))

    rf_bands = {}
    for d in (500, 1000, 2000, 5000):
        clip = gpd.clip(rf, gpd.GeoDataFrame(geometry=[ru.buffer(d)], crs=CRS_M))
        rf_bands[d] = float(clip.geometry.area.sum() / 10000.0)

    g = grid.copy()
    if "dist_to_reserve_m" in g.columns:
        g["band"] = pd.cut(
            g["dist_to_reserve_m"],
            bins=[-0.1, 500, 1000, 2000, 5000, 1e9],
            labels=["Within 0.5 km", "0.5–1 km", "1–2 km", "2–5 km", "Beyond 5 km"],
        )
    rich = (
        g.groupby("band", observed=False)[["n_species", "n_records"]].mean().reset_index()
        if "n_species" in g.columns
        else pd.DataFrame()
    )
    opp = {}
    for col, label in [
        ("riparian_gap", "Cleared gaps along streams"),
        ("patch_gap_edge", "Cleared edges next to habitat"),
        ("isolated_patch_context", "Near isolated patches"),
        ("on_public_land", "Public / Crown land"),
    ]:
        if col in g.columns:
            opp[label] = int(g[col].fillna(False).astype(bool).sum())

    # Local (5 km / 3.5 km) metrics — what the Robertson story can honestly claim
    local_m = 5000.0
    local_buf = gpd.GeoDataFrame(geometry=[ru.buffer(local_m)], crs=CRS_M)
    rf_local = gpd.clip(rf, local_buf)
    pre_local = gpd.clip(preclear, local_buf)
    g_near = g.copy()
    if "dist_to_reserve_m" in g_near.columns:
        near_mask = g_near["dist_to_reserve_m"] <= 3500
    else:
        g_near["__d"] = g_near.geometry.centroid.distance(ru)
        near_mask = g_near["__d"] <= 3500
    opp_near = {}
    for col, label in [
        ("riparian_gap", "Cleared gaps along streams"),
        ("patch_gap_edge", "Cleared edges next to habitat"),
        ("isolated_patch_context", "Near isolated patches"),
        ("on_public_land", "Public / Crown land"),
    ]:
        if col in g.columns:
            opp_near[label] = int(g.loc[near_mask, col].fillna(False).astype(bool).sum())

    cent = unary_union(list(reserve.geometry)).centroid
    cent_wgs = gpd.GeoSeries([cent], crs=CRS_M).to_crs(4326).iloc[0]

    def _read_json(path: Path) -> dict:
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    profile = _read_json(PROFILE_JSON)
    wildlife = _read_json(WILDLIFE_JSON)
    gaps_sum = _read_json(GAPS_SUMMARY_JSON)
    parcel = _read_json(PARCEL_EXPLORER_JSON)
    habitat_sum = _read_json(HABITAT_SUMMARY_JSON)

    return {
        "reserve_ha": float(reserve.geometry.area.sum() / 10000.0),
        "study_km2": float(study.geometry.area.sum() / 1e6),
        # Study-wide totals (12.5 km AOI) — do not present as Yarrawa Brush alone
        "rf_ha": float(rf.geometry.area.sum() / 10000.0),
        "preclear_ha": float(preclear.geometry.area.sum() / 10000.0),
        # Local surrounds used by the StoryMap narrative
        "rf_ha_5km": float(rf_local.geometry.area.sum() / 10000.0),
        "preclear_ha_5km": float(pre_local.geometry.area.sum() / 10000.0),
        "cleared_ha": float(cleared.geometry.area.sum() / 10000.0),
        "rf_bands": rf_bands,
        "touches_core": int(core.get("touches_reserve", pd.Series(dtype=bool)).fillna(False).astype(bool).sum()),
        "core_near_1km": int((core.distance(ru) <= 1000).sum()),
        "core_patches": len(core),
        "rf_patches": n_rf_patches,
        "core_ha": float(core["area_ha"].sum()) if "area_ha" in core.columns else float(core.geometry.area.sum() / 10000),
        "richness_by_band": rich,
        "opportunity_cells": opp,
        "opportunity_cells_near": opp_near,
        "reserve_lat": float(cent_wgs.y),
        "reserve_lon": float(cent_wgs.x),
        "species_roster": threatened_species_roster(),
        "yarrawa_brush_ha_published": 2500.0,
        "life_summary": life_landscape_summary(),
        # Phase 1–5 story packages (living atlas JSON)
        "reserve_profile": profile,
        "species_cards": list(wildlife.get("meet_the_locals_cards") or []),
        "plant_story": wildlife.get("plant_story") or {},
        "habitat_gaps_n": int(gaps_sum.get("n_opportunities") or 0),
        "habitat_gaps_by_type": gaps_sum.get("by_type") or {},
        "opportunity_areas_n": int(parcel.get("count") or 0),
        "opportunity_areas_by_type": (
            pd.DataFrame(parcel.get("areas") or [])
            .get("opportunity_type", pd.Series(dtype=str))
            .value_counts()
            .to_dict()
            if parcel.get("areas")
            else {}
        ),
        "parcel_explorer_areas": list(parcel.get("areas") or []),
        "small_pieces_n": int(habitat_sum.get("small_pieces_n") or 0),
        "updated_profile_utc": profile.get("generated_at_utc"),
        "updated_wildlife_utc": wildlife.get("generated_at_utc"),
    }


@st.cache_data(show_spinner="Summarising forest life records…")
def life_landscape_summary(max_km: float = 5.0) -> dict:
    """
    Honest life stats near the reserve for the StoryMap.
    Counts public observations / listed taxa — not a viability model.
    """
    reserve = gpd.read_file(MASTER_GPKG, layer="robertson_nature_reserve").to_crs(CRS_M)
    rf = gpd.read_file(MASTER_GPKG, layer="rainforest_extant").to_crs(CRS_M)
    sp = gpd.read_file(MASTER_GPKG, layer="species_observations_clean").to_crs(CRS_M)
    ru = unary_union(list(reserve.geometry))
    buf = gpd.GeoDataFrame(geometry=[ru.buffer(max_km * 1000)], crs=CRS_M)
    rf_local = gpd.clip(rf, buf)
    near = sp.loc[sp.geometry.distance(ru) <= max_km * 1000].copy()
    thr = near.loc[near["is_threatened"].fillna(False)].copy()
    if "is_sensitive" in thr.columns:
        thr = thr.loc[~thr["is_sensitive"].fillna(False)]

    def _taxa(df: gpd.GeoDataFrame) -> int:
        if df.empty or "scientificName" not in df.columns:
            return 0
        return int(df["scientificName"].nunique())

    by_group = {}
    if not thr.empty and "taxon_group" in thr.columns:
        by_group = thr.groupby("taxon_group")["scientificName"].nunique().to_dict()

    obs_on_rf = 0
    if not near.empty and not rf_local.empty:
        try:
            joined = gpd.sjoin(near, rf_local[["geometry"]], how="inner", predicate="intersects")
            obs_on_rf = int(len(joined))
        except Exception:
            obs_on_rf = 0

    insects = near.loc[near.get("taxon_group", pd.Series(dtype=str)) == "Insecta"] if "taxon_group" in near.columns else near.head(0)

    return {
        "threatened_mammals": int(by_group.get("Mammalia", 0)),
        "threatened_birds": int(by_group.get("Aves", 0)),
        "threatened_flora": int(by_group.get("Flora", 0)),
        "threatened_taxa_total": _taxa(thr),
        "insect_taxa_5km": _taxa(insects),
        "insect_records_5km": int(len(insects)),
        "obs_on_rainforest_5km": obs_on_rf,
        "all_obs_5km": int(len(near)),
        "flora_obs_5km": int((near["taxon_group"] == "Flora").sum()) if "taxon_group" in near.columns else 0,
        "mammal_obs_5km": int((near["taxon_group"] == "Mammalia").sum()) if "taxon_group" in near.columns else 0,
        "bird_obs_5km": int((near["taxon_group"] == "Aves").sum()) if "taxon_group" in near.columns else 0,
    }


@st.cache_data(show_spinner="Building threatened species roster…")
def threatened_species_roster(max_km: float = 5.0) -> pd.DataFrame:
    """
    Named threatened taxa from public BioNet points within max_km of the reserve.
    Category 1–3 sensitive taxa were already excluded in Phase 3 cleaning.
    Coordinates are not plotted here — names + distance bands only.
    """
    sp = gpd.read_file(MASTER_GPKG, layer="species_observations_clean").to_crs(CRS_M)
    reserve = gpd.read_file(MASTER_GPKG, layer="robertson_nature_reserve").to_crs(CRS_M)
    ru = unary_union(list(reserve.geometry))
    thr = sp.loc[sp["is_threatened"].fillna(False)].copy()
    if thr.empty:
        return pd.DataFrame()
    # Extra safety: never roster taxa still flagged sensitive
    if "is_sensitive" in thr.columns:
        thr = thr.loc[~thr["is_sensitive"].fillna(False)]
    thr["dist_m"] = thr.geometry.distance(ru)
    near = thr.loc[thr["dist_m"] <= max_km * 1000].copy()
    if near.empty:
        return pd.DataFrame()

    def _band(d: float) -> str:
        if d <= 500:
            return "Within 0.5 km"
        if d <= 1000:
            return "0.5–1 km"
        if d <= 2000:
            return "1–2 km"
        if d <= 5000:
            return "2–5 km"
        return "Beyond 5 km"

    near["closest_band"] = near["dist_m"].map(_band)
    rows = []
    for (sci, vern, group, status), sub in near.groupby(
        ["scientificName", "vernacularName", "taxon_group", "stateConservation"], dropna=False
    ):
        vern_s = str(vern) if pd.notna(vern) and str(vern).strip() else "—"
        sci_s = str(sci)
        rows.append(
            {
                "Common name": vern_s,
                "Scientific name": sci_s,
                "Group": str(group) if pd.notna(group) else "—",
                "NSW status": str(status) if pd.notna(status) else "—",
                "Public records (within 5 km)": int(len(sub)),
                "Closest to reserve": sub.loc[sub["dist_m"].idxmin(), "closest_band"],
                "Years": f"{int(sub['year'].min()) if pd.notna(sub['year'].min()) else '—'}–"
                f"{int(sub['year'].max()) if pd.notna(sub['year'].max()) else '—'}",
                "Why this landscape matters": species_why_text(sci_s, vern_s, str(group)),
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values("Public records (within 5 km)", ascending=False).reset_index(drop=True)


def bounds_of(*gdfs: gpd.GeoDataFrame) -> list:
    xs, ys = [], []
    for gdf in gdfs:
        if gdf is None or gdf.empty:
            continue
        minx, miny, maxx, maxy = gdf.total_bounds
        xs.extend([minx, maxx])
        ys.extend([miny, maxy])
    if not xs:
        return [[-34.65, 150.50], [-34.50, 150.70]]
    return [[min(ys), min(xs)], [max(ys), max(xs)]]


def fit_bounds_for_recipe(fit_mode: str) -> list:
    """Chapter framing: close/near/context on the reserve; aoi = full study window."""
    study = load_layer("study_area", 30)
    if fit_mode == "aoi":
        return bounds_of(study)
    reserve = load_layer("robertson_nature_reserve", 4)
    if reserve.empty:
        return bounds_of(study)
    metres = {"close": 900, "near": 2400, "context": 5500}.get(fit_mode, 2400)
    try:
        buf = reserve.to_crs(CRS_M).copy()
        buf["geometry"] = buf.geometry.buffer(metres)
        return bounds_of(buf.to_crs(4326))
    except Exception:
        return bounds_of(reserve)


def make_map(fit, basemap_name: str = "Soft paper") -> folium.Map:
    """
    Build a Folium map. Satellite mode stays simple on purpose:
    streamlit_folium often breaks when LayerControl + multiple base layers are added.
    """
    cfg = BASEMAPS.get(basemap_name, BASEMAPS["Soft paper"])
    # prefer_canvas helps vector overlays; keep zoom/drag fully interactive
    m = folium.Map(
        tiles=None,
        control_scale=True,
        zoom_control=True,
        prefer_canvas=True,
    )
    is_satellite = basemap_name.startswith("Satellite")
    tile_kwargs = {
        "tiles": cfg["tiles"],
        "attr": cfg["attr"],
        "name": "Satellite" if is_satellite else basemap_name,
        "overlay": False,
        "control": False,  # no LayerControl — avoids blank / frozen Action maps
        "show": True,
    }
    if "subdomains" in cfg:
        tile_kwargs["subdomains"] = cfg["subdomains"]
    if "max_zoom" in cfg:
        tile_kwargs["max_zoom"] = cfg["max_zoom"]
    folium.TileLayer(**tile_kwargs).add_to(m)
    if labels := cfg.get("labels"):
        folium.TileLayer(
            tiles=labels,
            attr=cfg["attr"],
            name="Place labels",
            overlay=True,
            control=False,
            show=True,
            opacity=0.9,
            max_zoom=cfg.get("max_zoom", 19),
        ).add_to(m)
    m.fit_bounds(fit, padding=(28, 28))
    return m


class RipplePulse(MacroElement):
    """Animated pulse marker at the reserve — the visual 'ripple' icon on the map."""

    _template = Template(
        """
        {% macro script(this, kwargs) %}
        var pulseCss = `
        .ripple-pulse { position: relative; width: 22px; height: 22px; }
        .ripple-pulse .core {
          position:absolute; left:50%; top:50%; width:12px; height:12px;
          margin:-6px 0 0 -6px; border-radius:50%;
          background:#14532d; border:2px solid #fff;
          box-shadow:0 0 0 1px rgba(20,83,45,0.4);
          z-index:3;
        }
        .ripple-pulse .ring {
          position:absolute; left:50%; top:50%; width:12px; height:12px;
          margin:-6px 0 0 -6px; border-radius:50%;
          border:2px solid rgba(202,138,4,0.85);
          animation: rippleOut 2.4s ease-out infinite;
          z-index:1;
        }
        .ripple-pulse .ring.delay { animation-delay: 1.2s; border-color: rgba(22,101,52,0.55); }
        @keyframes rippleOut {
          0% { transform: scale(1); opacity: 0.9; }
          100% { transform: scale(4.8); opacity: 0; }
        }`;
        var style = document.createElement('style');
        style.innerHTML = pulseCss;
        document.head.appendChild(style);
        var icon = L.divIcon({
          className: '',
          html: '<div class="ripple-pulse"><div class="ring"></div><div class="ring delay"></div><div class="core"></div></div>',
          iconSize: [22,22],
          iconAnchor: [11,11]
        });
        L.marker([{{ this.lat }}, {{ this.lon }}], {icon: icon, interactive: true})
          .bindTooltip("The reserve — start of the story", {direction:'top'})
          .addTo({{ this._parent.get_name() }});
        {% endmacro %}
        """
    )

    def __init__(self, lat: float, lon: float):
        super().__init__()
        self._name = "RipplePulse"
        self.lat = lat
        self.lon = lon


class StoryMapChrome(MacroElement):
    """
    Compact on-map colour key only — long “what to notice” text lives above the map
    in Streamlit so the legend never eats the geography.
    """

    _template = Template(
        """
        {% macro script(this, kwargs) %}
        var chrome = L.control({position: 'bottomright'});
        chrome.onAdd = function(map) {
          var div = L.DomUtil.create('div', 'story-map-chrome');
          div.innerHTML = `
            <div style="
              max-width: 10.5rem;
              margin: 0 0.45rem 0.45rem 0;
              padding: 0.4rem 0.5rem 0.45rem;
              background: rgba(252,250,246,0.92);
              border: 1px solid rgba(30,58,40,0.14);
              border-radius: 8px;
              box-shadow: 0 4px 14px rgba(30,40,30,0.10);
              color: #1e3a28;
              pointer-events: none;
            ">
              <div style="
                font-family: Outfit, system-ui, sans-serif;
                font-size: 0.58rem;
                font-weight: 700;
                letter-spacing: 0.08em;
                text-transform: uppercase;
                color: #78716c;
                margin: 0 0 0.28rem;
              ">Key</div>
              <div style="display:grid;gap:0.22rem;">{{ this.legend_html }}</div>
            </div>`;
          L.DomEvent.disableClickPropagation(div);
          return div;
        };
        chrome.addTo({{ this._parent.get_name() }});
        {% endmacro %}
        """
    )

    def __init__(self, legend_html: str, sentence: str = ""):
        super().__init__()
        self._name = "StoryMapChrome"
        self.legend_html = legend_html
        # sentence kept for backward compatibility; no longer drawn on the map
        self.sentence = sentence or ""


class ReserveLabel(MacroElement):
    """Always-visible place name so novices can find the reserve without hovering."""

    _template = Template(
        """
        {% macro script(this, kwargs) %}
        var icon = L.divIcon({
          className: '',
          html: `
            <div style="
              transform: translate(-50%, -120%);
              white-space: nowrap;
              font-family: Outfit, system-ui, sans-serif;
              font-size: 11px;
              font-weight: 650;
              letter-spacing: 0.04em;
              color: #14532d;
              background: rgba(254,252,232,0.94);
              border: 1px solid rgba(20,83,45,0.28);
              border-radius: 999px;
              padding: 3px 9px;
              box-shadow: 0 4px 12px rgba(30,40,30,0.12);
            ">{{ this.label|e }}</div>`,
          iconSize: [0, 0],
          iconAnchor: [0, 0]
        });
        L.marker([{{ this.lat }}, {{ this.lon }}], {icon: icon, interactive: false})
          .addTo({{ this._parent.get_name() }});
        {% endmacro %}
        """
    )

    def __init__(self, lat: float, lon: float, label: str = "The reserve"):
        super().__init__()
        self._name = "ReserveLabel"
        self.lat = lat
        self.lon = lon
        self.label = label


def _attach_guide_fields(gdf: gpd.GeoDataFrame, layer_key: str) -> gpd.GeoDataFrame:
    """Add plain-language columns so every hover answers what / why."""
    guide = LAYER_GUIDE.get(layer_key, {})
    out = gdf.copy()
    out["what_is_this"] = guide.get("what", LAYERS.get(layer_key, {}).get("plain", ""))
    out["why_it_matters"] = guide.get("why", "")
    return out


_STORY_TIP_STYLE = (
    "background:rgba(248,245,238,0.96); border:1px solid rgba(30,58,40,0.14); "
    "border-radius:8px; padding:10px 12px; max-width:240px; white-space:normal; "
    "box-shadow:0 8px 22px rgba(30,40,30,0.14); "
    "font-family:Fraunces,Georgia,serif; font-size:14px; font-style:italic; "
    "line-height:1.3; color:#1e3a28;"
)


def _with_story_tip(gdf: gpd.GeoDataFrame, line) -> gpd.GeoDataFrame:
    """One short StoryMap-style hover line (not a GIS attribute table)."""
    out = gdf.copy()
    if callable(line):
        out["hover_line"] = out.apply(line, axis=1).astype(str)
    else:
        out["hover_line"] = str(line)
    return out


def add_poly(
    m,
    gdf,
    *,
    name,
    color,
    fill_opacity=0.35,
    weight=1.5,
    show=True,
    fields=None,
    aliases=None,
    tip_field: str | None = "hover_line",
    stroke_color: str | None = None,
    line_opacity: float | None = None,
):
    if gdf is None or gdf.empty:
        return
    tip = None
    keep: list[str] = []
    if tip_field and tip_field in gdf.columns:
        keep = [tip_field]
        tip = folium.GeoJsonTooltip(
            fields=[tip_field],
            aliases=[""],
            labels=False,
            sticky=False,
            style=_STORY_TIP_STYLE,
        )
    elif fields:
        keep = [c for c in fields if c in gdf.columns]
        if keep:
            tip = folium.GeoJsonTooltip(
                fields=keep,
                aliases=aliases or keep,
                sticky=False,
                style=_STORY_TIP_STYLE,
            )
    data = gdf[keep + ["geometry"]] if keep else gdf[["geometry"]]
    edge = stroke_color if stroke_color is not None else (color if fill_opacity < 0.55 else "#1c241c")
    opac = 0.0 if weight <= 0 else (line_opacity if line_opacity is not None else (0.85 if fill_opacity < 0.4 else 0.95))
    folium.GeoJson(
        data.__geo_interface__,
        name=name,
        show=show,
        style_function=lambda _f, c=color, fo=fill_opacity, w=weight, e=edge, o=opac: {
            "color": e,
            "fillColor": c,
            "fillOpacity": fo,
            "weight": w,
            "opacity": o,
        },
        tooltip=tip,
    ).add_to(m)


def add_lines(
    m,
    gdf,
    *,
    name,
    color,
    weight=2.0,
    show=True,
    fields=None,
    aliases=None,
    tip_field: str | None = "hover_line",
    dash_array: str | None = None,
    line_opacity: float = 0.92,
):
    if gdf is None or gdf.empty:
        return
    tip = None
    keep: list[str] = []
    if tip_field and tip_field in gdf.columns:
        keep = [tip_field]
        tip = folium.GeoJsonTooltip(
            fields=[tip_field],
            aliases=[""],
            labels=False,
            sticky=False,
            style=_STORY_TIP_STYLE,
        )
    elif fields:
        keep = [c for c in (fields or []) if c in gdf.columns]
        if keep:
            tip = folium.GeoJsonTooltip(
                fields=keep,
                aliases=aliases or keep,
                sticky=False,
                style=_STORY_TIP_STYLE,
            )
    data = gdf[keep + ["geometry"]] if keep else gdf[["geometry"]]
    folium.GeoJson(
        data.__geo_interface__,
        name=name,
        show=show,
        style_function=lambda _f, c=color, w=weight, d=dash_array, o=line_opacity: {
            "color": c,
            "weight": w,
            "opacity": o,
            "dashArray": d,
        },
        tooltip=tip,
    ).add_to(m)


def _story_legend_html(beats: list[tuple[str, str]]) -> str:
    rows = []
    for color, label in beats[:4]:
        rows.append(
            f'<div style="display:flex;align-items:center;gap:0.35rem;'
            f'font-family:Outfit,system-ui,sans-serif;font-size:0.68rem;line-height:1.15;color:#3f4a40;">'
            f'<span style="width:0.65rem;height:0.65rem;border-radius:2px;background:{color};'
            f'border:1px solid rgba(30,58,40,0.16);flex:0 0 auto;"></span>'
            f"<span>{label}</span></div>"
        )
    return "".join(rows)


def add_story_map_chrome(m, slide: dict, metrics: dict, *, imagery: bool = False) -> None:
    """Slim on-map colour key + reserve place-name."""
    if imagery:
        beats = list(slide.get("action_legend_beats") or slide.get("legend_beats") or [])
        beats = [(c, lab) for c, lab in beats if "was" not in lab.lower()]
        if not beats:
            beats = list(slide.get("legend_beats") or [])
    else:
        beats = list(slide.get("legend_beats") or [])
    # Prefer short labels on the map
    short = []
    for color, label in beats[:4]:
        short_lab = label.split("—")[0].split("(")[0].strip()
        if len(short_lab) > 28:
            short_lab = short_lab[:26] + "…"
        short.append((color, short_lab))
    m.add_child(StoryMapChrome(_story_legend_html(short)))
    lat = metrics.get("reserve_lat")
    lon = metrics.get("reserve_lon")
    if lat is not None and lon is not None:
        m.add_child(ReserveLabel(float(lat), float(lon), "The reserve"))


def _organicize_geoms(gdf: gpd.GeoDataFrame, grow_m: float = 90, shrink_m: float = 55, simplify_m: float = 28) -> gpd.GeoDataFrame:
    """Round blocky analysis cells into soft contour-like shapes (metric CRS in/out)."""
    if gdf is None or gdf.empty:
        return gdf
    out = gdf.copy()
    soft = []
    for geom in out.geometry:
        if geom is None or geom.is_empty:
            soft.append(geom)
            continue
        try:
            shaped = geom.buffer(grow_m).buffer(-shrink_m)
            if shaped.is_empty:
                shaped = geom.buffer(grow_m * 0.35)
            soft.append(shaped.simplify(simplify_m, preserve_topology=True))
        except Exception:
            soft.append(geom)
    out["geometry"] = soft
    return out


@st.cache_data(show_spinner=False)
def load_story_package() -> dict:
    if not STORY_PACKAGE.is_file():
        return {}
    try:
        return json.loads(STORY_PACKAGE.read_text(encoding="utf-8"))
    except Exception:
        return {}


@st.cache_data(show_spinner=False)
def load_neighbours_season() -> pd.DataFrame:
    if not NEIGHBOURS_SEASON_CSV.is_file():
        return pd.DataFrame()
    return pd.read_csv(NEIGHBOURS_SEASON_CSV)


@st.cache_data(show_spinner=False)
def load_greenness_summary() -> pd.DataFrame:
    if not GREENNESS_SUMMARY_CSV.is_file():
        return pd.DataFrame()
    return pd.read_csv(GREENNESS_SUMMARY_CSV)



@st.cache_data(show_spinner="Building listed-species hexes…")
def _threat_cells_near(near_m: float = 5000.0) -> gpd.GeoDataFrame:
    """
    Public aggregated threatened-species grid cells near the reserve.
    Analysis CRS EPSG:7856. Never raw observation points.
    """
    reserve = gpd.read_file(MASTER_GPKG, layer="robertson_nature_reserve").to_crs(CRS_M)
    ru = unary_union(list(reserve.geometry))
    if LIVING_GPKG.is_file():
        try:
            g = gpd.read_file(LIVING_GPKG, layer="threatened_species_living").to_crs(CRS_M)
        except Exception:
            g = gpd.read_file(MASTER_GPKG, layer="threatened_species_aggregated").to_crs(CRS_M)
    else:
        g = gpd.read_file(MASTER_GPKG, layer="threatened_species_aggregated").to_crs(CRS_M)
    if g.empty:
        return gpd.GeoDataFrame(geometry=[], crs=CRS_M)
    g = g.copy()
    g["threat_n_species"] = pd.to_numeric(g.get("threat_n_species"), errors="coerce").fillna(0)
    g["threat_n_records"] = pd.to_numeric(g.get("threat_n_records"), errors="coerce").fillna(0)
    g = g.loc[g["threat_n_species"] > 0].copy()
    if g.empty:
        return g
    g["__d"] = g.geometry.centroid.distance(ru)
    return g.loc[g["__d"] <= near_m].drop(columns="__d", errors="ignore")


def _hexagon(cx: float, cy: float, radius: float):
    """Flat-top hexagon centred on (cx, cy); radius = centre-to-vertex (metres)."""
    from shapely.geometry import Polygon

    angles = np.deg2rad(np.array([0, 60, 120, 180, 240, 300]))
    coords = [(cx + radius * np.cos(a), cy + radius * np.sin(a)) for a in angles]
    return Polygon(coords)


@st.cache_data(show_spinner="Building listed-species hexes…")
def threat_hex_layer(near_m: float = 5000.0, hex_m: float = 450.0) -> gpd.GeoDataFrame:
    """
    Hexagonal intensity surface for listed species near the reserve.

    GIS concept: re-bin public 250 m threat aggregates into ~450 m hexes so the map
    reads as intensity, not melted organic blooms. Still aggregated — not dens/pins.
    """
    cells = _threat_cells_near(near_m)
    empty_cols = ["hex_id", "n_species", "n_records", "intensity", "intensity_class", "hover_line", "geometry"]
    if cells.empty:
        return gpd.GeoDataFrame(columns=empty_cols, crs=4326)

    pts = cells.copy()
    pts["geometry"] = pts.geometry.centroid
    minx, miny, maxx, maxy = pts.total_bounds
    dx = hex_m * 1.5
    dy = hex_m * np.sqrt(3)
    rows = []
    row_i = 0
    y = miny - hex_m
    while y <= maxy + hex_m:
        x_off = (hex_m * 0.75) if (row_i % 2) else 0.0
        x = minx - hex_m + x_off
        col_i = 0
        while x <= maxx + hex_m:
            rows.append({"hex_id": f"h{row_i}_{col_i}", "geometry": _hexagon(x, y, hex_m)})
            x += dx
            col_i += 1
        y += dy
        row_i += 1
    hexes = gpd.GeoDataFrame(rows, crs=CRS_M)
    joined = gpd.sjoin(
        pts[["threat_n_species", "threat_n_records", "geometry"]],
        hexes,
        how="inner",
        predicate="within",
    )
    if joined.empty:
        return gpd.GeoDataFrame(columns=empty_cols, crs=4326)
    agg = joined.groupby("hex_id", as_index=False).agg(
        n_species=("threat_n_species", "max"),
        n_records=("threat_n_records", "sum"),
    )
    out = hexes.merge(agg, on="hex_id", how="inner")
    out["intensity"] = out["n_species"].astype(float) + np.log1p(out["n_records"].astype(float))
    # Fixed breaks — qcut collapses when many hexes share low counts
    out["intensity_class"] = pd.cut(
        out["intensity"],
        bins=[-np.inf, 2.0, 3.5, 6.0, np.inf],
        labels=["Lower", "Moderate", "Higher", "Highest"],
    ).astype(str)
    out["hover_line"] = out.apply(
        lambda r: (
            f"{r['intensity_class']} intensity · ~{int(r['n_species'])} listed taxa · "
            f"~{int(r['n_records'])} public records (aggregated hex — not a den)"
        ),
        axis=1,
    )
    return out.to_crs(4326)


@st.cache_data(show_spinner=False)
def threat_heat_points(near_m: float = 5000.0) -> list[list[float]]:
    """HeatMap weights from aggregated cell centroids — not raw BioNet pins."""
    cells = _threat_cells_near(near_m)
    if cells.empty:
        return []
    wgs = cells.to_crs(4326)
    pts: list[list[float]] = []
    for _, row in wgs.iterrows():
        geom = row.geometry.centroid
        weight = float(max(row.get("threat_n_records") or 1, 1))
        pts.append([float(geom.y), float(geom.x), min(weight, 40.0)])
    return pts


@st.cache_data(show_spinner="Building listed-species hexes…")
def refuge_blooms() -> gpd.GeoDataFrame:
    """Compatibility shim — hex intensity classes for any legacy bloom callers."""
    hx = threat_hex_layer()
    if hx.empty:
        return gpd.GeoDataFrame(columns=["bloom", "geometry"], crs=4326)
    out = hx.rename(columns={"intensity_class": "bloom"}).copy()
    out["records_sum"] = out["n_records"]
    out["species_peak"] = out["n_species"]
    return out


def fire_hotspots_gdf() -> gpd.GeoDataFrame:
    if not LIVING_GPKG.is_file():
        return gpd.GeoDataFrame(columns=["title", "status", "source", "geometry"], crs=4326)
    try:
        g = gpd.read_file(LIVING_GPKG, layer="fire_incidents_living")
    except Exception:
        return gpd.GeoDataFrame(columns=["title", "status", "source", "geometry"], crs=4326)
    if g.empty:
        return g.to_crs(4326) if g.crs else gpd.GeoDataFrame(columns=["title", "status", "source", "geometry"], crs=4326)
    return g.to_crs(4326)


def add_fire_hotspots(m, *, name="Fire / hotspot watch", show=True) -> None:
    g = fire_hotspots_gdf()
    if g is None or g.empty:
        return
    fg = folium.FeatureGroup(name=name, show=show)
    for _, row in g.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        title = str(row.get("title") or "Hotspot")
        status = str(row.get("status") or "—")
        source = str(row.get("source") or "—")
        folium.CircleMarker(
            location=[geom.y, geom.x],
            radius=8,
            color="#7f1d1d",
            weight=2,
            fill=True,
            fill_color="#c1121f",
            fill_opacity=0.85,
            popup=folium.Popup(
                f"<b>{title}</b><br>Status: {status}<br>Source: {source}<br>"
                "<i>Caution signal — not reserve causation.</i>",
                max_width=260,
            ),
            tooltip=title,
        ).add_to(fg)
    fg.add_to(m)



def add_soft_refuge_heat(m, *, show: bool = True) -> None:
    """Folium heatmap underlay from aggregated threat-cell centroids (not raw pins)."""
    if not show:
        return
    try:
        from folium.plugins import HeatMap
    except Exception:
        return
    pts = threat_heat_points()
    if not pts:
        return
    HeatMap(
        pts,
        name="Listed-species heat",
        min_opacity=0.25,
        max_zoom=14,
        radius=22,
        blur=28,
        gradient={0.2: "#ffcdb2", 0.45: "#ff8a5b", 0.7: "#e76f51", 1.0: "#9d0208"},
    ).add_to(m)



def add_refuge_blooms(m, *, name="Listed-species hexes", show=True, fill_opacity=0.58, soft_heat: bool = False) -> None:
    """
    LIFE map symbology: hexagonal intensity + optional heatmap underlay.
    Replaces organic 'blooms' that misread as habitat polygons.
    """
    # Heat underlay + hex choropleth (replaces misleading organic blooms)
    add_soft_refuge_heat(m, show=show)

    hx = threat_hex_layer()
    if hx is None or hx.empty:
        return

    palette = {
        "Lower": "#ffcdb2",
        "Moderate": "#ffb4a2",
        "Higher": "#e76f51",
        "Highest": "#9d0208",
    }
    order = ["Lower", "Moderate", "Higher", "Highest"]
    # Also handle unexpected class labels
    classes = [c for c in order if c in set(hx["intensity_class"].astype(str))]
    extras = [c for c in hx["intensity_class"].astype(str).unique() if c not in classes]
    for intensity_class in classes + extras:
        sub = hx.loc[hx["intensity_class"].astype(str) == intensity_class]
        if sub.empty:
            continue
        color = palette.get(intensity_class, "#e76f51")
        opac = fill_opacity * (
            0.45
            if intensity_class == "Lower"
            else 0.6
            if intensity_class == "Moderate"
            else 0.72
            if intensity_class == "Higher"
            else 0.82
        )
        tip = sub.copy()
        if "hover_line" not in tip.columns:
            tip["hover_line"] = intensity_class
        folium.GeoJson(
            tip[["hover_line", "geometry"]].__geo_interface__,
            name=f"{name}: {intensity_class}",
            show=show,
            style_function=lambda _f, c=color, o=opac: {
                "fillColor": c,
                "color": "#7f1d1d",
                "weight": 0.8,
                "fillOpacity": o,
                "opacity": 0.75,
            },
            tooltip=folium.GeoJsonTooltip(fields=["hover_line"], aliases=[""]),
        ).add_to(m)


def add_elevation_wash(m, gdf: gpd.GeoDataFrame, show: bool = True, fill_opacity: float = 0.28) -> None:
    """Cool hypsometric tint — higher ground reads cooler / mistier."""
    if gdf is None or gdf.empty:
        return
    # Soft topo art: parchment low → cool mist high
    colours = ["#f3ebe0", "#d8c4a8", "#a8b5a0", "#7f9a9e", "#5c6b8a"]
    bands = list(gdf["band"].unique())
    # Sort by elev_mid if available
    if "elev_mid" in gdf.columns:
        order = gdf.groupby("band")["elev_mid"].mean().sort_values()
        bands = list(order.index)
    for i, band in enumerate(bands):
        sub = gdf.loc[gdf["band"] == band]
        color = colours[min(i, len(colours) - 1)]
        folium.GeoJson(
            sub[["band", "geometry"]].__geo_interface__,
            name=f"Elevation: {band}",
            show=show,
            style_function=lambda _f, c=color, o=fill_opacity: {
                "color": c,
                "fillColor": c,
                "fillOpacity": o,
                "weight": 0,
            },
            tooltip=folium.GeoJsonTooltip(
                fields=["band"],
                aliases=["Elevation class (what: similar height band from analysis grid)"],
                sticky=True,
            ),
        ).add_to(m)


def add_hillshade(m, show: bool = True, opacity: float = 0.55) -> None:
    data = hillshade_overlay()
    if not data:
        return
    folium.raster_layers.ImageOverlay(
        image=data["uri"],
        bounds=data["bounds"],
        opacity=opacity,
        name="Terrain hillshade",
        show=show,
        interactive=False,
        cross_origin=False,
        zindex=1,
    ).add_to(m)


def add_ripple_bands(m, bands: gpd.GeoDataFrame, show: bool = True) -> None:
    """Draw concentric influence bands — thin amber rings (ruler, not impact)."""
    # Fewer, quieter rings so they support the hero layer instead of competing
    palette = [
        ("0–0.5 km", "#1a3c2a", 0.10),
        ("0.5–1 km", "#3f6f4a", 0.07),
        ("1–2 km", "#d4a017", 0.06),
        ("2–5 km", "#a8a29e", 0.04),
    ]
    for label, color, opac in reversed(palette):
        sub = bands.loc[bands["band"] == label]
        if sub.empty:
            continue
        dash = "4 8" if label == "2–5 km" else None
        tip_sub = _with_story_tip(sub, f"{label} from the reserve — a ruler, not an impact radius")
        folium.GeoJson(
            tip_sub[["hover_line", "geometry"]].__geo_interface__,
            name=f"Ripple: {label}",
            show=show,
            style_function=lambda _f, c=color, o=opac, d=dash: {
                "color": c,
                "fillColor": c,
                "fillOpacity": o,
                "weight": 1.15,
                "dashArray": d,
            },
            tooltip=folium.GeoJsonTooltip(
                fields=["hover_line"],
                aliases=[""],
                labels=False,
                sticky=False,
                style=_STORY_TIP_STYLE,
            ),
        ).add_to(m)


def plain_stat(col, value: str, label: str) -> None:
    col.markdown(
        f'<div class="stat-plain">{value}</div><div class="stat-label">{label}</div>',
        unsafe_allow_html=True,
    )


def render_flow() -> None:
    parts = []
    for i, step in enumerate(FLOW_STEPS):
        cls = "flow-step" if i == 0 else "flow-step soft"
        parts.append(f'<span class="{cls}">{step}</span>')
        if i < len(FLOW_STEPS) - 1:
            parts.append('<span class="flow-arrow">→</span>')
    st.markdown(f'<div class="flow">{"".join(parts)}</div>', unsafe_allow_html=True)


def render_acknowledgement(compact: bool = False) -> None:
    """
    Final page only: Acknowledgement of Country, then data-source credits.
    Full-width — not a leftover map panel.
    """
    del compact
    st.markdown(
        '<p style="margin:0.2rem 0 0.85rem;font-size:0.72rem;letter-spacing:0.12em;'
        'text-transform:uppercase;font-weight:700;color:#5c6b5e;">Respect</p>',
        unsafe_allow_html=True,
    )

    photo = acknowledgement_photo_b64()
    left, right = st.columns([0.48, 0.52], gap="large")
    with left:
        if photo:
            st.markdown(
                f'<div style="border-radius:0.9rem;overflow:hidden;border:1px solid rgba(30,58,40,0.14);'
                f'margin:0 0 0.65rem;max-height:420px;">'
                f'<img src="{photo}" alt="Country acknowledgement artwork" '
                f'style="width:100%;height:420px;object-fit:cover;object-position:center;display:block;"/>'
                f"</div>",
                unsafe_allow_html=True,
            )
            st.caption(
                "Artwork shared for this Acknowledgement of Country page. "
                "Replace with a licensed local work and artist credit when available."
            )
        st.markdown(
            f'<div style="padding:1.05rem 1.15rem;background:rgba(30,58,40,0.07);'
            f'border:1px solid rgba(30,58,40,0.14);border-radius:0.85rem;">'
            f'<p style="margin:0 0 0.4rem;font-size:0.7rem;letter-spacing:0.12em;text-transform:uppercase;'
            f'color:#14532d;font-weight:700;">Acknowledgement of Country</p>'
            f'<p style="margin:0;color:#2c382e;font-size:1.08rem;line-height:1.6;font-weight:350;">'
            f"{ACKNOWLEDGEMENT_OF_COUNTRY}</p>"
            f'<p style="margin:0.75rem 0 0;color:#5c6b5e;font-size:0.9rem;line-height:1.45;">'
            f"Any future care for rainforest around Robertson should sit alongside that continuing "
            f"connection to Country.</p></div>",
            unsafe_allow_html=True,
        )

    with right:
        st.markdown(
            '<p style="margin:0 0 0.35rem;font-size:0.7rem;letter-spacing:0.12em;text-transform:uppercase;'
            'font-weight:700;color:#5c6b5e;">Data sources used in this story</p>',
            unsafe_allow_html=True,
        )
        st.caption(
            "These public providers underpin the maps and wildlife evidence. "
            "Logos are for credit only — not endorsement."
        )
        cols = st.columns(2)
        for i, src in enumerate(DATA_SOURCE_CREDITS):
            with cols[i % 2]:
                uri = logo_data_uri(src["file"])
                if uri:
                    st.markdown(
                        f'<div style="margin:0.35rem 0 0.55rem;padding:0.65rem 0.75rem;background:#fff;'
                        f'border:1px solid rgba(30,58,40,0.1);border-radius:0.65rem;min-height:5.2rem;">'
                        f'<img src="{uri}" alt="{src["name"]}" '
                        f'style="height:52px;width:auto;max-width:100%;object-fit:contain;display:block;'
                        f'margin:0 0 0.4rem;background:#fff;"/>'
                        f'<p style="margin:0;font-size:0.82rem;color:#2c382e;font-weight:600;">{src["name"]}</p>'
                        f'<p style="margin:0;font-size:0.74rem;color:#5c6b5e;">{src["used_for"]}</p></div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f'<div style="margin:0.35rem 0 0.55rem;padding:0.6rem 0.7rem;background:rgba(255,255,255,0.6);'
                        f'border:1px solid rgba(30,58,40,0.1);border-radius:0.65rem;">'
                        f'<p style="margin:0;font-size:0.85rem;color:#2c382e;font-weight:600;">{src["name"]}</p>'
                        f'<p style="margin:0;font-size:0.74rem;color:#5c6b5e;">{src["used_for"]}</p></div>',
                        unsafe_allow_html=True,
                    )


def render_land_care_photo(work: dict) -> None:
    """Illustrative photo for the selected land-care work type."""
    fname = work.get("photo") or ""
    b64 = land_care_photo_b64(fname) if fname else ""
    if not b64:
        return
    caption = work.get("photo_caption") or work.get("title") or "Illustrative care example"
    st.markdown(
        f'<div style="margin-top:0.75rem;border-radius:0.85rem;overflow:hidden;'
        f'border:1px solid rgba(30,58,40,0.14);">'
        f'<img src="data:image/jpeg;base64,{b64}" alt="{work.get("title", "Land care")}" '
        f'style="width:100%;height:220px;object-fit:cover;display:block;"/>'
        f'<div style="padding:0.65rem 0.8rem;background:rgba(30,58,40,0.05);">'
        f'<p style="margin:0 0 0.2rem;font-size:0.68rem;letter-spacing:0.08em;text-transform:uppercase;'
        f'font-weight:700;color:{work.get("color", "#3f6f4a")};">What this care can look like</p>'
        f'<p style="margin:0;color:#2c382e;font-size:0.88rem;line-height:1.4;">{caption}</p>'
        f'<p style="margin:0.35rem 0 0;color:#78716c;font-size:0.75rem;">'
        f'Illustrative only — not a Robertson work site or a mandate for any parcel.</p>'
        f"</div></div>",
        unsafe_allow_html=True,
    )


def render_hero(metrics: dict) -> None:
    b64 = hero_image_b64()
    bg = (
        f"background-image:url('{b64}');"
        if b64
        else "background:linear-gradient(160deg,#1e3a28,#3f6f4a);"
    )
    st.markdown(
        f"""
        <section class="hero">
          <div class="hero-media" style="{bg}"></div>
          <div class="hero-veil"></div>
          <div class="hero-ripple-mark" aria-hidden="true"></div>
          <div class="hero-copy">
            <div class="hero-brand">{BRAND}</div>
            <p class="hero-line">{BRAND_SUBTITLE}</p>
            <p class="hero-tagline">{BRAND_TAGLINE}</p>
            <p class="hero-sub">Robertson Nature Reserve · {metrics["reserve_ha"]:.1f} hectares · Southern Highlands</p>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<p style="text-align:center;color:#4d5a4f;font-weight:300;margin:1rem auto 0.5rem;'
        f'max-width:36rem;font-size:1.05rem;line-height:1.45;">{BRAND_ALT}</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p style="text-align:center;color:#5c6b5e;font-size:0.95rem;max-width:42rem;margin:0.5rem auto 0.85rem;'
        'line-height:1.55;letter-spacing:0.03em;">'
        '<b style="color:#9a3412;">LOSS</b> &nbsp;→&nbsp; '
        '<b style="color:#14532d;">KEPT</b> &nbsp;→&nbsp; '
        '<b style="color:#0e7490;">LIFE</b> &nbsp;→&nbsp; '
        '<b style="color:#3f6f4a;">CARE</b> &nbsp;→&nbsp; '
        '<b style="color:#1e3a28;">RESPECT</b></p>',
        unsafe_allow_html=True,
    )


def render_story_header(chapter: str) -> None:
    st.markdown(
        f'<p class="atlas-kicker">Robertson · Southern Highlands</p>'
        f'<h2 class="chapter-title">{chapter}</h2>',
        unsafe_allow_html=True,
    )


def render_palette_key() -> None:
    bars = {
        "land": "linear-gradient(#3f6f4a,#d4a017)",
        "species": "linear-gradient(#ffcdb2,#9d0208)",
        "setting": "linear-gradient(#6b4f3a,#3b6d8c)",
        "barrier": "#9f1239",
        "cue": "#b45309",
    }
    chips = []
    for fam, (title, blurb) in FAMILY_LABELS.items():
        chips.append(
            f'<div class="palette-chip"><div class="palette-bar" style="background:{bars[fam]}"></div>'
            f"<div><b>{title}</b><br>{blurb}</div></div>"
        )
    st.markdown(f'<div class="palette-key">{"".join(chips)}</div>', unsafe_allow_html=True)


def render_legend(keys: list[str], legend_beats: list[tuple[str, str]] | None = None) -> None:
    """Story-beat legend (2–4 items) preferred over full GIS catalogue."""
    if legend_beats:
        blocks = [
            '<div style="margin:0.2rem 0 0.35rem;font-size:0.78rem;color:#78716c;'
            'text-transform:uppercase;letter-spacing:0.04em">On this map</div>'
        ]
        for color, label in legend_beats[:4]:
            blocks.append(
                f'<div class="legend-row"><span class="swatch" style="background:{color}"></span>'
                f"<span>{label}</span></div>"
            )
        st.markdown("".join(blocks), unsafe_allow_html=True)
        return

    order = ["land", "species", "setting", "barrier", "cue"]
    by_fam: dict[str, list[str]] = {f: [] for f in order}
    for k in keys:
        meta = LAYERS.get(k)
        if not meta:
            continue
        by_fam.setdefault(meta.get("family", "cue"), []).append(k)
    blocks = []
    for fam in order:
        keys_f = by_fam.get(fam) or []
        if not keys_f:
            continue
        title, _ = FAMILY_LABELS.get(fam, (fam, ""))
        blocks.append(
            f'<div style="margin:0.45rem 0 0.15rem;font-size:0.78rem;color:#78716c;'
            f'text-transform:uppercase;letter-spacing:0.04em">{title}</div>'
        )
        for k in keys_f:
            meta = LAYERS[k]
            blocks.append(
                f'<div class="legend-row"><span class="swatch" style="background:{meta["color"]}"></span>'
                f'<span><b>{meta["label"]}</b> — {meta["plain"]}</span></div>'
            )
    if blocks:
        st.markdown("".join(blocks), unsafe_allow_html=True)


# Short labels for the narrow narrative column (StoryMap craft drawer)
_TOGGLE_LABELS = {
    "reserve": "Protected patch",
    "rainforest": "Rainforest remnant",
    "preclear": "Historic cover",
    "cleared": "Cleared land",
    "threat_grid": "Listed-species hexes",
    "fire_hotspots": "Fire watch",
    "core": "Habitat patches",
    "roads_high": "Stronger roads",
    "roads_med": "Moderate roads",
    "basalt": "Volcanic ground",
    "hydro": "Streams",
    "riparian": "Riparian zone",
    "opp_edge": "Edges to plant",
    "opp_riparian": "Stream gaps",
    "opp_isolated": "Lonelier patches",
    "opp_public": "Public land",
    "ripple": "Distance rings",
    "hillshade": "Terrain shade",
    "elev": "Elevation wash",
    "study": "Study frame",
}


def layer_filter_ui(chapter: str) -> list[str]:
    """Optional layer toggles — same session key the evolving map reads."""
    recipe = CHAPTER_MAP_RECIPES.get(chapter, {})
    defaults = list(recipe.get("layers") or CHAPTER_LAYER_DEFAULTS.get(chapter, ["reserve", "ripple"]))
    options = defaults.copy()
    for extra in ("hillshade", "elev", "study", "ripple", "reserve"):
        if extra not in options and extra in LAYERS:
            options.append(extra)

    st.markdown(
        '<p class="filter-help">Story chooses the default layers. Adjust only if you want to explore.</p>',
        unsafe_allow_html=True,
    )
    selected = []
    state_key = f"layers_v3::{chapter}"
    if state_key not in st.session_state:
        st.session_state[state_key] = {k: (k in defaults) for k in options}

    for k in options:
        st.session_state[state_key].setdefault(k, k in defaults)

    # One checkbox per row — multi-column layout was crushing labels to single letters
    for key in options:
        meta = LAYERS[key]
        label = _TOGGLE_LABELS.get(key, meta["label"])
        checked = st.checkbox(
            label,
            value=st.session_state[state_key].get(key, key in defaults),
            key=f"cb_v2_{chapter}_{key}",
            help=meta["plain"],
        )
        st.session_state[state_key][key] = checked
        if checked:
            selected.append(key)

    c1, c2 = st.columns(2)
    if c1.button("Reset plate", key=f"rec_v2_{chapter}", use_container_width=True):
        for k in options:
            st.session_state[state_key][k] = k in defaults
        st.rerun()
    if c2.button("Reserve only", key=f"clr_v2_{chapter}", use_container_width=True):
        for k in options:
            st.session_state[state_key][k] = k == "reserve"
        st.rerun()
    return selected


def _role_opacity(key: str, fam: str, emphasis: str, base: float, hero: set[str], context: set[str]) -> float:
    """Hero loud, context ghosted, else family emphasis."""
    if key in hero:
        return min(0.92, max(base, 0.72) * 1.15)
    if key in context:
        return min(0.34, base * 0.55 if base > 0.2 else 0.26)
    return _family_opacity(fam, emphasis, base)


def paint_layers(
    m: folium.Map,
    enabled: list[str],
    metrics: dict,
    emphasis: str = "Balanced",
    *,
    hero: list[str] | None = None,
    context: list[str] | None = None,
    soft_heat: bool = False,
    story_fast: bool = True,
    imagery: bool = False,
) -> None:
    """Draw enabled catalogue layers (terrain under → themes → reserve → pulse)."""
    hero_set = set(hero or [])
    context_set = set(context or [])
    # Satellite / Action uses ground-checkable pack; Story uses soft silhouettes
    if story_fast and imagery:
        pack = action_layer_pack()
    elif story_fast:
        pack = story_layer_pack()
    else:
        pack = {}
    # On satellite, thicken strokes so overlays stay readable over imagery
    img_line_boost = 0.6 if imagery else 0.0
    order = [
        "hillshade",
        "elev",
        "study",
        "cleared",
        "preclear",
        "basalt",
        "riparian",
        "ripple",
        "rainforest",
        "core",
        "threat_grid",
        "fire_hotspots",
        "opp_public",
        "opp_isolated",
        "opp_riparian",
        "opp_edge",
        "hydro",
        "roads_med",
        "roads_high",
        "reserve",
    ]
    for key in order:
        if key not in enabled:
            continue
        meta = LAYERS[key]
        fam = meta.get("family", "cue")

        if key == "hillshade":
            add_hillshade(m, show=True, opacity=_role_opacity(key, fam, emphasis, 0.52, hero_set, context_set))
            continue
        if key == "elev":
            add_elevation_wash(
                m,
                elevation_wash(),
                show=True,
                fill_opacity=_role_opacity(key, fam, emphasis, 0.30, hero_set, context_set),
            )
            continue
        if key == "ripple":
            add_ripple_bands(m, ripple_bands(), show=True)
            continue
        if key == "threat_grid":
            add_refuge_blooms(
                m,
                name=meta["label"],
                fill_opacity=_role_opacity(key, fam, emphasis, 0.68, hero_set, context_set),
                soft_heat=soft_heat,
            )
            continue
        if key == "fire_hotspots":
            add_fire_hotspots(m, name=meta["label"], show=True)
            continue

        # Fast path: pre-simplified story silhouettes — polished, not GIS-default
        if story_fast and key in pack and key not in ("roads_med",):
            gdf = pack[key]
            if gdf is None or gdf.empty:
                continue
            if key == "reserve":
                # Cream / bright halo so the seed reads on soft paper and on imagery
                halo = "#fef9e7" if not imagery else "#fde68a"
                add_poly(
                    m,
                    gdf,
                    name="Reserve halo",
                    color=halo,
                    fill_opacity=0.0,
                    weight=(12 if key in hero_set else 8) + (2 if imagery else 0),
                    tip_field=None,
                    stroke_color=halo,
                    line_opacity=0.95,
                )
                add_poly(
                    m,
                    gdf,
                    name=meta["label"],
                    color="#14532d",
                    fill_opacity=(0.55 if imagery else 0.88) if key in hero_set else (0.12 if imagery else 0.22),
                    weight=2.8 if imagery else 2.4,
                    stroke_color="#fefce8" if imagery else "#0f3d22",
                )
                continue
            if key == "preclear":
                add_poly(
                    m,
                    gdf,
                    name=meta["label"],
                    color="#d4b896",
                    fill_opacity=0.28 if imagery else 0.42,
                    weight=0,
                    stroke_color="#d4b896",
                )
                continue
            if key == "rainforest":
                add_poly(
                    m,
                    gdf,
                    name=meta["label"],
                    color="#3f6f4a",
                    fill_opacity=(0.45 if key in hero_set else 0.32) if imagery else (0.62 if key in hero_set else 0.48),
                    weight=0.8 if imagery else 0.35,
                    stroke_color="#bbf7d0" if imagery else "#2f5d3a",
                    line_opacity=0.85 if imagery else 0.55,
                )
                continue
            if key == "core":
                add_poly(
                    m,
                    gdf,
                    name=meta["label"],
                    color="#2f5d3a",
                    fill_opacity=(0.40 if key in hero_set else 0.28) if imagery else (0.58 if key in hero_set else 0.40),
                    weight=0.9 if imagery else 0.45,
                    stroke_color="#86efac" if imagery else "#1f3f28",
                    line_opacity=0.8 if imagery else 0.5,
                )
                continue
            if key.startswith("opp_"):
                add_poly(
                    m,
                    gdf,
                    name=meta["label"],
                    color=meta["color"],
                    fill_opacity=((0.40 if key in hero_set else 0.28) if imagery else (0.55 if key in hero_set else 0.38)),
                    weight=(1.6 if key in hero_set else 1.0) + img_line_boost,
                    stroke_color=meta["color"],
                    line_opacity=0.9 if imagery else 0.75,
                )
                continue
            if key == "roads_high":
                add_lines(
                    m,
                    gdf,
                    name=meta["label"],
                    color="#fecaca" if imagery else "#b91c1c",
                    weight=(3.2 if key in hero_set else 2.4) + img_line_boost,
                    line_opacity=0.95,
                )
                continue
            if key == "hydro":
                add_lines(
                    m,
                    gdf,
                    name=meta["label"],
                    color="#7dd3fc" if imagery else "#4f7f98",
                    weight=(2.4 if key in hero_set else 1.8) + img_line_boost,
                    line_opacity=0.9,
                )
                continue
            add_poly(
                m,
                gdf,
                name=meta["label"],
                color=meta["color"],
                fill_opacity=_role_opacity(key, fam, emphasis, 0.5, hero_set, context_set),
                weight=1.0 if key in hero_set else 0.6,
                stroke_color=meta["color"],
            )
            continue

        if meta["kind"] == "opp":
            tip_name = {
                "opp_edge": "Cleared edge — a place to grow forest",
                "opp_riparian": "Stream gap — a place to heal",
                "opp_isolated": "Near a lonelier patch",
                "opp_public": "Public / Crown land",
            }.get(key, meta["label"])
            sub = pack.get(key) if story_fast else None
            if sub is None:
                comps = gpd.read_file(MASTER_GPKG, layer=meta["source"]).to_crs(CRS_M)
                sub = comps.loc[comps["component"] == meta["component"]] if not comps.empty else comps
                if not sub.empty:
                    dissolved = sub.dissolve(by="component", aggfunc="first").reset_index()
                    dissolved = _organicize_geoms(dissolved, grow_m=85, shrink_m=50, simplify_m=32)
                    sub = _with_story_tip(dissolved.to_crs(4326), tip_name)
            add_poly(
                m,
                sub,
                name=meta["label"],
                color=meta["color"],
                fill_opacity=_role_opacity(key, fam, emphasis, 0.68, hero_set, context_set),
                weight=1.8 if key in hero_set else 1.2,
            )
            continue
        if key in ("roads_high", "roads_med"):
            if story_fast and key == "roads_high" and key in pack:
                add_lines(
                    m,
                    pack[key],
                    name=meta["label"],
                    color=meta["color"],
                    weight=2.4,
                    show=True,
                )
                continue
            roads = load_layer(meta["source"], 12)
            if roads.empty or "barrier_class" not in roads.columns:
                continue
            cls = "high" if key == "roads_high" else "medium"
            roads = _attach_guide_fields(roads.loc[roads["barrier_class"] == cls], key)
            for c_src, c_dst in (
                ("roadnamebase", "road_name"),
                ("functionhierarchy", "road_class"),
                ("barrier_class", "barrier"),
            ):
                if c_src in roads.columns:
                    roads[c_dst] = roads[c_src].astype(str)
            roads = _with_story_tip(
                roads,
                lambda r: f"{r.get('road_name') or 'Road'} — a tear in the lattice"
                if cls == "high"
                else f"{r.get('road_name') or 'Road'} — moderate barrier",
            )
            wt = 2.4 if cls == "high" else 1.5
            if key in context_set:
                wt *= 0.85
            add_lines(
                m,
                roads,
                name=meta["label"],
                color=meta["color"],
                weight=wt,
            )
            continue
        if key == "riparian":
            rip = load_layer(meta["source"], 20)
            if "buffer_m" in rip.columns:
                rip = rip.loc[rip["buffer_m"] == 100]
            rip = _with_story_tip(rip, "Wet ground beside the stream")
            add_poly(
                m,
                rip,
                name=meta["label"],
                color=meta["color"],
                fill_opacity=_role_opacity(key, fam, emphasis, 0.22, hero_set, context_set),
                weight=0.35,
            )
            continue
        if key == "basalt":
            geo = load_layer(meta["source"], 20)
            if "is_basalt_or_volcanic" in geo.columns:
                geo = geo.loc[geo["is_basalt_or_volcanic"]]
            geo = _with_story_tip(
                geo,
                lambda r: f"{r.get('Unit_Name') or 'Volcanic ground'} — where rainforest can hold",
            )
            add_poly(
                m,
                geo,
                name=meta["label"],
                color=meta["color"],
                fill_opacity=_role_opacity(key, fam, emphasis, 0.42, hero_set, context_set),
                weight=0.6 if key in context_set else 1.0,
            )
            continue
        if key == "hydro":
            hydro = _with_story_tip(load_layer(meta["source"], 15), "A stream line — moisture and movement")
            add_lines(
                m,
                hydro,
                name=meta["label"],
                color=meta["color"],
                weight=2.2 if key in hero_set else 1.4,
            )
            continue

        base_opac = {
            "reserve": 0.88,
            "study": 0.03,
            "cleared": 0.28,
            "preclear": 0.20,
            "rainforest": 0.62,
            "core": 0.58,
        }.get(key, 0.4)
        opac = _role_opacity(key, fam, emphasis, base_opac, hero_set, context_set)

        gdf = load_layer(meta["source"], 8 if key == "reserve" else 22)
        gdf = _attach_guide_fields(gdf, key)

        if key == "reserve":
            for c_src, c_dst in (
                ("reserve_name", "name"),
                ("gaz_area_ha", "gazetted_ha"),
            ):
                if c_src in gdf.columns:
                    gdf[c_dst] = gdf[c_src]
            if "gazetted_ha" in gdf.columns:
                gdf["gazetted_ha"] = pd.to_numeric(gdf["gazetted_ha"], errors="coerce").round(1)
            gdf = _with_story_tip(
                gdf,
                lambda r: (
                    f"Robertson Nature Reserve"
                    + (f" · {r['gazetted_ha']:.1f} ha" if pd.notna(r.get("gazetted_ha")) else "")
                ),
            )
            # Outline always; solid fill only when the reserve is the hero idea
            fill = opac if key in hero_set else 0.0
            halo_w = 8 if key in hero_set else 5
            add_poly(m, gdf, name="Reserve halo", color="#fefce8", fill_opacity=0.0, weight=halo_w, tip_field=None)
            add_poly(
                m,
                gdf,
                name=meta["label"],
                color=meta["color"],
                fill_opacity=fill,
                weight=2.8 if key in hero_set else 2.2,
            )
            continue

        if key == "study":
            gdf = _with_story_tip(gdf, "The landscape we are watching with")
            add_poly(
                m,
                gdf,
                name=meta["label"],
                color=meta["color"],
                fill_opacity=opac,
                weight=1.4,
            )
            continue

        if key == "rainforest":
            # StoryMap silhouette — avoid a GIS spray of tiny outlined patches
            area_ha = float(pd.to_numeric(gdf.get("area_ha"), errors="coerce").fillna(0).sum()) if "area_ha" in gdf.columns else None
            tip = "Rainforest that still remains"
            if area_ha and area_ha > 0:
                tip = f"Rainforest that still remains · {area_ha:,.0f} ha"
            sil = gdf.to_crs(CRS_M).dissolve().reset_index(drop=True)
            grow, shrink, simp = (55, 32, 36) if key in hero_set else (45, 28, 40)
            sil = _organicize_geoms(sil, grow_m=grow, shrink_m=shrink, simplify_m=simp).to_crs(4326)
            sil = _with_story_tip(sil, tip)
            add_poly(
                m,
                sil,
                name=meta["label"],
                color=meta["color"],
                fill_opacity=opac,
                weight=0.55 if key in hero_set else 0.35,
            )
            continue

        if key == "core":
            if "area_ha" in gdf.columns:
                gdf["area_ha_shown"] = pd.to_numeric(gdf["area_ha"], errors="coerce").round(1)
            gdf = _with_story_tip(
                gdf,
                lambda r: (
                    "Habitat patch"
                    + (f" · {r['area_ha_shown']:.1f} ha" if pd.notna(r.get("area_ha_shown")) else "")
                    + (" · touches the reserve" if bool(r.get("touches_reserve")) else "")
                ),
            )
            add_poly(
                m,
                gdf,
                name=meta["label"],
                color=meta["color"],
                fill_opacity=opac,
                weight=1.0 if key in hero_set else 0.7,
            )
            continue

        # cleared / preclear / generic — soft story tips, light outlines
        tip = {
            "cleared": "Cleared land — waiting for healing",
            "preclear": "Modelled historic rainforest — a memory of wider forest",
        }.get(key, meta["label"])
        gdf = _with_story_tip(gdf, tip)
        add_poly(
            m,
            gdf,
            name=meta["label"],
            color=meta["color"],
            fill_opacity=opac,
            weight=0.35 if key in context_set else 0.8,
        )

    # Pulse only when the reserve is the hero idea — otherwise the place-name label is enough
    if story_fast and "reserve" in hero_set:
        m.add_child(RipplePulse(metrics["reserve_lat"], metrics["reserve_lon"]))
    elif not story_fast and ("reserve" in enabled or "ripple" in enabled):
        m.add_child(RipplePulse(metrics["reserve_lat"], metrics["reserve_lon"]))


def render_layer_decoder(enabled: list[str]) -> None:
    """Plain-language decode of every visible layer: what / why / hover / don't infer."""
    with st.expander("Reading the atlas — what each layer means", expanded=False):
        st.caption("What each polygon or line is, why it is on the map, and what hover can share.")
        rows = []
        for k in enabled:
            guide = LAYER_GUIDE.get(k)
            meta = LAYERS.get(k)
            if not guide or not meta:
                continue
            rows.append(
                {
                    "Layer": meta["label"],
                    "What the geometry is": guide["what"],
                    "Why it matters here": guide["why"],
                    "Shareable on hover": guide["hover"],
                    "Do not infer": guide["not"],
                }
            )
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def render_living_feeds_panel() -> None:
    """Twin Lakes living feeds: season neighbours, greenness, fire, evidence ladder."""
    pkg = load_story_package()
    feeds = pkg.get("feeds") or {}
    ladder = pkg.get("evidence_ladder") or {}
    generated = pkg.get("generated_at") or "not yet refreshed"

    st.markdown("### Twin Lakes — living feeds")
    st.caption(f"Package updated {generated}. Run `refresh-living-feeds.ps1` to refresh.")

    if ladder:
        st.markdown(
            f"""
            <div class="vision">
              <h3>Evidence ladder</h3>
              <p><b>Place:</b> {ladder.get('place_facts', '—')}</p>
              <p><b>Function:</b> {ladder.get('landscape_function', '—')}</p>
              <p><b>Living association:</b> {ladder.get('living_association', '—')}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    sp = feeds.get("species") or {}
    gn = feeds.get("greenness") or {}
    fr = feeds.get("fire") or {}

    c1, c2, c3 = st.columns(3)
    plain_stat(
        c1,
        str(sp.get("neighbours_season_n") or "—"),
        "Neighbours this season",
    )
    delta = gn.get("ndvi_delta")
    plain_stat(
        c2,
        f"+{delta:.3f}" if isinstance(delta, (int, float)) else "—",
        "Greenness remnant − cleared",
    )
    plain_stat(
        c3,
        str(fr.get("incidents_in_watch") if fr.get("status") == "ok" else "—"),
        "Hotspots in watch window",
    )

    with st.expander("Neighbours this season", expanded=True):
        if sp.get("why"):
            st.markdown(f'<div class="caveat">{sp["why"]}</div>', unsafe_allow_html=True)
        season = load_neighbours_season()
        if season.empty:
            st.info("No season roster yet — run the living feeds refresh.")
        else:
            top = sp.get("top_neighbour") or (season.iloc[0]["Common name"] if "Common name" in season.columns else "—")
            st.caption(f"Most recorded this window: **{top}**")
            st.dataframe(season, hide_index=True, use_container_width=True)

    with st.expander("Remnant vs cleared greenness", expanded=True):
        if gn.get("why"):
            st.markdown(f'<div class="caveat">{gn["why"]}</div>', unsafe_allow_html=True)
        summary = load_greenness_summary()
        chart_df = summary.loc[summary["class"].isin(["rainforest_remnant", "cleared_non_native"])].copy() if not summary.empty else summary
        if chart_df.empty:
            st.info("No greenness summary yet — run the living feeds refresh.")
        else:
            chart_df = chart_df.rename(columns={"class": "Land class", "mean_ndvi": "Mean NDVI"})
            chart_df["Land class"] = chart_df["Land class"].map(
                {
                    "rainforest_remnant": "Rainforest remnant",
                    "cleared_non_native": "Cleared / non-native",
                }
            )
            st.bar_chart(chart_df.set_index("Land class")["Mean NDVI"], height=220)
            if gn.get("scene_id"):
                st.caption(f"Scene: {gn.get('scene_id')} · cloud {gn.get('cloud_cover', '—')}%")

    with st.expander("Fire / hotspot pressure", expanded=False):
        if fr.get("status") != "ok":
            st.warning(fr.get("message") or "Fire feed not available yet.")
        else:
            if fr.get("why"):
                st.markdown(f'<div class="caveat">{fr["why"]}</div>', unsafe_allow_html=True)
            titles = fr.get("incident_titles") or []
            st.write(
                f"**{fr.get('incidents_in_watch', 0)}** hotspot(s) in the "
                f"{fr.get('watch_buffer_km', '—')} km watch window · source `{fr.get('source', '—')}`"
            )
            if titles:
                st.write("· " + " · ".join(str(t) for t in titles[:8]))
            notes = fr.get("notes") or []
            for note in notes:
                st.caption(str(note))


def render_species_panel(metrics: dict) -> None:
    """Named threatened taxa associated with the remnant landscape (not reserve causation)."""
    roster = metrics.get("species_roster")
    st.markdown("### Neighbours in the remnant")
    st.markdown(
        '<div class="caveat">These public records sit within 5 km of the reserve. They show the wider remnant '
        "is used by listed species — not that the reserve alone created every sighting. Survey effort also "
        "shapes where records appear.</div>",
        unsafe_allow_html=True,
    )
    if roster is None or (isinstance(roster, pd.DataFrame) and roster.empty):
        st.info("No public threatened species names available within 5 km after sensitivity filters.")
        return
    s1, s2, s3 = st.columns(3)
    plain_stat(s1, f"{len(roster)}", "Listed species (public names)")
    plain_stat(s2, f"{int(roster['Public records (within 5 km)'].sum())}", "Public records within 5 km")
    top = roster.iloc[0]["Common name"] if len(roster) else "—"
    plain_stat(s3, str(top), "Most recorded near reserve")
    st.dataframe(roster, hide_index=True, use_container_width=True)
    with st.expander("What can be shared on the map vs in this table?"):
        st.markdown(
            """
- **On the map (rose–copper blooms):** aggregated intensity only — never precise pins.
- **In this table:** common + scientific names for **public** threatened records (BioNet Category 1–3
  sensitive taxa were removed in data prep). We do **not** plot those name rows as precise pins here.
- **Never share:** reverse-engineered denatured locations, or raw sensitive coordinates.
- **Why column:** ecological association with remnant forest / edges / streams — a briefing cue, not a
  population viability model.
"""
        )


def render_life_at_stake_panel(metrics: dict) -> None:
    """Legacy deeper dig — prefer render_life_worth_panel for the StoryMap chapter."""
    render_life_worth_panel(metrics, placement="full")


def _life_guild_and_care(metrics: dict) -> tuple[str, str, dict]:
    """Shared guild selection + care-line for the LIFE chapter panels."""
    life = metrics.get("life_summary") or {}
    if "life_guild" not in st.session_state:
        st.session_state.life_guild = "Mammals"
    guild = st.session_state.life_guild
    hint_ids = GUILD_CARE_HINTS.get(guild, ["protect", "edge"])
    hint_titles = [
        LAND_MANAGEMENT_BY_ID[wid]["title"]
        for wid in hint_ids
        if wid in LAND_MANAGEMENT_BY_ID
    ]
    care_line = ", ".join(hint_titles[:3]) if hint_titles else "Protect living bush"
    return guild, care_line, life


def render_life_worth_stats(metrics: dict) -> None:
    """Compact listed-species counts for the left rail."""
    life = metrics.get("life_summary") or {}
    c1, c2 = st.columns(2)
    plain_stat(c1, str(life.get("threatened_mammals", "—")), "Listed mammals (5 km)")
    plain_stat(c2, str(life.get("threatened_birds", "—")), "Listed birds (5 km)")
    c3, c4 = st.columns(2)
    plain_stat(c3, str(life.get("threatened_flora", "—")), "Listed plants (5 km)")
    plain_stat(c4, f"{int(life.get('obs_on_rainforest_5km') or 0):,}", "Records on rainforest")


def render_life_worth_under_map(metrics: dict) -> None:
    """
    Fill the media column under the refuge map: guild chips, species cards, worth strip.
    Two-column cards use the wide space that used to sit empty beside a tall left stack.
    """
    guild, care_line, life = _life_guild_and_care(metrics)
    roster = metrics.get("species_roster")

    st.markdown(
        '<p style="margin:0.55rem 0 0.25rem;font-size:0.68rem;letter-spacing:0.1em;'
        'text-transform:uppercase;font-weight:700;color:#5c6b5e;">Who uses these pockets</p>',
        unsafe_allow_html=True,
    )
    st.caption("Choose mammals, birds, plants or insects. Names come from public records near Robertson.")

    guilds = ["Mammals", "Birds", "Plants", "Insects"]
    gcols = st.columns(4)
    for i, g in enumerate(guilds):
        with gcols[i]:
            on = st.session_state.life_guild == g
            if st.button(
                g,
                key=f"life_guild_map_{g}",
                use_container_width=True,
                type="primary" if on else "secondary",
            ):
                st.session_state.life_guild = g
                st.rerun()

    guild, care_line, life = _life_guild_and_care(metrics)

    if guild == "Insects":
        st.markdown(
            f'<div style="margin-top:0.55rem;padding:0.85rem 1rem;border-radius:0.75rem;'
            f'border-left:4px solid #c45c48;background:rgba(196,92,72,0.06);'
            f'border:1px solid rgba(30,58,40,0.1);border-left-width:4px;">'
            f'<p style="margin:0 0 0.35rem;font-weight:700;color:#9a3412;">Insects are hard to see in the records</p>'
            f'<p style="margin:0 0 0.35rem;color:#2c382e;font-size:0.92rem;line-height:1.4;">'
            f'Public lists show only about {int(life.get("insect_taxa_5km") or 0)} insect kinds '
            f'and {int(life.get("insect_records_5km") or 0)} records nearby. '
            f'That usually means people have looked less — not that insects are gone.</p>'
            f'<p style="margin:0;color:#5c6b5e;font-size:0.85rem;">'
            f'<b>How care helps:</b> {care_line}</p></div>',
            unsafe_allow_html=True,
        )
    else:
        rows: list[dict] = []
        if isinstance(roster, pd.DataFrame) and not roster.empty:
            group_col = "Group"
            if guild == "Mammals":
                mask = roster[group_col].astype(str).str.contains("Mammal", case=False, na=False)
            elif guild == "Birds":
                mask = roster[group_col].astype(str).str.contains("Aves|Bird", case=False, na=False)
            else:
                mask = roster[group_col].astype(str).str.contains("Flora|Plant", case=False, na=False)
            rows = roster.loc[mask].head(6).to_dict(orient="records")

        if not rows:
            st.info(f"No threatened {guild.lower()} names in the public list for this area yet.")
        else:
            # Two-column gallery fills the wide media column
            left_rows = rows[0::2]
            right_rows = rows[1::2]
            col_l, col_r = st.columns(2, gap="medium")

            def _card_html(r: dict) -> str:
                common = r.get("Common name") or "—"
                sci = r.get("Scientific name") or ""
                status = r.get("NSW status") or "—"
                needs = r.get("Why this landscape matters") or species_why_text(
                    str(sci), str(common), str(r.get("Group") or "")
                )
                return (
                    f'<div style="margin:0 0 0.65rem;padding:0.75rem 0.85rem;border-radius:0.65rem;'
                    f'background:rgba(30,58,40,0.045);border:1px solid rgba(30,58,40,0.1);min-height:7.5rem;">'
                    f'<p style="margin:0 0 0.2rem;font-weight:700;color:#1e3a28;font-size:0.98rem;">'
                    f'{common}</p>'
                    f'<p style="margin:0 0 0.35rem;color:#5c6b5e;font-size:0.8rem;">'
                    f'<i>{sci}</i> · {status}</p>'
                    f'<p style="margin:0 0 0.3rem;color:#2c382e;font-size:0.86rem;line-height:1.35;">'
                    f'<b>Needs:</b> {needs}</p>'
                    f'<p style="margin:0;color:#5c6b5e;font-size:0.8rem;">'
                    f'<b>Care that helps:</b> {care_line}</p></div>'
                )

            with col_l:
                st.markdown("".join(_card_html(r) for r in left_rows), unsafe_allow_html=True)
            with col_r:
                if right_rows:
                    st.markdown("".join(_card_html(r) for r in right_rows), unsafe_allow_html=True)

    # Simple care reminders under the wildlife cards
    w1, w2, w3, w4 = st.columns(4)
    beats = [
        (w1, "Protect bush", "Keep living forest standing"),
        (w2, "Close gaps", "Help wildlife move between patches"),
        (w3, "Plant creeks", "Cool water and link the valleys"),
        (w4, "Weed edges", "Let the understorey recover"),
    ]
    for col, title, blurb in beats:
        with col:
            st.markdown(
                f'<div style="padding:0.65rem 0.7rem;border-radius:0.6rem;background:rgba(30,58,40,0.06);'
                f'border:1px solid rgba(30,58,40,0.12);min-height:5.2rem;">'
                f'<p style="margin:0 0 0.25rem;font-size:0.72rem;letter-spacing:0.06em;text-transform:uppercase;'
                f'font-weight:700;color:#14532d;">{title}</p>'
                f'<p style="margin:0;color:#2c382e;font-size:0.84rem;line-height:1.35;">{blurb}</p></div>',
                unsafe_allow_html=True,
            )
    st.caption(LIFE_WORTH_INTEGRITY)


def render_life_worth_panel(metrics: dict, *, placement: str = "full") -> None:
    """Who uses these remnant pockets, and how careful land care can help."""
    if placement in {"rail", "full"}:
        st.markdown(
            '<p style="margin:0.55rem 0 0.35rem;font-size:0.68rem;letter-spacing:0.1em;'
            'text-transform:uppercase;font-weight:700;color:#5c6b5e;">Wildlife nearby</p>',
            unsafe_allow_html=True,
        )
        st.caption("From public wildlife records within about five kilometres of the reserve.")
        render_life_worth_stats(metrics)
    if placement in {"under_map", "full"}:
        render_life_worth_under_map(metrics)


def _story_slides(metrics: dict) -> list[dict]:
    """Bring Back the Brush V1 — 16 art-forward StoryMap chapters."""
    return build_story_slides(metrics)


def render_evidence_chips(tags: list[str]) -> None:
    if not tags:
        return
    chips = []
    for tag in tags:
        cls = {
            "MODELLED": "modelled",
            "PUBLISHED": "published",
            "CALCULATED": "calculated",
            "OBSERVED": "",
        }.get(tag, "")
        tip = EVIDENCE_HELP.get(tag, "")
        chips.append(
            f'<span class="evidence-chip {cls}" title="{tip}">{tag}</span>'
        )
    st.markdown(f'<div class="evidence-row">{"".join(chips)}</div>', unsafe_allow_html=True)


def render_extra_panel(extra: str | None, metrics: dict | None = None) -> None:
    """Art-forward panels — real metrics when available; honest placeholders otherwise."""
    if not extra:
        return
    metrics = metrics or {}

    if extra == "reserve_profile":
        p = metrics.get("reserve_profile") or {}
        r = p.get("reserve") or {}
        v = p.get("vegetation_in_reserve") or {}
        t = p.get("threatened_ecological_community") or {}
        updated = p.get("generated_at_utc") or "—"
        st.markdown(
            f'<div class="placeholder-card"><div class="tag">CALCULATED · updated {updated}</div>'
            f"<h4>Ecological profile (quiet metrics)</h4>"
            f"<p><b>{r.get('area_ha_calculated', '—')} ha</b> · {v.get('majority_pct_name', '—')}<br>"
            f"TEC: {t.get('tec_name', 'Robertson Rainforest')} — "
            f"{t.get('nsw_status', 'EEC')} / EPBC {t.get('epbc_status', 'CE')}</p></div>",
            unsafe_allow_html=True,
        )
        return

    if extra == "meet_the_locals":
        cards_list = metrics.get("species_cards") or []
        plant = metrics.get("plant_story") or {}
        st.markdown("##### Who uses this landscape?")
        st.caption("Cards from BioNet records near the reserve — not an invented species list.")
        if cards_list:
            for card in cards_list[:8]:
                st.markdown(
                    f"**{card.get('common_name')}** (*{card.get('scientific_name')}*) · "
                    f"{card.get('story_group')} · {card.get('conservation_status_nsw')}"
                )
                st.caption(card.get("why_fragmented_rainforest_matters", ""))
        if plant:
            st.markdown("##### It’s not just where animals live")
            st.write(plant.get("message", ""))
            chars = plant.get("rainforest_character_species_recorded") or []
            if chars:
                st.caption(
                    "Rainforest character species with local records: "
                    + ", ".join(
                        f"{c.get('vernacular_name') or c.get('scientific_name')}" for c in chars[:6]
                    )
                )
        return

    if extra in {"land_management", "land_care_where", "land_care_how"}:
        mode = "how" if extra in {"land_management", "land_care_how"} else "where"
        render_land_care_panel(metrics, mode=mode)
        return

    if extra in {"life_worth", "life"}:
        render_life_worth_panel(metrics)
        return

    if extra == "acknowledgement":
        render_acknowledgement()
        return

    if extra == "parcel_explorer":
        # Legacy path — land-care panel replaced the AREA_xxx picker
        render_land_care_panel(metrics, mode="where")
        return

    cards = {
        "illustrative": (
            "Illustrative journey",
            "This chapter uses habitat and gaps to explain fragmentation for everyday readers. "
            "It is not a tracked animal path.",
            "MODELLED storytelling",
        ),
        "community": (
            "Community conservation (coming next)",
            "Local groups such as Robertson Environment Protection Society, Bushcare, creek restoration, "
            "and citizen science belong here once locations and permissions are verified. "
            "We will not invent pins.",
            "Research backlog",
        ),
        "reserve_value": (
            "Why this place matters",
            "Protection turned a living remnant into a public promise beside town. "
            "Something real still stands — rare forest next to the village.",
            "KEPT",
        ),
        "kept_island": (
            "Why this place matters",
            "The reserve is a small protected piece in mostly cleared country, "
            "still near other rainforest. That is part of what makes Robertson special.",
            "KEPT",
        ),
        "one_hectare": (
            "Start with the short gaps",
            "A hectare of planting beside living bush or along a creek often helps more than a much larger "
            "planting stranded in open paddock.",
            "NEXT",
        ),
        "living_feeds": (
            "This story can grow",
            "As new wildlife sightings arrive, the living layers of the story can refresh.",
            "Living story",
        ),
        "village": (
            "Ideas for the village",
            "Creek planting, suitable street trees, school plantings, roadside links, and private "
            "stepping stones — ideas to talk about, not adopted council plans.",
            "Ideas only",
        ),
    }
    if extra in cards:
        title, body, tag = cards[extra]
        st.markdown(
            f'<div class="placeholder-card"><div class="tag">{tag}</div>'
            f"<h4>{title}</h4><p>{body}</p></div>",
            unsafe_allow_html=True,
        )


def render_progress(idx: int, n: int, slide: dict | None = None) -> None:
    """Always-visible story spine — one label per slide (STORY_SPINE / build_story_slides order)."""
    labels = list(STORY_SPINE)
    # Length must match STORY_SPINE (currently five chapters)
    colors = ["#9a3412", "#14532d", "#0e7490", "#3f6f4a", "#1e3a28"]
    cells = []
    for i, lab in enumerate(labels):
        col = colors[i] if i < len(colors) else "#1e3a28"
        on = i == idx
        opacity = "1" if on else "0.42"
        weight = "700" if on else "500"
        underline = f"box-shadow: inset 0 -3px 0 {col};" if on else ""
        cells.append(
            f'<span style="opacity:{opacity};font-weight:{weight};color:{col};'
            f'padding:0.15rem 0.4rem;{underline}letter-spacing:0.06em;font-size:0.88rem;">{lab}</span>'
        )
        if i < len(labels) - 1:
            cells.append('<span style="color:#8a968b;margin:0 0.05rem;">→</span>')
    st.markdown(
        f'<div style="display:flex;align-items:center;justify-content:center;flex-wrap:wrap;gap:0.1rem;'
        f'margin:0.2rem 0 0.85rem;">{"".join(cells)}</div>',
        unsafe_allow_html=True,
    )


def chapter_plate_path(chapter_key: str) -> Path | None:
    slug = CHAPTER_PLATE_SLUGS.get(chapter_key)
    if not slug:
        return None
    path = PLATES_DIR / f"{slug}.png"
    return path if path.is_file() else None


@st.cache_data(show_spinner=False)
def plate_image_b64(chapter_key: str, mtime_ns: int = 0) -> str | None:
    path = chapter_plate_path(chapter_key)
    if path is None:
        return None
    return base64.b64encode(path.read_bytes()).decode("ascii")


def load_plate_b64(chapter_key: str) -> str | None:
    path = chapter_plate_path(chapter_key)
    if path is None:
        return None
    return plate_image_b64(chapter_key, path.stat().st_mtime_ns)


def render_map_thesis_bar(slide: dict) -> None:
    """Colour key above the map — same language as the on-map chrome card."""
    sentence = slide.get("map_sentence") or ""
    beats = list(slide.get("legend_beats") or [])
    items = "".join(
        f'<span class="mt-leg-item">'
        f'<span class="mt-swatch" style="background:{color}"></span>{label}</span>'
        for color, label in beats[:4]
    )
    st.markdown(
        f'<div class="map-thesis-bar">'
        f'<p class="mt-kicker">Read this map</p>'
        f'<p class="mt-line">{sentence}</p>'
        f'<div class="mt-legend">{items}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )


def render_basemap_mode_toggle() -> str:
    """Story map vs satellite photo — for residents, not GIS technicians."""
    if "map_view_mode" not in st.session_state:
        st.session_state.map_view_mode = "Story"

    forced = st.session_state.pop("force_basemap", None)
    if forced and forced in BASEMAPS:
        st.caption(f"Map background: {forced}")
        return forced

    c1, c2 = st.columns(2)
    with c1:
        story_on = st.button(
            "Story map",
            use_container_width=True,
            type="primary" if st.session_state.map_view_mode == "Story" else "secondary",
            key="basemap_story_btn",
        )
    with c2:
        action_on = st.button(
            "Satellite photo",
            use_container_width=True,
            type="primary" if st.session_state.map_view_mode == "Action" else "secondary",
            key="basemap_action_btn",
        )
    if story_on:
        st.session_state.map_view_mode = "Story"
        st.rerun()
    if action_on:
        st.session_state.map_view_mode = "Action"
        st.rerun()

    if st.session_state.map_view_mode == "Action":
        st.caption(
            "Satellite view — compare the drawn remnants with real canopy around town. "
            "Always check on the ground before assuming a place is available to work."
        )
        return "Satellite + labels"
    st.caption("Story map — soft colours to follow the idea.")
    return "Soft paper"


def render_evolving_map(slide: dict, metrics: dict, basemap: str, chapter_idx: int) -> None:
    """
    One Folium map for the StoryMap journey.
    Basemap follows Story (soft paper) or Action (satellite) mode.
    """
    # Action view zooms nearer so 250 m cells are readable against imagery
    fit_key = slide.get("fit", "aoi")
    basemap_name = basemap if basemap in BASEMAPS else "Soft paper"
    imagery = basemap_name.startswith("Satellite")
    if imagery and fit_key in ("aoi", "context"):
        fit_key = "near"
    fit = fit_bounds_for_recipe(fit_key)
    fmap = make_map(fit, basemap_name=basemap_name)
    layers = list(slide.get("layers") or [])
    if "reserve" not in layers:
        layers = [*layers, "reserve"]
    # Modelled past forest looks false on today's satellite — omit in Action view
    if imagery:
        layers = [k for k in layers if k != "preclear"]
    paint_layers(
        fmap,
        layers,
        metrics,
        emphasis=slide.get("emphasis", "Balanced"),
        hero=list(slide.get("hero") or []),
        context=list(slide.get("context") or []),
        soft_heat=bool(slide.get("soft_heat")),
        story_fast=True,
        imagery=imagery,
    )
    add_story_map_chrome(fmap, slide, metrics, imagery=imagery)
    # Thesis lives above the map — keeps the Folium legend tiny
    notice = (
        slide.get("action_map_sentence")
        if imagery
        else slide.get("map_sentence")
    ) or ""
    if notice:
        st.caption(notice)
    st.markdown('<div class="media-stage craft-wrap">', unsafe_allow_html=True)
    # Key includes basemap + work type so Streamlit remounts when switching Story ↔ Action or care type
    safe_bm = basemap_name.replace(" ", "_").replace("+", "plus")
    work_id = slide.get("_work_id") or st.session_state.get("land_care_work_id", "")
    layer_sig = "-".join(layers[:6])
    map_h = int(slide.get("_map_height") or 620)
    st_folium(
        fmap,
        use_container_width=True,
        height=map_h,
        returned_objects=[],
        key=f"story_map_main_{chapter_idx}_{safe_bm}_{work_id}_{layer_sig}_{map_h}",
    )
    st.markdown("</div>", unsafe_allow_html=True)


def list_then_now_photo_pairs() -> list[tuple[Path, Path, str]]:
    """Deprecated — photo slots removed from the public StoryMap."""
    return []


@st.cache_data(show_spinner="Preparing then/now layers (5 km)…")
def then_now_local_pack(buffer_m: float = 5000.0) -> dict[str, gpd.GeoDataFrame]:
    """
    Clip pre-clear + extant rainforest to 5 km of the reserve so the slider
    matches the hectares told in the story (not the whole 12.5 km AOI).
    """
    reserve = gpd.read_file(MASTER_GPKG, layer="robertson_nature_reserve").to_crs(CRS_M)
    ru = unary_union(list(reserve.geometry))
    buf = gpd.GeoDataFrame(geometry=[ru.buffer(buffer_m)], crs=CRS_M)
    out: dict[str, gpd.GeoDataFrame] = {
        "reserve": _with_story_tip(reserve.to_crs(4326), "Robertson Nature Reserve"),
    }
    try:
        pre = gpd.clip(gpd.read_file(MASTER_GPKG, layer="rainforest_preclear_modelled").to_crs(CRS_M), buf)
        out["preclear"] = _with_story_tip(
            _dissolve_story(pre, simplify_m=100),
            "Modelled pre-clear rainforest within 5 km — not a Yarrawa Brush boundary",
        )
    except Exception:
        out["preclear"] = gpd.GeoDataFrame(geometry=[], crs=4326)
    try:
        rf = gpd.clip(gpd.read_file(MASTER_GPKG, layer="rainforest_extant").to_crs(CRS_M), buf)
        out["rainforest"] = _story_patches(
            rf,
            tip="Mapped rainforest within 5 km of the reserve",
            simplify_m=25,
            max_parts=220,
        )
    except Exception:
        out["rainforest"] = gpd.GeoDataFrame(geometry=[], crs=4326)
    return out


def render_then_now_slider(metrics: dict, basemap_name: str, chapter_idx: int) -> None:
    """
    Interactive then→now forest change within 5 km of the reserve.
    Slider controls map opacity only — hectare figures stay fixed and honest.
    """
    past_ha = float(metrics.get("preclear_ha_5km") or 0)
    now_ha = float(metrics.get("rf_ha_5km") or 0)
    brush = float(metrics.get("yarrawa_brush_ha_published") or 2500)
    lost_ha = max(past_ha - now_ha, 0)
    kept_pct = (100.0 * now_ha / past_ha) if past_ha > 0 else 0.0

    st.markdown("##### Reading the map")
    st.markdown(
        f"""
<div style="background:rgba(30,58,40,0.05);border:1px solid rgba(30,58,40,0.12);
border-radius:0.75rem;padding:0.85rem 1rem;margin:0.35rem 0 0.75rem;font-size:0.95rem;line-height:1.45;color:#2c382e;">
<p style="margin:0 0 0.55rem;"><b>Tan</b> is rainforest that models say once stood here
(about <b>{past_ha:,.0f} hectares</b> within five kilometres of today’s reserve).</p>
<p style="margin:0 0 0.55rem;"><b>Green</b> is rainforest still mapped today
(about <b>{now_ha:,.0f} hectares</b> in that same area).</p>
<p style="margin:0 0 0.55rem;"><b>What was lost nearby:</b> roughly <b>{lost_ha:,.0f} hectares</b>
— only about <b>{kept_pct:.0f}%</b> of that past cover remains.</p>
<p style="margin:0;font-size:0.88rem;color:#5c6b5e;">
These numbers match this map (a five-kilometre circle around the reserve).
Old accounts of the wider Yarrawa Brush speak of about <b>{brush:,.0f} hectares</b> —
that wider story is not drawn as a boundary here.</p>
</div>
""",
        unsafe_allow_html=True,
    )

    st.markdown(
        """
**What the slider does**

It only fades the colours so you can compare past and present.

- **Left** — more of the past (tan)
- **Right** — more of today (green)
- **Middle** — both together

It does **not** change the hectare figures above.
"""
    )
    t = st.slider(
        "Fade from past rainforest toward rainforest today",
        min_value=0,
        max_value=100,
        value=35,
        format="%d%% toward today",
        key=f"then_now_slider_{chapter_idx}",
        help="Drag toward today to see more green, or toward the past to see more tan. The hectare numbers stay fixed.",
    )
    past_share = 100 - t
    st.caption(
        f"Showing **{t}% toward today** and **{past_share}% toward the past**. "
        "The hectare figures above stay the same."
    )

    past_op = max(0.0, min(0.55, (100 - t) / 100 * 0.55))
    now_op = max(0.12, min(0.72, t / 100 * 0.72))

    # Soft paper for modelled past — satellite misleads when tan overlays paddocks
    fit = fit_bounds_for_recipe("context")
    fmap = make_map(fit, basemap_name="Soft paper")
    pack = then_now_local_pack()

    preclear = pack.get("preclear")
    rainforest = pack.get("rainforest")
    reserve = pack.get("reserve")
    if preclear is not None and not preclear.empty and past_op > 0.02:
        add_poly(
            fmap,
            preclear,
            name="Pre-clear rainforest (modelled, 5 km)",
            color="#d4b896",
            fill_opacity=past_op,
            weight=0,
            stroke_color="#d4b896",
        )
    if rainforest is not None and not rainforest.empty:
        add_poly(
            fmap,
            rainforest,
            name="Rainforest today (mapped, 5 km)",
            color="#3f6f4a",
            fill_opacity=now_op,
            weight=0.4,
            stroke_color="#2f5d3a",
            line_opacity=0.6,
        )
    if reserve is not None and not reserve.empty:
        add_poly(
            fmap,
            reserve,
            name="Reserve halo",
            color="#fef9e7",
            fill_opacity=0.0,
            weight=8,
            tip_field=None,
            stroke_color="#fef9e7",
        )
        add_poly(
            fmap,
            reserve,
            name="Robertson Nature Reserve",
            color="#14532d",
            fill_opacity=0.75,
            weight=2.4,
            stroke_color="#0f3d22",
        )
        if metrics.get("reserve_lat") is not None:
            fmap.add_child(ReserveLabel(float(metrics["reserve_lat"]), float(metrics["reserve_lon"]), "The reserve"))

    legend = _story_legend_html(
        [
            ("#d4b896", "Past"),
            ("#3f6f4a", "Today"),
            ("#14532d", "Reserve"),
        ]
    )
    fmap.add_child(
        StoryMapChrome(
            legend,
            f"Past ~{past_ha:,.0f} ha → today ~{now_ha:,.0f} ha nearby. The slider only fades the colours.",
        )
    )

    st.markdown('<div class="media-stage craft-wrap">', unsafe_allow_html=True)
    st_folium(
        fmap,
        use_container_width=True,
        height=580,
        returned_objects=[],
        key=f"then_now_map_{chapter_idx}_{t}",
    )
    st.markdown("</div>", unsafe_allow_html=True)


@st.cache_data(show_spinner="Preparing kept-island layers (1 km)…")
def kept_island_local_pack(buffer_m: float = 1000.0) -> dict:
    """
    Clip cleared + rainforest to 1 km of the reserve, and find the nearest
    non-touching rainforest patch for a short connector callout.
    Analysis CRS: EPSG:7856 (metres). Output geometries: WGS84 for Folium.
    """
    reserve = gpd.read_file(MASTER_GPKG, layer="robertson_nature_reserve").to_crs(CRS_M)
    ru = unary_union(list(reserve.geometry))
    buf = gpd.GeoDataFrame(geometry=[ru.buffer(buffer_m)], crs=CRS_M)
    ring = gpd.GeoDataFrame(
        {"hover_line": ["1 km study ring around the reserve"], "geometry": [ru.buffer(buffer_m).boundary]},
        crs=CRS_M,
    ).to_crs(4326)

    out: dict = {
        "reserve": _with_story_tip(reserve.to_crs(4326), "Robertson Nature Reserve — what we kept"),
        "ring": ring,
        "buffer_m": buffer_m,
        "neighbour": None,
        "connector": gpd.GeoDataFrame(geometry=[], crs=4326),
        "neighbour_poly": gpd.GeoDataFrame(geometry=[], crs=4326),
    }

    try:
        cleared = gpd.clip(
            gpd.read_file(MASTER_GPKG, layer="cleared_or_non_native").to_crs(CRS_M),
            buf,
        )
        out["cleared"] = _with_story_tip(
            _dissolve_story(cleared, simplify_m=90),
            "Cleared / non-native land within 1 km — the open landscape around the reserve",
        )
    except Exception:
        out["cleared"] = gpd.GeoDataFrame(geometry=[], crs=4326)

    try:
        rf = gpd.clip(
            gpd.read_file(MASTER_GPKG, layer="rainforest_extant").to_crs(CRS_M),
            buf,
        )
        out["rainforest"] = _story_patches(
            rf,
            tip="Mapped rainforest remnant within 1 km",
            simplify_m=18,
            max_parts=100,
        )
    except Exception:
        out["rainforest"] = gpd.GeoDataFrame(geometry=[], crs=4326)
        rf = gpd.GeoDataFrame(geometry=[], crs=CRS_M)

    # Prefer patch layer for neighbour distance; fall back to exploded extant pieces
    patches = gpd.GeoDataFrame(geometry=[], crs=CRS_M)
    try:
        patches = gpd.read_file(MASTER_GPKG, layer="rainforest_patches").to_crs(CRS_M)
    except Exception:
        if rf is not None and not rf.empty:
            patches = rf.explode(index_parts=False).reset_index(drop=True)

    neighbour_meta = None
    if patches is not None and not patches.empty:
        patches = patches[patches.geometry.notna() & ~patches.geometry.is_empty].copy()
        # Exclude patches that touch the reserve (they are the same local core)
        others = patches[patches.geometry.distance(ru) > 2.0].copy()
        if not others.empty:
            others["dist_m"] = others.geometry.distance(ru)
            others["ha"] = others.geometry.area / 10000.0
            nearest = others.sort_values("dist_m").iloc[0]
            dist_m = float(nearest["dist_m"])
            ha = float(nearest["ha"])
            p_res, p_patch = nearest_points(ru, nearest.geometry)
            connector = gpd.GeoDataFrame(
                {
                    "hover_line": [f"About {dist_m:.0f} m to the nearest other rainforest patch (~{ha:.1f} ha)"],
                    "geometry": [LineString([p_res, p_patch])],
                },
                crs=CRS_M,
            ).to_crs(4326)
            mid = LineString([p_res, p_patch]).interpolate(0.5, normalized=True)
            mid_wgs = gpd.GeoSeries([mid], crs=CRS_M).to_crs(4326).iloc[0]
            neigh_poly = gpd.GeoDataFrame(
                {"hover_line": [f"Nearest other rainforest (~{ha:.1f} ha)"], "geometry": [nearest.geometry]},
                crs=CRS_M,
            ).to_crs(4326)
            out["connector"] = connector
            out["neighbour_poly"] = neigh_poly
            neighbour_meta = {
                "lat": float(mid_wgs.y),
                "lon": float(mid_wgs.x),
                "dist_m": dist_m,
                "ha": ha,
                "label": f"~{dist_m:.0f} m to nearest rainforest",
            }
    out["neighbour"] = neighbour_meta
    return out


def render_kept_island_map(metrics: dict, basemap_name: str, chapter_idx: int) -> None:
    """
    KEPT slide map: reserve as an island in cleared land within 1 km,
    with a light nearest-neighbour link toward the NEXT chapter.
    """
    profile = metrics.get("reserve_profile") or {}
    rings = profile.get("landscape_rings") or {}
    nearby = profile.get("nearby_habitat") or {}
    tec = profile.get("threatened_ecological_community") or {}
    reserve_ha = float(metrics.get("reserve_ha") or profile.get("reserve", {}).get("area_ha_calculated") or 0)
    rf_1km = float(rings.get("rainforest_ha_within_1000m") or 0)
    cleared_1km = float(rings.get("cleared_contrast_ha_within_1000m") or 0)
    n_patches = int(nearby.get("rainforest_patches_within_1km_excl_touching") or 0)
    nearest_m = nearby.get("nearest_rainforest_patch_m")
    nearest_ha = nearby.get("nearest_rainforest_patch_ha")
    nsw = tec.get("nsw_status") or "Endangered"
    epbc = tec.get("epbc_status") or "Critically Endangered"

    st.markdown("##### Around the reserve")
    st.markdown(
        f"""
<div style="background:rgba(30,58,40,0.05);border:1px solid rgba(30,58,40,0.12);
border-radius:0.75rem;padding:0.85rem 1rem;margin:0.35rem 0 0.75rem;font-size:0.95rem;line-height:1.45;color:#2c382e;">
<p style="margin:0 0 0.55rem;"><b>Dark green</b> is Robertson Nature Reserve
(~<b>{reserve_ha:.1f} hectares</b>) — the piece we kept.</p>
<p style="margin:0 0 0.55rem;"><b>Warm sand</b> is cleared land within a kilometre
(~<b>{cleared_1km:,.0f} hectares</b>). <b>Green patches</b> are other rainforest still nearby
(~<b>{rf_1km:,.0f} hectares</b>).</p>
<p style="margin:0 0 0.55rem;">About <b>{n_patches}</b> other rainforest patches sit within a kilometre.
The <b>gold dashed line</b> points to the nearest one
{f"(about {float(nearest_m):.0f} metres away, roughly {float(nearest_ha):.1f} hectares)" if nearest_m is not None else ""}.</p>
<p style="margin:0;font-size:0.88rem;color:#5c6b5e;">
Listed as Robertson Rainforest — {nsw} in NSW
{f" and {epbc} nationally" if epbc else ""}.</p>
</div>
""",
        unsafe_allow_html=True,
    )

    pack = kept_island_local_pack(1000.0)
    # Tight frame on the 1 km island (not the old ~2.4 km "near" view)
    reserve_m = load_layer("robertson_nature_reserve", 4)
    if reserve_m is not None and not reserve_m.empty:
        try:
            tight = reserve_m.to_crs(CRS_M).copy()
            tight["geometry"] = tight.geometry.buffer(1150.0)
            fit = bounds_of(tight.to_crs(4326))
        except Exception:
            fit = fit_bounds_for_recipe("close")
    else:
        fit = fit_bounds_for_recipe("close")

    use_bm = basemap_name if str(basemap_name).startswith("Satellite") else "Soft paper"
    fmap = make_map(fit, basemap_name=use_bm)

    cleared = pack.get("cleared")
    rainforest = pack.get("rainforest")
    reserve = pack.get("reserve")
    ring = pack.get("ring")
    connector = pack.get("connector")
    neighbour_poly = pack.get("neighbour_poly")
    neighbour = pack.get("neighbour")

    if cleared is not None and not cleared.empty:
        add_poly(
            fmap,
            cleared,
            name="Cleared / non-native (1 km)",
            color="#c4a882",
            fill_opacity=0.58,
            weight=0,
            stroke_color="#c4a882",
        )
    if rainforest is not None and not rainforest.empty:
        add_poly(
            fmap,
            rainforest,
            name="Rainforest nearby (1 km)",
            color="#3f6f4a",
            fill_opacity=0.62,
            weight=0.5,
            stroke_color="#2f5d3a",
            line_opacity=0.65,
        )
    if neighbour_poly is not None and not neighbour_poly.empty:
        add_poly(
            fmap,
            neighbour_poly,
            name="Nearest other rainforest",
            color="#eab308",
            fill_opacity=0.45,
            weight=2.6,
            stroke_color="#a16207",
            line_opacity=0.95,
        )
    if ring is not None and not ring.empty:
        add_lines(
            fmap,
            ring,
            name="1 km frame",
            color="#57534e",
            weight=2.0,
            line_opacity=0.75,
            dash_array="2 8",
        )
    if connector is not None and not connector.empty:
        add_lines(
            fmap,
            connector,
            name="Nearest neighbour link",
            color="#b45309",
            weight=3.2,
            line_opacity=0.95,
            dash_array="8 10",
        )
    if reserve is not None and not reserve.empty:
        add_poly(
            fmap,
            reserve,
            name="Reserve halo",
            color="#fef9e7",
            fill_opacity=0.0,
            weight=10,
            tip_field=None,
            stroke_color="#fef9e7",
        )
        add_poly(
            fmap,
            reserve,
            name="Robertson Nature Reserve",
            color="#14532d",
            fill_opacity=0.85,
            weight=2.8,
            stroke_color="#052e16",
        )
        if metrics.get("reserve_lat") is not None:
            fmap.add_child(
                ReserveLabel(float(metrics["reserve_lat"]), float(metrics["reserve_lon"]), "The reserve we kept")
            )

    if neighbour and neighbour.get("lat") is not None:
        fmap.add_child(
            ReserveLabel(float(neighbour["lat"]), float(neighbour["lon"]), neighbour.get("label") or "Nearest link")
        )

    legend = _story_legend_html(
        [
            ("#14532d", "Reserve"),
            ("#c4a882", "Cleared"),
            ("#3f6f4a", "Rainforest"),
            ("#b45309", "Nearest link"),
        ]
    )
    dist_txt = f"about {float(nearest_m):.0f} metres away" if nearest_m is not None else "nearby"
    fmap.add_child(
        StoryMapChrome(
            legend,
            f"A small reserve in cleared country — nearest other rainforest {dist_txt}.",
        )
    )

    st.markdown('<div class="media-stage craft-wrap">', unsafe_allow_html=True)
    st_folium(
        fmap,
        use_container_width=True,
        height=580,
        returned_objects=[],
        key=f"kept_island_map_v2_{chapter_idx}",
    )
    st.markdown("</div>", unsafe_allow_html=True)
    st.caption(
        "Warm sand is cleared land. Green is rainforest. The gold dash points to the nearest other patch."
    )


def render_land_care_panel(metrics: dict, *, mode: str = "where") -> None:
    """CARE page: choose a kind of care and see nearby places that may suit it."""
    if "land_care_work_id" not in st.session_state:
        st.session_state.land_care_work_id = LAND_CARE_DEFAULT_ID

    heading = "Choose a kind of care" if mode == "where" else "Match care to the place"
    st.markdown(
        f'<p style="margin:0.55rem 0 0.35rem;font-size:0.68rem;letter-spacing:0.1em;'
        f'text-transform:uppercase;font-weight:700;color:#5c6b5e;">{heading}</p>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Pick one option. The map shows nearby places that may suit that work — "
        "ideas to talk about, not a work order."
    )

    # Work-type chips (2×3) — colour swatch matches map legend
    cols = st.columns(2)
    for i, work in enumerate(LAND_MANAGEMENT_WORK):
        with cols[i % 2]:
            selected = st.session_state.land_care_work_id == work["id"]
            count = land_care_count(metrics, work)
            count_bit = f" · ~{count}" if count is not None else ""
            label = f"{work['title']}{count_bit}"
            if st.button(
                label,
                key=f"land_care_chip_{mode}_{work['id']}",
                use_container_width=True,
                type="primary" if selected else "secondary",
                help=work["summary"],
            ):
                st.session_state.land_care_work_id = work["id"]
                st.rerun()

    work = land_care_work(st.session_state.land_care_work_id)
    count = land_care_count(metrics, work)
    count_line = (
        f"About {count} nearby places marked on the map"
        if count is not None
        else "Living bush near the reserve (no place count for this work type)"
    )

    # One detail panel — not a wall of cards
    if mode == "where":
        st.markdown(
            f'<div style="margin-top:0.75rem;padding:0.85rem 1rem;border-radius:0.75rem;'
            f'border-left:4px solid {work["color"]};background:rgba(30,58,40,0.05);'
            f'border:1px solid rgba(30,58,40,0.1);border-left-width:4px;">'
            f'<p style="margin:0 0 0.2rem;font-size:0.72rem;letter-spacing:0.08em;text-transform:uppercase;'
            f'font-weight:700;color:{work["color"]};">{work["title"]}</p>'
            f'<p style="margin:0 0 0.45rem;color:#2c382e;font-size:0.95rem;line-height:1.4;">{work["summary"]}</p>'
            f'<p style="margin:0 0 0.35rem;color:#2c382e;font-size:0.9rem;"><b>On the map:</b> {work["where_on_map"]}</p>'
            f'<p style="margin:0;color:#5c6b5e;font-size:0.85rem;"><b>Nearby:</b> {count_line}</p>'
            f"</div>",
            unsafe_allow_html=True,
        )
        render_land_care_photo(work)
    else:
        st.markdown(
            f'<div style="margin-top:0.75rem;padding:0.85rem 1rem;border-radius:0.75rem;'
            f'border-left:4px solid {work["color"]};background:rgba(30,58,40,0.05);'
            f'border:1px solid rgba(30,58,40,0.1);border-left-width:4px;">'
            f'<p style="margin:0 0 0.2rem;font-size:0.72rem;letter-spacing:0.08em;text-transform:uppercase;'
            f'font-weight:700;color:{work["color"]};">{work["title"]}</p>'
            f'<p style="margin:0 0 0.45rem;color:#2c382e;font-size:0.95rem;line-height:1.4;">'
            f'<b>What to do:</b> {work["do"]}</p>'
            f'<p style="margin:0 0 0.35rem;color:#2c382e;font-size:0.9rem;">'
            f'<b>Check first:</b> {work["field_check"]}</p>'
            f'<p style="margin:0 0 0.35rem;color:#2c382e;font-size:0.9rem;">'
            f'<b>Talk to:</b> {work["talk_to"]}</p>'
            f'<p style="margin:0 0 0.35rem;color:#5c6b5e;font-size:0.85rem;">'
            f'<b>Best for:</b> {work["fits"]}</p>'
            f'<p style="margin:0 0 0.35rem;color:#2c382e;font-size:0.9rem;">'
            f'<b>Why it helps:</b> {(LAND_CARE_LIFE_LINKS.get(work["id"]) or {}).get("helps", "Supports bush used by local wildlife.")}</p>'
            f'<p style="margin:0;color:#5c6b5e;font-size:0.85rem;"><b>Nearby:</b> {count_line}</p>'
            f"</div>",
            unsafe_allow_html=True,
        )
        render_land_care_photo(work)

    st.markdown(
        f'<p style="margin:0.65rem 0 0;font-size:0.78rem;color:#78716c;line-height:1.35;">'
        f"{LAND_CARE_INTEGRITY}</p>",
        unsafe_allow_html=True,
    )


def apply_land_care_to_slide(slide: dict) -> dict:
    """Sync selected work type into map layers / hero for Chapters 3–4."""
    work = land_care_work(st.session_state.get("land_care_work_id"))
    out = dict(slide)
    out["layers"] = list(work["layers"])
    out["hero"] = list(work.get("hero") or [])
    out["context"] = list(work.get("context") or [])
    out["action_map_sentence"] = (
        f'{work["where_on_map"]} Check on the photo first, and only act with agreement.'
    )
    # Work-aware key for Folium remount + legend
    color = work.get("color") or "#c9a24a"
    out["action_legend_beats"] = [
        (color, work["title"]),
        ("#3f6f4a", "Rainforest"),
        ("#14532d", "Nature Reserve"),
    ]
    if "hydro" in out["layers"]:
        out["action_legend_beats"].insert(1, ("#4f7f98", "Stream"))
    if "opp_public" in out["layers"]:
        out["action_legend_beats"] = [
            ("#5b8a72", "Public land hint — not free to plant"),
            ("#3f6f4a", "Rainforest"),
            ("#14532d", "Nature Reserve"),
        ]
    return out


def ensure_land_care_action_view(slide: dict, chapter_idx: int) -> None:
    """Default Chapters 3–4 to satellite / Action the first time you land on them."""
    if slide.get("default_view") != "Action":
        return
    marker = f"land_care_viewed_{chapter_idx}"
    if not st.session_state.get(marker):
        st.session_state.map_view_mode = "Action"
        st.session_state[marker] = True


def render_action_steps() -> None:
    """Practical conservation steps for Robertson — end of the story."""
    items = "".join(f"<li style='margin:0.35rem 0;'>{step}</li>" for step in ACTION_STEPS)
    st.markdown(
        f'<div style="margin-top:0.75rem;padding:0.85rem 1rem;background:rgba(30,58,40,0.06);'
        f'border-radius:0.75rem;border:1px solid rgba(30,58,40,0.12);">'
        f'<p style="margin:0 0 0.45rem;font-size:0.68rem;letter-spacing:0.1em;text-transform:uppercase;'
        f'font-weight:700;color:#5c6b5e;">Actionable steps for Robertson</p>'
        f'<ol style="margin:0;padding-left:1.2rem;color:#2c382e;font-size:0.92rem;line-height:1.45;">'
        f"{items}</ol></div>",
        unsafe_allow_html=True,
    )


def render_sidecar(slide: dict, metrics: dict, basemap: str, idx: int, n: int) -> None:
    """Community StoryMap sidecar: story on the left, evolving map on the right."""
    render_progress(idx, n, slide)

    show_map = slide.get("map", True)
    extra = slide.get("extra")
    land_care_extras = {"land_care_where", "land_care_how", "land_management", "parcel_explorer"}
    ensure_land_care_action_view(slide, idx)

    # Final page: full-width Country acknowledgement + data sources (no empty map column)
    if extra == "acknowledgement":
        render_acknowledgement()
        bprev, bnext, _spacer = st.columns([1.1, 1.1, 3.8], gap="small")
        with bprev:
            st.button(
                "← Previous",
                use_container_width=True,
                disabled=idx <= 0,
                key=f"prev_{idx}",
                on_click=lambda i=idx - 1: st.session_state.__setitem__("slide_idx", i),
            )
        with bnext:
            def _go_cover() -> None:
                st.session_state.slide_idx = 0
                st.session_state.entered_atlas = False

            st.button(
                "Cover",
                use_container_width=True,
                type="primary",
                key=f"next_{idx}",
                on_click=_go_cover,
            )
        return

    recipe_layers = list(slide["layers"])
    state_key = f"layers_v4::{slide['key']}"
    if state_key not in st.session_state:
        st.session_state[state_key] = {k: (k in recipe_layers) for k in recipe_layers}

    paint_slide = dict(slide)
    if extra in land_care_extras:
        paint_slide = apply_land_care_to_slide(paint_slide)
        for k in list(st.session_state.get(state_key, {})):
            st.session_state[state_key][k] = k in paint_slide["layers"]
        for k in paint_slide["layers"]:
            st.session_state.setdefault(state_key, {})[k] = True
    else:
        selected = [k for k, on in st.session_state[state_key].items() if on]
        if selected:
            paint_slide["layers"] = selected

    # Care chapter needs a wider story rail for chips + photo
    if extra in {"land_care_how", "land_management"}:
        narrative, media = st.columns([0.38, 0.62], gap="large")
    elif show_map:
        narrative, media = st.columns([0.30, 0.70], gap="large")
    else:
        narrative, media = st.columns([0.48, 0.52], gap="medium")

    with narrative:
        st.markdown(
            f'<p class="sm-kicker">{slide["kicker"]}</p>'
            f'<h2 class="sm-title">{slide["title"]}</h2>'
            f'<div class="sm-title-rule"></div>',
            unsafe_allow_html=True,
        )
        for para in slide["body"]:
            st.markdown(f'<p class="sm-body">{para}</p>', unsafe_allow_html=True)
        contrast = slide.get("contrast")
        if contrast and len(contrast) == 2:
            c_lab, c_txt = contrast
            c_col = {
                "LOSS": "#9a3412",
                "KEPT": "#14532d",
                "LIFE": "#9f1239",
                "NEXT": "#a16207",
                "CARE": "#3f6f4a",
                "RESPECT": "#1e3a28",
            }.get(str(c_lab), "#1e3a28")
            st.markdown(
                f'<div style="margin:0.7rem 0 0.85rem;padding:0.75rem 0.9rem;border-left:4px solid {c_col};'
                f'background:rgba(30,58,40,0.05);border-radius:0 0.65rem 0.65rem 0;">'
                f'<p style="margin:0 0 0.2rem;font-size:0.68rem;letter-spacing:0.12em;text-transform:uppercase;'
                f'font-weight:700;color:{c_col};">{c_lab}</p>'
                f'<p style="margin:0;color:#2c382e;font-size:0.98rem;line-height:1.4;">{c_txt}</p></div>',
                unsafe_allow_html=True,
            )
        beats = list(slide.get("beats") or [])[:1]
        if beats:
            val, label = beats[0]
            st.markdown(
                f'<div class="sm-beat">'
                f'<p class="sm-beat-val">{val}</p>'
                f'<p class="sm-beat-label">{label}</p>'
                f"</div>",
                unsafe_allow_html=True,
            )
        if extra in {"life", "life_worth"}:
            render_life_worth_panel(metrics, placement="rail")
        if extra == "actions":
            render_action_steps()
        if extra and extra not in {
            "life",
            "life_worth",
            "actions",
            "then_now",
            "kept_island",
            "acknowledgement",
            *land_care_extras,
        }:
            render_extra_panel(extra, metrics)
        if extra in land_care_extras:
            render_extra_panel(extra, metrics)
        if extra == "kept_island":
            render_extra_panel(extra, metrics)
        notes: list[str] = []
        if slide.get("footnote"):
            notes.append(str(slide["footnote"]))
        if show_map or notes or slide.get("evidence"):
            with st.expander("Sources & notes", expanded=False):
                for note in notes:
                    st.caption(note)
                if slide.get("evidence"):
                    render_evidence_chips(list(slide.get("evidence") or []))

    with media:
        if show_map:
            active_basemap = render_basemap_mode_toggle()
            if extra == "then_now":
                render_then_now_slider(metrics, active_basemap, idx)
            elif extra == "kept_island":
                render_kept_island_map(metrics, active_basemap, idx)
            else:
                if extra in land_care_extras:
                    paint_slide = dict(paint_slide)
                    paint_slide["_work_id"] = st.session_state.get(
                        "land_care_work_id", LAND_CARE_DEFAULT_ID
                    )
                # LIFE chapter: slightly shorter map so cards fit under it
                if extra in {"life", "life_worth"}:
                    paint_slide = dict(paint_slide)
                    paint_slide["_map_height"] = 420
                render_evolving_map(paint_slide, metrics, active_basemap, idx)
                if extra in {"life", "life_worth"}:
                    render_life_worth_panel(metrics, placement="under_map")
        elif extra == "acknowledgement":
            render_acknowledgement()
        else:
            b64 = hero_image_b64()
            bg = f"background-image:url('{b64}');" if b64 else "background:linear-gradient(160deg,#1e3a28,#3f6f4a);"
            st.markdown(
                f"""
                <div style="{bg}background-size:cover;background-position:center;height:620px;
                border-radius:1.35rem 0.45rem 1.2rem 0.65rem;display:flex;align-items:flex-end;padding:1.4rem;
                border:1px solid rgba(30,58,40,0.14);">
                  <div style="color:#f4f7f2;font-family:Fraunces,serif;font-size:1.65rem;font-weight:650;
                  font-style:italic;text-shadow:0 2px 18px rgba(0,0,0,0.4);max-width:18rem;line-height:1.15;">
                    Keep this small reserve.<br>Then care for the living edges around town.
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    bprev, bnext, _spacer = st.columns([1.1, 1.1, 3.8], gap="small")
    with bprev:
        st.button(
            "← Previous",
            use_container_width=True,
            disabled=idx <= 0,
            key=f"prev_{idx}",
            on_click=lambda i=idx - 1: st.session_state.__setitem__("slide_idx", max(0, i)),
        )
    with bnext:
        if idx >= n - 1:
            def _go_cover() -> None:
                st.session_state.slide_idx = 0
                st.session_state.entered_atlas = False

            st.button(
                "Cover",
                use_container_width=True,
                type="primary",
                key=f"next_{idx}",
                on_click=_go_cover,
            )
        else:
            st.button(
                "Next →",
                use_container_width=True,
                type="primary",
                key=f"next_{idx}",
                on_click=lambda i=idx + 1: st.session_state.__setitem__("slide_idx", i),
            )


def main() -> None:
    _style_page()
    if not MASTER_GPKG.is_file():
        st.error(f"Master GeoPackage missing:\n{MASTER_GPKG}\n\nRun `python src/07_export_master.py` first.")
        st.stop()

    metrics = influence_metrics()
    slides = _story_slides(metrics)

    if "entered_atlas" not in st.session_state:
        st.session_state.entered_atlas = False
    if "slide_idx" not in st.session_state:
        st.session_state.slide_idx = 0
    # Clamp before any widget binds to slide_idx (story length can shrink after merges)
    st.session_state.slide_idx = max(0, min(int(st.session_state.slide_idx), len(slides) - 1))

    # Cover — StoryMap title screen
    if not st.session_state.entered_atlas:
        render_hero(metrics)
        c1, c2, c3 = st.columns([1.15, 1, 1.15])
        with c2:
            if st.button("Begin the story", use_container_width=True, type="primary"):
                st.session_state.entered_atlas = True
                st.session_state.slide_idx = 0
                st.rerun()
        st.stop()

    with st.sidebar:
        st.markdown(f"### {BRAND}")
        st.caption("Five pages · Lost → Kept → Life → Care → Respect")
        # Bind jump control directly to slide_idx so Next/Prev cannot be overwritten
        # by a stale selectbox value (classic Streamlit widget-state fight).
        st.selectbox(
            "Jump to chapter",
            options=list(range(len(slides))),
            format_func=lambda i: f"{i + 1:02d} · {slides[i]['title']}",
            key="slide_idx",
            label_visibility="collapsed",
        )
        if st.button("Cover"):
            st.session_state.entered_atlas = False
            st.rerun()
        st.divider()
        st.caption("Above the map: Story view or Satellite view.")
        with st.expander("More map backgrounds", expanded=False):
            craft = st.selectbox(
                "Background map",
                list(BASEMAPS.keys()),
                index=list(BASEMAPS.keys()).index("Esri terrain"),
                help="Optional. Day-to-day: use Story or Satellite above the map.",
            )
            if st.button("Apply background"):
                st.session_state.force_basemap = craft
                st.session_state.map_view_mode = "Action" if "Satellite" in craft else "Story"
                st.rerun()

    idx = int(st.session_state.slide_idx)
    # Basemap is chosen inside the map panel (Story / Action); placeholder is unused
    render_sidecar(slides[idx], metrics, "Soft paper", idx, len(slides))


if __name__ == "__main__":
    main()
