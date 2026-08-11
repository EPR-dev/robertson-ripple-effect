# Phase 5 complete — Ecological Opportunity Areas

**Date:** 2026-08-11  
**Status:** Complete for review

## Philosophy

GIS identifies **ecological opportunities**, not land-use decisions.  
Public IDs are anonymous (`AREA_001` …). No owner names.

## Types

{'CONNECT': 26, 'RIPARIAN': 18, 'PROTECT': 3, 'RESTORE': 2, 'BUFFER': 1}

## Deliverables

- Master layer `ecological_opportunity_areas`
- `outputs/csv/ecological_opportunity_areas.csv`
- `outputs/csv/parcel_explorer.json` (Parcel Explorer payload)
- `outputs/geojson/ecological_opportunity_areas.geojson`
- `src/14_prepare_opportunity_areas.py`

## Parcel Explorer fields (all calculated)

area_id, existing_vegetation_ha, nearest_rainforest_remnant_m, habitat_patches_nearby,
potential_habitat_connected_ha, waterway_distance_m, native_species_recorded_nearby,
threatened_species_context, opportunity_type, why_it_matters

## Cartographic art

Soft dawn-gold outlines by type; never solid “target” fills. Click reveals a quiet card.

## Next

Phase 6 — StoryMap web prototype (12 chapters, cartographic art).
