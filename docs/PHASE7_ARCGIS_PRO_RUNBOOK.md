# Phase 7 — ArcGIS Pro analysis runbook

**Status:** Ready for you to run in ArcGIS Pro  
**Inputs:** `outputs/geopackage/robertson_conservation.gpkg`  
**CRS:** EPSG:7856 (GDA2020 / MGA Zone 56)  
**Python prep already done:** patches, barriers (`cost_hint`), gaps, opportunity areas

This phase produces the modelled connectivity products the StoryMap must not invent in Cursor.

---

## Decision outcome

Answer two questions with transparent metrics:

1. **Scenario A:** Does temporarily removing Robertson Nature Reserve from the habitat network change connectivity measures in a measurable way?
2. **Scenario B:** Where could ~1 ha of restoration produce the largest **connectivity gain per hectare**?

Report modest results honestly.

---

## GIS concept

**Least-cost / resistance modelling** estimates relative landscape permeability.  
It is **not** GPS tracking of animals. Label all outputs:

> potential habitat connections / modelled connectivity pathways

---

## Setup

1. ArcGIS Pro 3.x with Spatial Analyst (and preferably Linkage Mapper or Cost Distance / Optimal Path tools).
2. Create project `robertson_rainforest_connectivity.aprx` under `outputs/maps/` or your Pro folder.
3. Add master GPKG layers:
   - `robertson_nature_reserve`
   - `core_habitat_patches`
   - `rainforest_patches`
   - `roads_barriers`
   - `habitat_connection_opportunities`
   - `ecological_opportunity_areas`
   - `cleared_or_non_native` (optional cost)
   - `hydro_lines` / `riparian_buffers` (optional lower resistance)
4. Confirm all layers are EPSG:7856 before distance tools.

---

## Task checklist

### 7.1 Cost / resistance surface

- [ ] Convert `roads_barriers.cost_hint` to raster (or Euclidean distance → reclass)
- [ ] Add land-cover costs you document (e.g. cleared high, native low, riparian medium-low)
- [ ] Export `outputs/raster/phase7/resistance.tif`
- [ ] Write `outputs/reports/phase7_resistance_rules.md` listing every cost value

**Failure mode:** Using raw road presence without hierarchy over-penalises tracks.  
**Validate:** Visually check high costs follow highways; riparian not blocked by default.

### 7.2 Least-cost pathways (potential connections)

- [ ] Sources/destinations: `core_habitat_patches` (or rainforest subset near Robertson)
- [ ] Run Cost Distance / Optimal Corridor / Linkage Mapper equivalent
- [ ] Export corridors as `data/processed/modelled_connectivity_pathways.gpkg`
- [ ] Attribute: from_patch, to_patch, cost, length_m, method, evidence_tag=`MODELLED`

### 7.3 Scenario A — without the reserve

- [ ] Copy core habitat; erase / remove cells intersecting `robertson_nature_reserve`
- [ ] Re-run the same corridor / graph metrics
- [ ] Compare: connected component size, mean NN, corridor cost between neighbours
- [ ] Export table `outputs/csv/scenario_a_with_vs_without_reserve.csv`
- [ ] One-paragraph honest interpretation for StoryMap Ch 07

### 7.4 Scenario B — one hectare tests

- [ ] Select 5–15 candidate 1 ha polygons from:
  - `habitat_connection_opportunities` (SHORT_50M, CREEK_GAP, STEPPING_STONE)
  - `ecological_opportunity_areas` (CONNECT / RIPARIAN)
- [ ] For each: add polygon to habitat, recompute metric, record delta
- [ ] Compute **connectivity_gain_per_ha** = Δmetric / area_ha
- [ ] Export `outputs/csv/scenario_b_connectivity_gain_per_ha.csv`
- [ ] Map top candidates for StoryMap Ch 10

### 7.5 Optional weighted opportunity index

- [ ] Only after reviewing unweighted factors
- [ ] Document weights in `outputs/reports/phase7_opportunity_weights.md`
- [ ] Never present as land-use decisions

### 7.6 Cartography for StoryMaps

- [ ] Soft moss symbology for habitat; dawn-gold for pathways/opportunities
- [ ] Share as AGOL web maps named per `docs/storymap_handoff.md`
- [ ] Export web map IDs into the handoff file

---

## Outputs expected back into Cursor

| File | Used by |
|------|---------|
| `scenario_a_with_vs_without_reserve.csv` | Ch 07 narrative |
| `scenario_b_connectivity_gain_per_ha.csv` | Ch 10 narrative |
| `modelled_connectivity_pathways.gpkg` | Ch 06 / 09 maps |
| Web map IDs | Phase 8 Esri StoryMap |

When these exist, re-run a small Python binder script (to add) or paste metrics into `story_package.json`.

---

## Interview talking points

- Why resistance surfaces are hypotheses
- Difference between structural and functional connectivity
- Why Scenario A might show a small effect and still leave the reserve valuable as TEC habitat
