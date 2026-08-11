# ArcGIS StoryMap handoff — Robertson Rainforest

**Prototype:** Streamlit cartographic StoryMap (`dashboard/app.py`)  
**Design standard:** [`CARTOGRAPHIC_ART_STANDARD.md`](CARTOGRAPHIC_ART_STANDARD.md)  
**Master GPKG:** `outputs/geopackage/robertson_conservation.gpkg`  
**Living feeds:** `outputs/twin_lakes/`

Rebuild this experience in Esri StoryMaps using one web map (or chapter web maps) plus sidecar / map tour blocks. Keep the **cartographic art** language — soft moss remnants, dawn-gold opportunities, quiet metrics.

---

### CHAPTER
01 · The Little Reserve

### PURPOSE
Meet Robertson Nature Reserve; show transparent ecological profile metrics.

### NARRATIVE
One small gazetted seed beside town; PCT + TEC context; quiet callouts (area, rings, water, nearby spp).

### MAP EXTENT
Tight zoom on reserve + ~1–2 km halo.

### ACTIVE LAYERS
`robertson_nature_reserve`, `rainforest_extant` (soft), distance rings optional

### HIDDEN LAYERS
Opportunity, threatened grid, roads

### REQUIRED ARCGIS WEB MAP
Reserve close-up web map (soft paper / imagery toggle)

### SUGGESTED INTERACTION
Reserve pulse on entry; scroll reveals metric callouts

### DATA SOURCE
NPWS estate; SVTM; `reserve_ecological_profile`

### ANALYSIS STATUS
Python complete (`src/10_build_reserve_profile.py`)

### VISUAL ASSETS NEEDED
Hero rainforest photo; reserve ground photo

---

### CHAPTER
02 · The Rainforest That Survived

### PURPOSE
Then/now rainforest — modelled loss vs mapped remnants.

### NARRATIVE
Yarrawa Brush ~2,500 ha PUBLISHED text; SVTM pre-clear MODELLED; extant OBSERVED.

### MAP EXTENT
~5 km surround

### ACTIVE LAYERS
`rainforest_preclear_modelled`, `rainforest_extant`, reserve

### HIDDEN LAYERS
Species, opportunities

### REQUIRED ARCGIS WEB MAP
Then/now swipe web map

### SUGGESTED INTERACTION
Swipe / before-after

### DATA SOURCE
SVTM extant + pre-clear; literature area

### ANALYSIS STATUS
Complete (do not fabricate Yarrawa boundary)

### VISUAL ASSETS NEEDED
Historic photo if rights clear; contemporary canopy photo

---

### CHAPTER
03 · Who Lives Here?

### PURPOSE
Wildlife + plants as the reason connectivity matters.

### NARRATIVE
Meet the Locals cards; plant community story; aggregated threatened context.

### MAP EXTENT
~2–5 km

### ACTIVE LAYERS
`threatened_species_aggregated`, rainforest, reserve

### HIDDEN LAYERS
Precise points for sensitive taxa (never)

### REQUIRED ARCGIS WEB MAP
Refuge web map

### SUGGESTED INTERACTION
Species cards sidecar; optional express map

### DATA SOURCE
BioNet clean; `wildlife_plants_story.json`

### ANALYSIS STATUS
Python complete (`src/11_prepare_wildlife_plants.py`)

### VISUAL ASSETS NEEDED
Licensed species photos for cards

---

### CHAPTER
04 · Beyond the Boundary

### PURPOSE
Zoom out to habitat, creeks, roads.

### ACTIVE LAYERS
`core_habitat_patches`, `hydro_lines`, high roads, reserve

### ANALYSIS STATUS
Complete

### VISUAL ASSETS NEEDED
Village / farm / remnant mosaic photo

---

### CHAPTER
05 · Islands of Green

### PURPOSE
Fragmentation and patch isolation.

### ACTIVE LAYERS
`rainforest_patches`, `core_habitat_patches`, roads

### DATA SOURCE
Enriched patches (`src/12_enrich_habitat_network.py`)

### ANALYSIS STATUS
Complete

---

### CHAPTER
06 · The Wildlife Network

### PURPOSE
Potential habitat connections (not tracked movement).

### ACTIVE LAYERS
Core patches, hydro, roads_barriers

### ANALYSIS STATUS
Python prep complete; ArcGIS corridors pending

---

### CHAPTER
07 · What Does Five Hectares Do?

### PURPOSE
Scenario A — network with vs without reserve.

### ACTIVE LAYERS
Reserve + core (placeholder until ArcGIS)

### ANALYSIS STATUS
**ArcGIS Pro required**

### VISUAL ASSETS NEEDED
Before/after network graphics from Pro

---

### CHAPTER
08 · The Other Little Pieces

### PURPOSE
Small patches (&lt;5 ha) and location-driven value.

### ACTIVE LAYERS
`small_habitat_pieces`, rainforest, edge opportunities

### ANALYSIS STATUS
Complete

---

### CHAPTER
09 · The Missing Links

### PURPOSE
Typed habitat connection opportunities.

### ACTIVE LAYERS
`habitat_connection_opportunities` (symbolize by type), core

### ANALYSIS STATUS
Python complete (`src/13_prepare_habitat_gaps.py`)

### SUGGESTED INTERACTION
Pop-ups with gap length / why_it_matters

---

### CHAPTER
10 · What Could One Hectare Do?

### PURPOSE
Scenario B — connectivity gain per hectare.

### ANALYSIS STATUS
**ArcGIS Pro required**

---

### CHAPTER
11 · Where Should We Look Next?

### PURPOSE
Ecological Opportunity Areas + Parcel Explorer.

### ACTIVE LAYERS
`ecological_opportunity_areas` (by type), public land context

### HIDDEN LAYERS
Owner names / cadastre labels (do not publish)

### ANALYSIS STATUS
Python complete (`src/14_prepare_opportunity_areas.py`)

### SUGGESTED INTERACTION
Click AREA_ID → metrics card

---

### CHAPTER
12 · A More Connected Robertson

### PURPOSE
Conceptual future + living feeds; people remain in the landscape.

### ACTIVE LAYERS
Rainforest, hydro, opportunity stitches, reserve

### ANALYSIS STATUS
Conceptual MODELLED + living OBSERVED feeds

### VISUAL ASSETS NEEDED
Community / village closing photograph

---

## Global rules for Esri rebuild

1. Evidence tags: OBSERVED / PUBLISHED / CALCULATED / MODELLED  
2. Opportunity language only — no acquisition framing  
3. Sensitive species: grid aggregates only  
4. Living atlas: show “Updated …” dates from JSON packages  
5. Cartography: art first — see design standard  
