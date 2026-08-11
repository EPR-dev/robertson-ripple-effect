# ArcGIS handoff — Phase 4 network inputs

## Inputs (GeoPackage)
`data/interim/phase4_network.gpkg`

| Layer | Use |
|-------|-----|
| `habitat_patches` | Full native remnant network units |
| `core_habitat_patches` | Preferred terminals / habitat for corridor analysis |
| `rainforest_patches` | Rainforest story / reserve context |
| `roads_barriers` | Barrier lines with `cost_hint` / `barrier_class` |
| `study_area` / `robertson_nature_reserve` | AOI + Scenario A removal feature |

## Suggested ArcGIS workflow
1. **Cost surface** — rasterize `cost_hint` (and any additional land costs you define). Keep a written cost table.
2. **Cost distance / corridors** — between `core_habitat_patches` (or selected large patches).
3. **Scenario A** — erase / mask out `robertson_nature_reserve` from habitat and re-run corridors.
4. **Scenario B** — test restoration slices (e.g. gaps with high `nn_distance_m` between large core patches).
5. Export corridor / fragmentation products back into `data/processed/` for Phase 7–8 packaging.

## Do not
- Treat Python `cost_hint` as a finished ecological resistance model
- Publish a weighted opportunity index before Phase 6 unweighted components exist
