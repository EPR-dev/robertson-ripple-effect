# Phase 2 complete — Wildlife + plants

**Date:** 2026-08-11
**Status:** Complete for review

## Deliverables

- `outputs/csv/wildlife_plants_story.json`
- `outputs/csv/meet_the_locals_cards.csv`
- `outputs/csv/taxon_group_summary_2km.csv`
- `outputs/csv/species_summary_2km.csv`
- `outputs/csv/threatened_species_summary_2km.csv`
- `outputs/reports/phase2_wildlife_plants.md`
- Master layer `native_plant_observations_public_2km` (non-sensitive flora)
- Script `src/11_prepare_wildlife_plants.py`

## Validation

1. Open `meet_the_locals_cards.csv` — every scientific name should appear in `species_summary_2km.csv` or AOI table.
2. Confirm no sensitive/threatened card has `map_display=public_point_ok_if_needed`.
3. Plant story TEC names match Phase 1 published listing.

## Next

Phase 3 — Rainforest remnants + enriched habitat network attributes.
