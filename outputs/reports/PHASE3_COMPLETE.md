# Phase 3 complete — Habitat network enrichment

**Date:** 2026-08-11  
**Status:** Complete for review

## GIS concept

**Habitat patches** are dissolved native-vegetation polygons used as nodes in a landscape network.
Attributes here describe patch size, neighbours, protection, water proximity and biodiversity context.
They are **not** proof of wildlife movement.

## Deliverables

- Enriched `rainforest_patches` / `core_habitat_patches` in master GPKG
- `small_habitat_pieces` (< 5 ha) for “Other Little Pieces”
- `outputs/csv/rainforest_patches_enriched.csv`
- `outputs/csv/small_habitat_pieces.csv`
- `outputs/csv/habitat_network_summary.json`
- `src/12_enrich_habitat_network.py`

## Summary

| Layer | Count | Notes |
|-------|------:|-------|
| Rainforest patches | 481 | 5300.49 ha total |
| Core habitat patches | 784 | rainforest + wet sclerophyll |
| Small pieces (<5 ha) | 909 | 1383.65 ha |

## Validation

1. Spot-check 5 rainforest patches: area_ha ≈ geometry area/10000 in EPSG:7856.
2. Confirm protection_status = protected_npws where patch intersects NPWS estate.
3. Confirm small_habitat_pieces all have area_ha < 5.

## Next

Phase 4 — Connectivity prep + typed habitat connection opportunities (gaps).
