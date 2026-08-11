# Phase 6 — Unweighted opportunity components

Unweighted opportunity component. Mapped independently — NOT a Restoration Opportunity Index score.

## Thresholds (from `config/settings.yaml`)

| Parameter | Value |
|-----------|-------|
| near_protected_m | 500 |
| near_core_m | 250 |
| near_reserve_m | 1000 |
| isolated_nn_m | 200 |
| isolated_influence_m | 500 |
| plantable_slope_deg | 15 |

## Components

| Field | Meaning |
|-------|---------|
| `near_protected` | Within near_protected_m of NPWS protected area |
| `near_reserve` | Within near_reserve_m of Robertson Nature Reserve |
| `near_core` | Within near_core_m of core habitat (rainforest/wet sclerophyll patches) |
| `on_cleared` | Intersects SVTM cleared / non-native contrast mask |
| `riparian_gap` | Within 100 m of stream AND cleared AND not on core habitat |
| `patch_gap_edge` | Near core habitat edge, cleared, not already core |
| `isolated_patch_context` | Near relatively isolated core patch, cleared, not core |
| `on_public_land` | Intersects Crown land or NPWS protected area |
| `on_basalt_volcanic` | Intersects basalt/latite/igneous geology (association only) |
| `plantable_slope` | Slope at/under plantable_slope_deg (or unknown) |

## Continuous fields
- `dist_to_protected_m`, `dist_to_reserve_m`, `dist_to_core_m`, `dist_to_isolated_core_m`
- Plus carried Phase 5: `dist_to_stream_m`, `slope_deg`, `elev_m`

## Outputs
- `opportunity_grid` — cell-level flags/distances
- `component_polygons` — dissolved areas for selected components
- `crown_land` — clipped Crown land tenure
- Diagnostic intersections CSV — **not** an index

## Next (not this phase)
- ArcGIS / analyst-approved weights → Restoration Opportunity Index
- Scenario B restoration targeting using these components + corridor products
