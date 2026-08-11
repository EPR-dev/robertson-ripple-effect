# Phase 4 — Habitat network rules (Python prep)

These layers are **analysis-ready inputs** for ArcGIS connectivity work.
They are **not** a connectivity model and **not** a suitability / opportunity score.

## Habitat patches

| Rule | Value |
|------|-------|
| Source | Phase 2 `native_vegetation` (SVTM classified PCTs; excludes Not classified) |
| Pre-dissolve | `make_valid` + simplify **1 m** (topology-preserving; dissolve performance) |
| Gap-close | Buffer **15 m** → dissolve → negative buffer (merge near fragments) |
| Minimum patch area | **0.5 ha** |
| Core habitat filter | veg_form/class contains: Rainforest, Wet Sclerophyll |
| CRS | Analysis CRS from settings (EPSG:7856) |

### Layers
- `habitat_patches` — all classified native vegetation patches after rules
- `core_habitat_patches` — rainforest + wet sclerophyll focus (corridor candidate habitat)
- `rainforest_patches` — rainforest-only patches (story layer)

### Patch attributes (proxies only)
- `area_ha`, `perimeter_m`, `shape_isoperimetric`
- `nn_distance_m` — edge-to-edge distance to nearest other patch (search capped)
- `n_patches_within_isolation_r` — count of other patches within isolation radius
- `dist_to_reserve_m`, `touches_reserve` — relationship to Robertson Nature Reserve

## Road barriers

| Field | Meaning |
|-------|---------|
| `barrier_class` | high / medium / low from NSW `functionhierarchy` |
| `cost_hint` | Ordinal hint for ArcGIS Cost Distance setup (higher = stronger barrier candidate) |

**Explicitly not included:** species-specific resistance, traffic volume calibration,
or any weighted Restoration Opportunity Index.

## ArcGIS handoff (your analysis)
1. Build cost surface from `roads_barriers.cost_hint` (+ optional land-cover costs you define)
2. Least-cost corridors / linkage mapper style products between `core_habitat_patches`
3. Scenario A — network with Robertson Nature Reserve removed
4. Scenario B — where small restoration yields largest connectivity gain
5. Fragmentation / equivalent connected area metrics as needed

## Patch summary (this run)

```
habitat_class  n_patches  total_area_ha  median_area_ha  median_nn_distance_m  n_touching_reserve
         core        784       17387.17            1.27                  46.2                   1
       native        702       32525.70            1.14                  45.4                   1
   rainforest        481        5300.49            1.41                  55.0                   1
```
