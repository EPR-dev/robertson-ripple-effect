# ArcGIS handoff — The Ripple Effect (Phase 7)

**Date:** 2026-08-10  
**Master GeoPackage:** `C:\Users\thesn\Gis_Workstation\robertson-ripple-effect\outputs\geopackage\robertson_conservation.gpkg`  
**Compiled grid CSV:** `C:\Users\thesn\Gis_Workstation\robertson-ripple-effect\outputs\csv\analysis_grid_metrics.csv`  
**Terrain rasters:** `C:\Users\thesn\Gis_Workstation\robertson-ripple-effect\outputs\raster\phase5`

## What Python prep has delivered

| Story beat | Key layers in master GPKG |
|------------|---------------------------|
| Reserve / AOI | `study_area`, `context_aoi`, `robertson_nature_reserve`, `protected_areas`, `lga`, `roads` |
| Remnant | `native_vegetation`, `rainforest_extant`, `wet_sclerophyll_extant`, `rainforest_preclear_modelled`, `cleared_or_non_native` |
| Refuge | `species_observations_clean`, `threatened_species_aggregated`, biodiv fields on `analysis_grid_metrics` |
| Network | `habitat_patches`, `core_habitat_patches`, `rainforest_patches`, `roads_barriers` |
| Ripple | `hydro_lines`, `hydro_areas`, `riparian_buffers`, `soil_landscapes`, `geology_rock_units`, `bushfire_prone_land` |
| Opportunity | `component_polygons`, `crown_land`, opportunity flags on `analysis_grid_metrics` |

## Compiled grid (`analysis_grid_metrics`)

250 m cells with:
- Biodiversity counts / richness (public observations; effort-biased)
- Threatened/sensitive **grid aggregates only**
- Landscape: stream distance, riparian flags, elev/slope/aspect, soil, geology, fire
- Unweighted opportunity components (no ROI score)

## ArcGIS analysis (optional / deferred)

Local briefing now uses the Streamlit dashboard (`dashboard/app.py`) on the master GPKG.
ArcGIS remains available later if you want:

1. **Cost surface** from `roads_barriers.cost_hint` (+ any land costs you document)
2. **Least-cost corridors** between `core_habitat_patches`
3. **Scenario A** — habitat network with `robertson_nature_reserve` removed
4. **Scenario B** — where small restoration yields largest connectivity gain (use `riparian_gap`, `patch_gap_edge`, `isolated_patch_context`)
5. **Weighted Restoration Opportunity Index** — only after agreeing weights on Phase 6 components
6. Cartographic terrain products (optional polish beyond Python slope/aspect)

## Do not

- Treat Python `cost_hint` or opportunity flags as a finished ecological score
- Publish precise sensitive species points (use `threatened_species_aggregated`)
- Label modelled pre-clear rainforest as a surveyed Yarrawa Brush boundary
- Claim reserve-driven regional climate change

## Suggested load order in ArcGIS Pro

1. Add `robertson_conservation.gpkg`
2. Symbolize story groups (Reserve → Remnant → Refuge → Network → Ripple → Opportunity)
3. Add rasters from `phase5/` (dem_clip, slope_deg, aspect_deg)
4. Run corridor / scenario tools; write results to `data/processed/`
5. Hand finished products to Phase 8 dashboard packaging

## QA

See `outputs/reports/data_quality_report.csv` and `outputs/reports/phase7_layer_inventory.csv`.
