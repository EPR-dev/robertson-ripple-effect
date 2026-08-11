"""
Robertson Rainforest — a short community story.

1. LOSS  — rainforest cleared around Robertson (negative)
2. KEPT  — Robertson Nature Reserve as a positive seed
3. LIFE  — listed life in remnant pockets
4. CARE  — ways to protect and care for living edges
5. RESPECT — Acknowledgement of Country

Public-facing. Concise. One idea per screen.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

BRAND = "Robertson Rainforest"
BRAND_SUBTITLE = "What was lost. What we kept. What still lives. How we can care for it."
BRAND_TAGLINE = "A short story for the people of Robertson"
BRAND_ALT = (
    "Most of the rainforest around Robertson was cleared long ago. "
    "A small reserve still holds a living piece — and careful care of the bush nearby can help it last."
)

ACKNOWLEDGEMENT_OF_COUNTRY = (
    "We acknowledge the Gundungurra and Dharawal (Tharawal) Peoples as the Traditional "
    "Custodians of the Country on which Robertson stands. We recognise their continuing "
    "connection to land, waters, sky and culture, and pay our respects to Elders past and present."
)

EVIDENCE_HELP = {
    "OBSERVED": "Seen in trusted public maps and records.",
    "PUBLISHED": "From published research or government listings.",
    "CALCULATED": "Measured from the maps in this story.",
    "MODELLED": "An informed estimate — not a field survey.",
}

CHAPTERS = [
    "What Was Lost",
    "What We Kept",
    "Life That Needs These Pockets",
    "Ways To Care For Land",
    "Acknowledgement of Country",
]

CHAPTER_PLATE_SLUGS = {
    "What Was Lost": "01_what_was_lost",
    "What We Kept": "02_what_we_kept",
    "Life That Needs These Pockets": "03_life_that_needs_these_pockets",
    "Ways To Care For Land": "04_ways_to_care_for_land",
    "Acknowledgement of Country": "06_acknowledgement_of_country",
}

STORY_SPINE = ["LOSS", "KEPT", "LIFE", "CARE", "RESPECT"]

FLOW_STEPS = [
    "what was lost",
    "what we kept",
    "life that needs pockets",
    "ways to care",
    "acknowledgement",
]

# Land-care work types — plain-language options for the CARE page.
# count_label keys match opportunity_cells_near labels from influence_metrics().
LAND_MANAGEMENT_WORK = [
    {
        "id": "protect",
        "title": "Protect living bush",
        "color": "#14532d",
        "summary": "The simplest win is keeping rainforest that is already standing.",
        "do": "Look after existing bush: keep weeds down at the edges, tread lightly, and support formal protection where it is welcome.",
        "where_on_map": "Dark green is the Nature Reserve. Lighter green is other rainforest still nearby.",
        "field_check": "On the photo, look for real tree canopy and fence lines. On foot, notice weeds, tracks, and rubbish — not dens or nests.",
        "talk_to": "NPWS for the reserve; neighbours and Landcare for bush outside the fence.",
        "fits": "Healthy bush, the Nature Reserve, and landholders already looking after remnants",
        "layers": ["rainforest", "reserve"],
        "hero": ["reserve", "rainforest"],
        "context": [],
        "count_label": None,
        "count_fallback": "living remnants",
        "photo": "protect.jpg",
        "photo_caption": "Protecting living bush means keeping canopy and understorey standing.",
    },
    {
        "id": "edge",
        "title": "Weed & harden edges",
        "color": "#c9a24a",
        "summary": "Where paddock meets bush, weeds and vines often push hardest into the forest.",
        "do": "Control vines and weeds along bush edges so native plants can recover, then plant a soft native fringe where people agree.",
        "where_on_map": "Gold squares mark cleared edges beside bush near the reserve.",
        "field_check": "Check the photo: is this really cleared land next to living bush? Confirm who owns it before any work.",
        "talk_to": "Bushcare or Landcare first, then the landholder — never assume a paddock edge is available.",
        "fits": "Reserve edges, remnant margins, and paddock fringes next to bush (with agreement)",
        "layers": ["opp_edge", "rainforest", "reserve"],
        "hero": ["opp_edge"],
        "context": ["rainforest", "reserve"],
        "count_label": "Cleared edges next to habitat",
        "count_fallback": "edge cells",
        "photo": "edge.jpg",
        "photo_caption": "Edge care can look like weeded margins and a recovering native fringe beside bush.",
    },
    {
        "id": "creek",
        "title": "Creek revegetation",
        "color": "#e76f51",
        "summary": "Planting along cleared creek lines cools water, holds soil, and links bush along the valley.",
        "do": "Plant local native trees and understorey along thin or cleared creek strips where landholders and agencies agree.",
        "where_on_map": "Rose squares mark stream-side gaps. Blue lines are mapped watercourses.",
        "field_check": "Confirm a real creek or drainage line in the photo and on the ground. Note stock access, weeds, and flood risk.",
        "talk_to": "Landholders, Landcare, and council or waterway programs — creek work needs permission and the right plants.",
        "fits": "Cleared or thin creek banks (public or private, only with agreement)",
        "layers": ["opp_riparian", "hydro", "rainforest", "reserve"],
        "hero": ["opp_riparian", "hydro"],
        "context": ["rainforest", "reserve"],
        "count_label": "Cleared gaps along streams",
        "count_fallback": "creek cells",
        "photo": "creek.jpg",
        "photo_caption": "Creek planting can cool water and link habitat along the banks.",
    },
    {
        "id": "gap",
        "title": "Close short gaps",
        "color": "#b45309",
        "summary": "Where two patches almost meet, a small planting can help wildlife move between them.",
        "do": "Restore short cleared gaps between two remnants so animals and plants can move more easily.",
        "where_on_map": "Gold squares near two green patches are places to talk about short links.",
        "field_check": "Look at the gap in the photo. Prefer short gaps beside living bush — not long open paddock crossings.",
        "talk_to": "Neighbours who share the gap, plus Landcare for design and plant lists.",
        "fits": "Short gaps beside existing bush (voluntary, agreed work only)",
        "layers": ["opp_edge", "rainforest", "reserve"],
        "hero": ["opp_edge", "rainforest"],
        "context": ["reserve"],
        "count_label": "Cleared edges next to habitat",
        "count_fallback": "edge cells",
        "photo": "gap.jpg",
        "photo_caption": "Closing a short gap can look like a planted link between two living patches.",
    },
    {
        "id": "public",
        "title": "Public places",
        "color": "#5b8a72",
        "summary": "Some nearby places sit on public or Crown land — still not a free-to-plant list.",
        "do": "Start conversations about verges, reserves, and Crown land with the agency that manages them.",
        "where_on_map": "Muted green squares hint at public or Crown land near the reserve.",
        "field_check": "Check who manages the land. Public land is not automatic permission. Watch for utilities and road safety.",
        "talk_to": "Council, Crown Lands, NPWS, or the road manager — then community groups if invited.",
        "fits": "Road verges, parks, Crown parcels, and other public land (with formal approval)",
        "layers": ["opp_public", "rainforest", "reserve"],
        "hero": ["opp_public"],
        "context": ["rainforest", "reserve"],
        "count_label": "Public / Crown land",
        "count_fallback": "public-context cells",
        "photo": "public.jpg",
        "photo_caption": "Agreed public plantings can add canopy and understorey on managed public land.",
    },
    {
        "id": "lonely",
        "title": "Support lonelier patches",
        "color": "#7c6a4a",
        "summary": "Some bush sits farther from the main network and feels the pressure of open edges.",
        "do": "Talk about buffers, weed control, and short links around patches that sit a little apart.",
        "where_on_map": "Warm brown squares sit near more isolated bush near the reserve.",
        "field_check": "Confirm the remnant still has living canopy. Ask whether isolation feels real on the ground.",
        "talk_to": "The landholder first; Landcare second. Isolation never justifies pressure on private land.",
        "fits": "Outlying remnants where owners want help reducing edge pressure",
        "layers": ["opp_isolated", "rainforest", "reserve"],
        "hero": ["opp_isolated"],
        "context": ["rainforest", "reserve"],
        "count_label": "Near isolated patches",
        "count_fallback": "isolated-context cells",
        "photo": "lonely.jpg",
        "photo_caption": "Supporting a lonelier patch can mean a buffer or link around an outlying remnant.",
    },
]

LAND_CARE_DEFAULT_ID = "edge"
LAND_MANAGEMENT_BY_ID = {w["id"]: w for w in LAND_MANAGEMENT_WORK}


def land_care_work(work_id: str | None = None) -> dict[str, Any]:
    """Resolve a work type; fall back to the default edge-care recipe."""
    wid = work_id or LAND_CARE_DEFAULT_ID
    return LAND_MANAGEMENT_BY_ID.get(wid) or LAND_MANAGEMENT_BY_ID[LAND_CARE_DEFAULT_ID]


def land_care_count(metrics: dict[str, Any], work: dict[str, Any]) -> int | None:
    """Near-reserve (~3.5 km) candidate cell count for this work type, if available."""
    label = work.get("count_label")
    if not label:
        return None
    near = metrics.get("opportunity_cells_near") or {}
    if label in near:
        return int(near[label])
    return None


# How each land-care choice can help living things (plain language — not guarantees).
LAND_CARE_LIFE_LINKS: dict[str, dict[str, Any]] = {
    "protect": {
        "guilds": ["Mammals", "Birds", "Plants", "Insects"],
        "helps": (
            "Keeping rainforest standing protects hollows, cool shade, and breeding places "
            "that mammals, forest birds, and rainforest plants already use."
        ),
    },
    "edge": {
        "guilds": ["Mammals", "Birds", "Plants", "Insects"],
        "helps": (
            "Weeding and hardening bush edges lets the understorey recover — food and cover "
            "for small mammals, birds, and the plants insects need."
        ),
    },
    "creek": {
        "guilds": ["Amphibians", "Birds", "Plants", "Insects"],
        "helps": (
            "Creek plantings cool the water, hold the soil, and restore moist paths that frogs, "
            "streamside plants, and insects depend on."
        ),
    },
    "gap": {
        "guilds": ["Mammals", "Birds"],
        "helps": (
            "Closing short gaps helps animals move between remnants instead of crossing "
            "open paddock alone."
        ),
    },
    "public": {
        "guilds": ["Birds", "Insects", "Plants"],
        "helps": (
            "Agreed plantings on verges and public reserves can add stepping-stone trees "
            "and flowers — only with the managing agency’s approval."
        ),
    },
    "lonely": {
        "guilds": ["Mammals", "Birds", "Plants"],
        "helps": (
            "Buffers and links around lonelier patches ease the pressure of open edges "
            "for wildlife stuck in small remnants."
        ),
    },
}

# Guild → preferred work ids shown on species cards
GUILD_CARE_HINTS: dict[str, list[str]] = {
    "Mammals": ["protect", "gap", "edge", "lonely"],
    "Birds": ["protect", "gap", "edge", "public"],
    "Plants": ["protect", "creek", "edge"],
    "Insects": ["creek", "edge", "protect", "public"],
    "Amphibians": ["creek", "protect"],
}

LIFE_WORTH_INTEGRITY = (
    "Wildlife numbers come from public records near Robertson. "
    "Absence of a record does not mean a species is gone."
)

CHAPTER_MAP_RECIPES: dict[str, dict[str, Any]] = {
    "What Was Lost": {
        "basemap": "Soft paper",
        "hero": ["preclear", "rainforest"],
        "context": ["reserve"],
        "layers": ["preclear", "rainforest", "reserve"],
        "map_sentence": "Tan shows rainforest that models say once covered this plateau. Green is what remains today.",
        "action_map_sentence": "On the photo, look for living tree canopy. Switch to Story map to see past and present more clearly.",
        "fit": "context",
        "emphasis": "Land influence",
        "soft_heat": False,
        "legend_beats": [
            ("#c4a574", "Past rainforest (modelled)"),
            ("#3f6f4a", "Rainforest today"),
            ("#14532d", "The reserve we kept"),
        ],
    },
    "What We Kept": {
        "basemap": "Soft paper",
        "hero": ["reserve"],
        "context": ["cleared", "rainforest"],
        "layers": ["cleared", "rainforest", "reserve"],
        "map_sentence": "Warm sand is cleared land within a kilometre. Green is rainforest still nearby. Dark green is the reserve we kept.",
        "action_map_sentence": "On the photo, compare the reserve trees with the paddocks around them. The gold dashed line points to the nearest other rainforest patch.",
        "fit": "close",
        "emphasis": "Land influence",
        "soft_heat": False,
        "legend_beats": [
            ("#14532d", "Robertson Nature Reserve"),
            ("#c4a882", "Cleared land nearby"),
            ("#3f6f4a", "Other rainforest nearby"),
            ("#b45309", "Nearest rainforest neighbour"),
        ],
    },
    "Life That Needs These Pockets": {
        "basemap": "Soft paper",
        "default_view": "Story",
        "hero": ["threat_grid"],
        "context": ["rainforest", "reserve"],
        "layers": ["threat_grid", "rainforest", "reserve"],
        "map_sentence": "Warmer colours show where more threatened plants and animals have been recorded nearby. Green is rainforest. The map never shows dens or nests.",
        "action_map_sentence": "On the photo, compare warmer colours with living canopy. These are public records grouped into areas — not exact animal locations.",
        "fit": "near",
        "emphasis": "Species refuge",
        "soft_heat": False,
        "legend_beats": [
            ("#ffcdb2", "Fewer records"),
            ("#e76f51", "More records"),
            ("#9d0208", "Most records"),
            ("#3f6f4a", "Rainforest remnants"),
            ("#14532d", "Nature Reserve"),
        ],
        "action_legend_beats": [
            ("#e76f51", "Where more listed species are recorded"),
            ("#3f6f4a", "Mapped rainforest"),
            ("#14532d", "Nature Reserve"),
        ],
    },
    "What To Care For Next": {
        "basemap": "Satellite + labels",
        "default_view": "Action",
        "hero": ["opp_edge"],
        "context": ["rainforest", "reserve"],
        "layers": ["opp_edge", "rainforest", "reserve"],
        "map_sentence": "Soft shapes hint where edge and creek care might help — switch to the photo to check real trees.",
        "action_map_sentence": "Gold and rose squares are places near the reserve worth a closer look. Check trees and creeks on the photo — ideas to talk about, not instructions for private land.",
        "fit": "near",
        "emphasis": "Land influence",
        "soft_heat": False,
        "legend_beats": [
            ("#c9a24a", "Edge places to check"),
            ("#e76f51", "Creek places to check"),
            ("#3f6f4a", "Rainforest that remains"),
            ("#14532d", "The reserve"),
        ],
        "action_legend_beats": [
            ("#c9a24a", "Edge place — check on the photo"),
            ("#e76f51", "Creek place — check on the photo"),
            ("#5b8a72", "Public land hint — not free to plant"),
            ("#3f6f4a", "Mapped rainforest"),
            ("#14532d", "Nature Reserve"),
        ],
    },
    "Ways To Care For Land": {
        "basemap": "Satellite + labels",
        "default_view": "Action",
        "hero": ["opp_edge"],
        "context": ["rainforest", "reserve"],
        "layers": ["opp_edge", "rainforest", "reserve"],
        "map_sentence": "Choose a kind of care on the left — the map shows nearby places that may suit that work.",
        "action_map_sentence": "Match the work to the place on the photo. Check on the ground first, and only act with the landholder or agency.",
        "fit": "near",
        "emphasis": "Land influence",
        "soft_heat": False,
        "legend_beats": [
            ("#14532d", "Protect living bush"),
            ("#c9a24a", "Edge and gap care"),
            ("#e76f51", "Creek care"),
            ("#5b8a72", "Public land hint"),
            ("#3f6f4a", "Remnants"),
        ],
        "action_legend_beats": [
            ("#c9a24a", "Edge place — check the trees"),
            ("#e76f51", "Creek place — check the waterway"),
            ("#5b8a72", "Public land hint only"),
            ("#4f7f98", "Mapped stream"),
            ("#14532d", "Nature Reserve"),
        ],
    },
    "Acknowledgement of Country": {
        "basemap": "Soft paper",
        "hero": ["reserve"],
        "context": ["rainforest"],
        "layers": ["rainforest", "reserve"],
        "map_sentence": "This Country has been cared for long before the reserve was gazetted.",
        "action_map_sentence": "",
        "fit": "near",
        "emphasis": "Land influence",
        "soft_heat": False,
        "legend_beats": [
            ("#14532d", "Robertson Nature Reserve"),
            ("#3f6f4a", "Living rainforest nearby"),
        ],
    },
}

CHAPTER_LAYER_DEFAULTS = {k: list(v["layers"]) for k, v in CHAPTER_MAP_RECIPES.items()}

# Kept for any legacy callers — preferred guidance now lives on each LAND_MANAGEMENT_WORK card.
ACTION_STEPS = [
    "Keep visiting Robertson Nature Reserve — proof that a small protected place can still hold rainforest beside town.",
    "Match the work to the place: weeds on edges, plantings on creeks, short gaps between living bush.",
    "Talk with neighbours, Bushcare or Landcare, schools and council before acting on any land that is not yours.",
    "Treat every marked place as something to talk about — never a demand on a private landholder.",
]

LAND_CARE_INTEGRITY = (
    "Places on the map are ideas to check near the reserve — "
    "not instructions for private land, and public land is not free to plant."
)


def _slide(
    key: str,
    kicker: str,
    body: list[str],
    *,
    spine: str = "",
    beat: tuple[str, str] | None = None,
    contrast: tuple[str, str] | None = None,
    footnote: str = "",
    evidence: list[str] | None = None,
    extra: str | None = None,
    map_on: bool = True,
) -> dict[str, Any]:
    recipe = CHAPTER_MAP_RECIPES[key]
    return {
        "key": key,
        "kicker": kicker,
        "title": key,
        "body": body,
        "beats": [beat] if beat else [],
        "contrast": contrast,
        "act": spine,
        "act_line": "",
        "layers": list(recipe["layers"]),
        "hero": list(recipe["hero"]),
        "context": list(recipe["context"]),
        "map_sentence": recipe["map_sentence"],
        "action_map_sentence": recipe.get("action_map_sentence") or "",
        "fit": recipe["fit"],
        "soft_heat": bool(recipe.get("soft_heat")),
        "legend_beats": list(recipe.get("legend_beats") or []),
        "action_legend_beats": list(recipe.get("action_legend_beats") or []),
        "story_basemap": recipe.get("basemap", "Soft paper"),
        "default_view": recipe.get("default_view", "Story"),
        "emphasis": recipe.get("emphasis", "Balanced"),
        "footnote": footnote,
        "extra": extra,
        "evidence": evidence or [],
        "map": map_on,
    }


def build_story_slides(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    """Five slides: loss, kept, life, care, acknowledgement."""
    reserve_ha = float(metrics.get("reserve_ha") or 0)
    brush_ha = float(metrics.get("yarrawa_brush_ha_published") or 2500)
    rf_5 = float(metrics.get("rf_ha_5km") or metrics.get("rf_ha") or 0)
    pre_5 = float(metrics.get("preclear_ha_5km") or 0)
    profile = metrics.get("reserve_profile") or {}
    veg = profile.get("vegetation_in_reserve") or {}
    tec = profile.get("threatened_ecological_community") or {}
    rings = profile.get("landscape_rings") or {}
    nearby = profile.get("nearby_habitat") or {}
    pct = veg.get("majority_pct_name") or "Sydney Montane Basalt Rainforest"
    lost_ha = max(pre_5 - rf_5, 0)
    rf_1km = float(rings.get("rainforest_ha_within_1000m") or 0)
    cleared_1km = float(rings.get("cleared_contrast_ha_within_1000m") or 0)
    n_rf_near = int(nearby.get("rainforest_patches_within_1km_excl_touching") or 0)
    nearest_m = nearby.get("nearest_rainforest_patch_m")
    life = metrics.get("life_summary") or {}
    listed_mammals = int(life.get("threatened_mammals") or 0)
    listed_birds = int(life.get("threatened_birds") or 0)
    listed_flora = int(life.get("threatened_flora") or 0)
    listed_total = int(life.get("threatened_taxa_total") or (listed_mammals + listed_birds + listed_flora))
    insect_taxa = int(life.get("insect_taxa_5km") or 0)
    gaps_by = metrics.get("habitat_gaps_by_type") or {}
    opp_near = metrics.get("opportunity_cells_near") or {}
    edge_n = int(opp_near.get("Cleared edges next to habitat") or gaps_by.get("SHORT_50M") or 0)

    return [
        _slide(
            key="What Was Lost",
            kicker="1 · LOSS",
            spine="LOSS",
            body=[
                "Most of the rainforest that once clothed this plateau is gone.",
                f"Old accounts describe the Yarrawa Brush as about {brush_ha:,.0f} hectares. "
                f"Around today’s reserve, maps suggest about {pre_5:,.0f} hectares of rainforest once stood nearby — "
                f"and only about {rf_5:,.0f} hectares remain.",
                "What was lost is not only trees. It is cool shade, linked patches of bush, "
                "and room for the plants and animals that need wet forest.",
            ],
            beat=(f"~{lost_ha:,.0f} ha", "rainforest no longer mapped nearby"),
            contrast=("LOSS", "Clearing took most of the forest"),
            footnote=(
                "The tan wash is a model of past rainforest — not a surveyed historic boundary. "
                "The green is rainforest mapped today."
            ),
            evidence=["PUBLISHED", "MODELLED", "OBSERVED"],
            extra="then_now",
        ),
        _slide(
            key="What We Kept",
            kicker="2 · KEPT",
            spine="KEPT",
            body=[
                "Against that loss, Robertson kept a living piece beside town.",
                f"Robertson Nature Reserve protects about {reserve_ha:.1f} hectares of {pct}. "
                f"It is part of Robertson Rainforest — listed as "
                f"{tec.get('nsw_status', 'Endangered')} in NSW"
                f"{(' and ' + str(tec.get('epbc_status')) + ' nationally') if tec.get('epbc_status') else ''}.",
                (
                    f"Within a kilometre, about {rf_1km:,.0f} hectares of rainforest still stand "
                    f"among roughly {cleared_1km:,.0f} hectares of cleared land — with about {n_rf_near} other "
                    f"rainforest patches nearby"
                    + (
                        f", the closest only about {float(nearest_m):.0f} metres away"
                        if nearest_m is not None
                        else ""
                    )
                    + ". A small reserve still matters because it is not alone — "
                    "other living bush remains around it."
                ),
                "For Robertson, that means a rare forest next to the village — "
                "a place of identity and living nature, not a number on a balance sheet.",
            ],
            beat=(f"{reserve_ha:.1f} ha", "protected rainforest beside town"),
            contrast=("KEPT", "A small reserve still holds living rainforest"),
            footnote=(
                "Figures within one kilometre come from mapped rainforest and cleared land around the reserve."
            ),
            evidence=["OBSERVED", "PUBLISHED", "CALCULATED"],
            extra="kept_island",
        ),
        _slide(
            key="Life That Needs These Pockets",
            kicker="3 · LIFE",
            spine="LIFE",
            body=[
                "These remnant pockets are not empty green shapes. They feed, shelter, and connect living things.",
                (
                    f"Within five kilometres, public records include about {listed_mammals} threatened mammals, "
                    f"{listed_birds} threatened birds, and {listed_flora} threatened plants"
                    + (f" — roughly {listed_total} listed species in all" if listed_total else "")
                    + ". Insects are rarely recorded here, so the map is quiet about them even if they are present."
                ),
                "The next page asks a practical question: how can we look after the bush "
                "so these animals and plants keep food, cover, and room to move?",
            ],
            beat=(str(listed_mammals or listed_total or "—"), "threatened mammals recorded nearby"),
            contrast=("LIFE", "Small pockets still hold listed life"),
            footnote=LIFE_WORTH_INTEGRITY,
            evidence=["OBSERVED", "PUBLISHED"],
            extra="life_worth",
        ),
        _slide(
            key="Ways To Care For Land",
            kicker="4 · CARE",
            spine="CARE",
            body=[
                "Looking after what remains starts with matching the work to the place.",
                "Choose a kind of care on the left — protect living bush, weed the edges, plant a creek, "
                "or close a short gap. The map shows nearby places that may suit that work.",
                "These are ideas to talk about with neighbours, Landcare, council and agencies — "
                "never a demand on anyone’s private land.",
            ],
            beat=(str(len(LAND_MANAGEMENT_WORK)), "kinds of care to choose from"),
            contrast=("CARE", "Protect bush · heal edges · plant creeks"),
            footnote=LAND_CARE_INTEGRITY,
            evidence=["CALCULATED", "OBSERVED"],
            extra="land_management",
        ),
        _slide(
            key="Acknowledgement of Country",
            kicker="5 · RESPECT",
            spine="RESPECT",
            body=[],
            beat=("Country", "first and always"),
            contrast=("RESPECT", "Acknowledgement of Country · and the sources behind this story"),
            evidence=["PUBLISHED"],
            extra="acknowledgement",
            map_on=False,
        ),
    ]
