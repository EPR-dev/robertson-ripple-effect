# Phase 4 complete — Missing links (habitat connection opportunities)

**Date:** 2026-08-11  
**Status:** Complete for review

## GIS concept

**Potential habitat connections** are places where geometry suggests a relatively small
intervention could link existing vegetation. Without tracking data, these are **not**
proven wildlife corridors.

## Opportunity types

| Type | Meaning |
|------|---------|
| SHORT_50M / SHORT_MED / NEAR_PAIR | Nearby patch pairs with a measurable gap |
| ROAD_GAP | Habitat on both sides of a road barrier |
| CREEK_GAP | Riparian cleared gap component |
| STEPPING_STONE | Small patch between larger patches |
| REMNANT_EXPANSION | Cleared fringe beside rainforest remnant |

## Results

- **Total opportunities:** 961
- **By type:** {'SHORT_50M': 293, 'SHORT_MED': 262, 'CREEK_GAP': 120, 'STEPPING_STONE': 100, 'ROAD_GAP': 80, 'REMNANT_EXPANSION': 58, 'NEAR_PAIR': 48}

## Deliverables

- Master layer `habitat_connection_opportunities`
- `outputs/csv/habitat_connection_opportunities.csv`
- `outputs/geojson/habitat_connection_opportunities.geojson`
- `src/13_prepare_habitat_gaps.py`

## Cartographic art

Draw gaps as soft dawn-gold stitches between moss habitat islands — delicate, hopeful,
never like hazard zoning.

## Next

Phase 5 — Ecological Opportunity Areas + Parcel Explorer attributes.
