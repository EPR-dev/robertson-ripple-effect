"""
Phase 2 — Wildlife + plants storytelling products.

Builds transparent taxon summaries and "Meet the Locals" / plant story cards
from BioNet clean observations already in the master GPKG.

Rules:
- No invented local occurrences
- Sensitive species: card allowed only with aggregated context (never precise coords)
- Cards support cartographic storytelling — not a species database dump
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(__file__).resolve().parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from config import load_settings  # noqa: E402
from utils import ensure_dirs, setup_logging, to_analysis_crs, write_gdf  # noqa: E402


STORY_GROUPS = {
    "Mammals": ["Mammalia"],
    "Birds": ["Aves"],
    "Amphibians": ["Amphibia"],
    "Reptiles": ["Reptilia"],
    "Native plants": ["Flora"],
}

# Connectivity narrative templates by broad habitat affinity (story aids — not models)
HABITAT_BLURBS = {
    "Mammalia": (
        "Many native mammals need linked canopy, hollows, or dense understorey. "
        "When rainforest and wet forest sit as islands in pasture, movement and recolonisation get harder."
    ),
    "Aves": (
        "Birds can cross gaps more easily than many mammals, yet rainforest specialists still depend on "
        "enough remnant cover and flowering/fruiting plants across the landscape."
    ),
    "Amphibia": (
        "Frogs often need moist refuges, streams, and vegetated drainage lines. "
        "Riparian gaps can matter as much as the size of a single bushland patch."
    ),
    "Reptilia": (
        "Reptiles use logs, rock, leaf litter and sunny edges within native vegetation. "
        "Small remnants can still matter when they keep structural habitat in the matrix."
    ),
    "Flora": (
        "Robertson Rainforest is a plant community first — trees, shrubs, ferns and vines that define the TEC. "
        "Conserving animals without conserving the flora misses half the story."
    ),
}

# Prefer these species for cards if present locally (real records required)
PREFERRED_CARD_SPECIES = [
    # mammals
    "Potorous tridactylus",
    "Phascolarctos cinereus",
    "Petauroides volans",
    "Cercartetus nanus",
    "Pteropus poliocephalus",
    "Dasyurus maculatus",
    # birds
    "Callocephalon fimbriatum",
    "Ninox strenua",
    "Menura novaehollandiae",
    # frogs
    "Litoria",
    # plants / rainforest
    "Doryphora sassafras",
    "Quintinia sieberi",
    "Polyosma cunninghamii",
    "Acacia melanoxylon",
    "Syzygium smithii",
    "Rhodamnia rubescens",
    "Persoonia glaucescens",
    "Tasmannia insipida",
    "Coprosma quadrifida",
]


def _buffer_subset(species: gpd.GeoDataFrame, geom, buffer_m: float, crs: str) -> gpd.GeoDataFrame:
    g = to_analysis_crs(species, crs)
    buf = geom.buffer(buffer_m)
    return g[g.intersects(buf)].copy()


def _species_table(df: gpd.GeoDataFrame | pd.DataFrame) -> pd.DataFrame:
    if df is None or len(df) == 0:
        return pd.DataFrame(
            columns=[
                "scientificName",
                "vernacularName",
                "taxon_group",
                "stateConservation",
                "countryConservation",
                "n_records",
                "year_min",
                "year_max",
                "is_threatened",
                "is_sensitive",
            ]
        )
    g = df.copy()
    g["vernacularName"] = g.get("vernacularName", pd.Series(index=g.index)).fillna("")
    agg = (
        g.groupby(["scientificName", "taxon_group"], dropna=False)
        .agg(
            vernacularName=("vernacularName", lambda s: next((str(x) for x in s if str(x).strip()), "")),
            stateConservation=("stateConservation", "first"),
            countryConservation=("countryConservation", "first"),
            n_records=("scientificName", "size"),
            year_min=("year", "min"),
            year_max=("year", "max"),
            is_threatened=("is_threatened", "max"),
            is_sensitive=("is_sensitive", "max"),
        )
        .reset_index()
        .sort_values(["is_threatened", "n_records"], ascending=[False, False])
    )
    return agg


def _group_summary(df: gpd.GeoDataFrame | pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    if df is None or len(df) == 0:
        return rows
    for label, classes in STORY_GROUPS.items():
        sub = df[df["taxon_group"].isin(classes)]
        if sub.empty:
            rows.append(
                {
                    "story_group": label,
                    "n_records": 0,
                    "n_species": 0,
                    "n_threatened_species": 0,
                }
            )
            continue
        thr = sub[sub["is_threatened"] == True]  # noqa: E712
        rows.append(
            {
                "story_group": label,
                "n_records": int(len(sub)),
                "n_species": int(sub["scientificName"].nunique()),
                "n_threatened_species": int(thr["scientificName"].nunique()),
            }
        )
    return rows


def _pick_cards(
    near: pd.DataFrame,
    aoi: pd.DataFrame,
    *,
    max_per_group: int = 4,
) -> list[dict[str, Any]]:
    """Build Meet the Locals cards from real local records only."""
    cards: list[dict[str, Any]] = []
    near = near.copy()
    aoi = aoi.copy()

    def _match_preferred(sci: str) -> bool:
        return any(sci.startswith(p) or p in sci for p in PREFERRED_CARD_SPECIES)

    for label, classes in STORY_GROUPS.items():
        pool = near[near["taxon_group"].isin(classes)].copy()
        if pool.empty:
            # fall back to AOI if nothing in 2 km
            pool = aoi[aoi["taxon_group"].isin(classes)].copy()
            locality = "recorded in study area"
        else:
            locality = "recorded within ~2 km of Robertson Nature Reserve"

        if pool.empty:
            continue

        pool["preferred"] = pool["scientificName"].astype(str).map(_match_preferred)
        pool = pool.sort_values(
            ["preferred", "is_threatened", "n_records"],
            ascending=[False, False, False],
        )

        picked = 0
        for _, row in pool.iterrows():
            if picked >= max_per_group:
                break
            sci = str(row["scientificName"])
            # Avoid duplicate scientific names across groups
            if any(c["scientific_name"] == sci for c in cards):
                continue
            sensitive = bool(row.get("is_sensitive"))
            status = str(row.get("stateConservation") or "Not listed")
            if status in ("", "None", "nan", "Not Listed"):
                status = "Not listed (NSW)"
            common = str(row.get("vernacularName") or "").strip() or sci.split()[0]
            blurb = HABITAT_BLURBS.get(classes[0], HABITAT_BLURBS["Flora"])
            cards.append(
                {
                    "card_id": f"sp_{len(cards)+1:03d}",
                    "story_group": label,
                    "common_name": common,
                    "scientific_name": sci,
                    "conservation_status_nsw": status,
                    "conservation_status_epbc": str(row.get("countryConservation") or ""),
                    "habitat_type": (
                        "Rainforest / wet forest mosaic"
                        if label != "Native plants"
                        else "Robertson Rainforest / native flora"
                    ),
                    "why_fragmented_rainforest_matters": blurb,
                    "recorded_locally": True,
                    "locality_context": locality,
                    "n_records_in_context": int(row["n_records"]),
                    "year_min": None if pd.isna(row["year_min"]) else int(row["year_min"]),
                    "year_max": None if pd.isna(row["year_max"]) else int(row["year_max"]),
                    "is_threatened": bool(row.get("is_threatened")),
                    "is_sensitive": sensitive,
                    "map_display": (
                        "aggregated_grid_only"
                        if sensitive or bool(row.get("is_threatened"))
                        else "public_point_ok_if_needed"
                    ),
                    "source": "NSW BioNet Species Sightings (public extract in project GPKG)",
                    "evidence_tag": "OBSERVED",
                    "photo_status": "needed",
                    "photo_credit": "",
                }
            )
            picked += 1
    return cards


def _plant_story(near_plants: pd.DataFrame, aoi_plants: pd.DataFrame, profile: dict) -> dict[str, Any]:
    top_near = near_plants.head(25)
    threatened = near_plants[near_plants["is_threatened"] == True]  # noqa: E712
    rainforest_associates = [
        "Doryphora sassafras",
        "Quintinia sieberi",
        "Polyosma cunninghamii",
        "Acacia melanoxylon",
        "Syzygium smithii",
        "Tasmannia insipida",
        "Coprosma quadrifida",
        "Ceratopetalum apetalum",
    ]
    present = []
    pool = pd.concat([near_plants, aoi_plants], ignore_index=True) if len(aoi_plants) else near_plants
    for name in rainforest_associates:
        hit = pool[pool["scientificName"].astype(str).str.startswith(name)]
        if not hit.empty:
            present.append(
                {
                    "scientific_name": str(hit.iloc[0]["scientificName"]),
                    "vernacular_name": str(hit.iloc[0].get("vernacularName") or ""),
                    "n_records_context": int(hit["n_records"].sum()),
                    "evidence_tag": "OBSERVED",
                }
            )
    return {
        "chapter_title": "It's Not Just Where Animals Live",
        "tec_name": profile.get("threatened_ecological_community", {}).get("tec_name"),
        "nsw_status": profile.get("threatened_ecological_community", {}).get("nsw_status"),
        "epbc_status": profile.get("threatened_ecological_community", {}).get("epbc_status"),
        "majority_pct_in_reserve": profile.get("vegetation_in_reserve", {}).get("majority_pct_name"),
        "n_plant_species_within_2km": int(near_plants["scientificName"].nunique()) if len(near_plants) else 0,
        "n_threatened_plant_species_within_2km": int(threatened["scientificName"].nunique())
        if len(threatened)
        else 0,
        "rainforest_character_species_recorded": present,
        "top_plants_within_2km": top_near[
            ["scientificName", "vernacularName", "n_records", "stateConservation", "is_threatened"]
        ].to_dict("records")
        if len(top_near)
        else [],
        "message": (
            "Conserving Robertson Rainforest means protecting the plant community itself — "
            "not only the animals that use it."
        ),
        "evidence_tag": "OBSERVED / PUBLISHED",
    }


def main() -> None:
    settings = load_settings()
    paths = settings["resolved_paths"]
    crs = str(settings["study_area"]["crs_analysis"])
    logger = setup_logging(
        paths["logs_dir"],
        name="phase2_wildlife_plants",
        level=str(settings.get("logging", {}).get("level", "INFO")),
    )
    ensure_dirs(paths["reports_dir"], paths["csv_dir"], paths["interim_dir"], paths["geojson_dir"])

    master = paths["gpkg_dir"] / str(settings.get("outputs", {}).get("master_gpkg", "robertson_conservation.gpkg"))
    logger.info("=== Phase 2: Wildlife + plants ===")
    species = gpd.read_file(master, layer="species_observations_clean")
    reserve = gpd.read_file(master, layer="robertson_nature_reserve")
    reserve = to_analysis_crs(reserve, crs)
    rgeom = unary_union(list(reserve.geometry))

    profile_path = paths["csv_dir"] / "reserve_ecological_profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8")) if profile_path.is_file() else {}

    near_2km = _buffer_subset(species, rgeom, 2000, crs)
    near_5km = _buffer_subset(species, rgeom, 5000, crs)

    aoi_table = _species_table(species)
    near2_table = _species_table(near_2km)
    near5_table = _species_table(near_5km)

    group_aoi = _group_summary(species)
    group_2km = _group_summary(near_2km)
    group_5km = _group_summary(near_5km)

    cards = _pick_cards(near2_table, aoi_table, max_per_group=4)
    plants_near = near2_table[near2_table["taxon_group"] == "Flora"].copy()
    plants_aoi = aoi_table[aoi_table["taxon_group"] == "Flora"].copy()
    plant_story = _plant_story(plants_near, plants_aoi, profile)

    threatened_near = near2_table[near2_table["is_threatened"] == True].copy()  # noqa: E712

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    package = {
        "generated_at_utc": generated,
        "crs_analysis": crs,
        "source": "species_observations_clean (BioNet public) in robertson_conservation.gpkg",
        "ala_status": "disabled in settings — BioNet primary",
        "story_chapter": "03 Who Lives Here? / Who Uses This Landscape?",
        "sensitivity_rule": (
            "Threatened and sensitive taxa must display as aggregated context only in public maps."
        ),
        "group_summary_aoi": group_aoi,
        "group_summary_2km": group_2km,
        "group_summary_5km": group_5km,
        "meet_the_locals_cards": cards,
        "plant_story": plant_story,
        "threatened_species_within_2km_n": int(len(threatened_near)),
        "cartographic_art": {
            "standard": "docs/CARTOGRAPHIC_ART_STANDARD.md",
            "ui_note": (
                "Present as portrait-style species cards beside a soft habitat map — "
                "not a spreadsheet of every BioNet row."
            ),
        },
        "living_atlas": {
            "refresh_species_layer": "python src/03_prepare_refuge.py",
            "refresh_cards": "python src/11_prepare_wildlife_plants.py",
        },
    }

    # Exports
    out_json = paths["csv_dir"] / "wildlife_plants_story.json"
    out_json.write_text(json.dumps(package, indent=2, default=str), encoding="utf-8")

    pd.DataFrame(group_2km).to_csv(paths["csv_dir"] / "taxon_group_summary_2km.csv", index=False)
    pd.DataFrame(group_aoi).to_csv(paths["csv_dir"] / "taxon_group_summary_aoi.csv", index=False)
    near2_table.to_csv(paths["csv_dir"] / "species_summary_2km.csv", index=False)
    threatened_near.to_csv(paths["csv_dir"] / "threatened_species_summary_2km.csv", index=False)
    pd.DataFrame(cards).to_csv(paths["csv_dir"] / "meet_the_locals_cards.csv", index=False)

    # Compact threatened grid already exists; export plant points for non-sensitive flora near reserve (story layer)
    flora_pts = near_2km[
        (near_2km["taxon_group"] == "Flora")
        & (near_2km["is_sensitive"] != True)  # noqa: E712
        & (near_2km["is_threatened"] != True)  # noqa: E712
    ].copy()
    if len(flora_pts) > 5000:
        flora_pts = flora_pts.sample(5000, random_state=42)
    gpkg = paths["interim_dir"] / "phase2_wildlife_plants.gpkg"
    if not flora_pts.empty:
        write_gdf(flora_pts, gpkg, layer="native_plant_observations_public_2km")
        # Also attach to master
        write_gdf(flora_pts, master, layer="native_plant_observations_public_2km")
        processed = paths["processed_dir"] / master.name
        if processed.is_file():
            write_gdf(flora_pts, processed, layer="native_plant_observations_public_2km")

    # Markdown report
    md = [
        "# Phase 2 — Wildlife & plants story package",
        "",
        f"**Generated:** {generated}",
        "",
        "## Concept",
        "",
        "Make habitat connectivity understandable through **real local species**, "
        "and keep plants as central as animals.",
        "",
        "## Taxon groups within 2 km of the reserve",
        "",
        "| Group | Records | Species | Threatened spp. |",
        "|-------|---------|---------|-----------------|",
    ]
    for row in group_2km:
        md.append(
            f"| {row['story_group']} | {row['n_records']} | {row['n_species']} | {row['n_threatened_species']} |"
        )
    md += [
        "",
        f"**Meet the Locals cards:** {len(cards)} (from observed records only)",
        f"**Threatened species (public summary) within 2 km:** {len(threatened_near)}",
        f"**Plant species within 2 km:** {plant_story['n_plant_species_within_2km']}",
        "",
        "## Sample cards",
        "",
    ]
    for card in cards[:8]:
        md.append(
            f"- **{card['common_name']}** (*{card['scientific_name']}*) — {card['story_group']}; "
            f"{card['conservation_status_nsw']}; {card['locality_context']}"
        )
    md += [
        "",
        "## Plant story",
        "",
        plant_story["message"],
        "",
        f"- TEC: {plant_story['tec_name']} ({plant_story['nsw_status']} / EPBC {plant_story['epbc_status']})",
        f"- Majority PCT in reserve: {plant_story['majority_pct_in_reserve']}",
        f"- Rainforest character species with local records: {len(plant_story['rainforest_character_species_recorded'])}",
        "",
        "## Sensitivity",
        "",
        package["sensitivity_rule"],
        "",
        "## ALA",
        "",
        "ALA remains disabled (`ala_enabled: false`). Enable later if a complementary pull is needed; "
        "dedupe against BioNet before adding cards.",
        "",
        "## Cartographic use",
        "",
        package["cartographic_art"]["ui_note"],
        "",
    ]
    (paths["reports_dir"] / "phase2_wildlife_plants.md").write_text("\n".join(md), encoding="utf-8")
    (paths["reports_dir"] / "PHASE2_COMPLETE.md").write_text(
        "\n".join(
            [
                "# Phase 2 complete — Wildlife + plants",
                "",
                f"**Date:** {generated[:10]}",
                "**Status:** Complete for review",
                "",
                "## Deliverables",
                "",
                "- `outputs/csv/wildlife_plants_story.json`",
                "- `outputs/csv/meet_the_locals_cards.csv`",
                "- `outputs/csv/taxon_group_summary_2km.csv`",
                "- `outputs/csv/species_summary_2km.csv`",
                "- `outputs/csv/threatened_species_summary_2km.csv`",
                "- `outputs/reports/phase2_wildlife_plants.md`",
                "- Master layer `native_plant_observations_public_2km` (non-sensitive flora)",
                "- Script `src/11_prepare_wildlife_plants.py`",
                "",
                "## Validation",
                "",
                "1. Open `meet_the_locals_cards.csv` — every scientific name should appear in `species_summary_2km.csv` or AOI table.",
                "2. Confirm no sensitive/threatened card has `map_display=public_point_ok_if_needed`.",
                "3. Plant story TEC names match Phase 1 published listing.",
                "",
                "## Next",
                "",
                "Phase 3 — Rainforest remnants + enriched habitat network attributes.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    logger.info(
        "Phase 2 complete: cards=%s groups_2km=%s plants_2km=%s",
        len(cards),
        group_2km,
        plant_story["n_plant_species_within_2km"],
    )


if __name__ == "__main__":
    main()
