# Cartographic Art Standard

**Status:** Binding design rule for the Robertson Rainforest Conservation StoryMap  
**Companion:** Living data refresh (see § Living atlas)

This project must not look like a GIS technician dashboard.  
It must look like **cartographic art with real data underneath**.

---

## Design outcome

Every map frame should feel closer to:

- a carefully printed landscape poster
- an Esri StoryMap sidecar plate
- a nature documentary still with geography

Than to:

- ArcGIS Pro default symbology
- a BI dashboard of charts and layer toggles
- a “tech demo” of every available field

Data remains the authority. Beauty is how we present it.

---

## Visual principles

1. **One idea per frame** — each map answers one narrative question.
2. **Reserve as the seed** — start tight; zoom outward with the story.
3. **Atmosphere over chrome** — soft paper / mist / deep canopy tones; minimal UI chrome.
4. **Typography with character** — display serif for titles; clean sans for body (already Fraunces + Outfit).
5. **Generous whitespace** — short narrative, large map, breathing room.
6. **Motion with purpose** — progressive zoom, fade-in remnants, pulse on the reserve; no busy animations.
7. **Evidence without clutter** — OBSERVED / PUBLISHED / CALCULATED / MODELLED as quiet labels, not badges everywhere.
8. **Photography + map dialogue** — full-bleed photos where they earn the emotion; maps carry the geography.
9. **No default GIS look** — avoid rainbow ramps, thick black outlines on every polygon, dense legend boxes, cyan selection halos.
10. **Living, not frozen** — maps and metrics should refresh when newer public data arrives (see Living atlas).

### Palette (working)

| Token | Role |
|-------|------|
| Deep canopy `#1e3a28` | Titles, reserve emphasis |
| Moss `#3f6f4a` | Extant rainforest / habitat |
| Mist / paper `#d7e2d4`–`#e4ebe3` | Background atmosphere |
| Dawn gold `#c9a24a` | Opportunity / “look here” accent (sparingly) |
| Ember `#e76f51` | Barriers / caution (roads, gaps) — never alarmist red floods |

### Symbology rules

| Layer | Art direction |
|-------|----------------|
| Reserve | Single dark outline + soft fill; may pulse once on entry |
| Rainforest remnants | Soft moss washes; no harsh edges at overview scales |
| Pre-clear model | Very light wash or dashed memory layer — clearly MODELLED |
| Habitat patches | Grouped by story role, not by every PCT ID |
| Water | Thin cool lines; riparian as gentle halo |
| Roads / barriers | Ember only for high barrier class; fade low hierarchy |
| Opportunity areas | Gold edges or soft hatch — never solid “target” fills that feel accusatory |
| Species | Aggregated grids / soft heat — never precise sensitive points |

---

## Living atlas (change over time)

The prototype is a **living conservation atlas**, not a one-off map export.

| Feed / layer family | Refresh expectation | Source |
|---------------------|---------------------|--------|
| BioNet / species richness | Periodic re-pull + re-aggregate | NSW BioNet |
| iNaturalist neighbours | Living feed script | iNaturalist API |
| Greenness / canopy proxy | Seasonal / on-demand | DEA / Planetary Computer |
| Fire context | Near-real-time watch | RFS / FIRMS |
| SVTM / NPWS / hydro | When new editions publish | NSW SEED / Spatial |
| Opportunity + profile metrics | Recompute after base layers update | Project pipeline |

### Engineering rules for living data

1. Raw downloads stay immutable under `data/raw/` with download dates.
2. Re-runs write new interim/processed outputs — never overwrite raw without a new dated cache policy.
3. `story_package.json` (Twin Lakes) carries refresh timestamps for the StoryMap.
4. UI should surface **“Updated …”** dates near living metrics.
5. If a feed fails, show last-good data + honest status — never invent newer numbers.
6. Version narrative claims that depend on counts (“X threatened species nearby”) so stale screenshots do not silently lie.

---

## StoryMap experience rules

- Scroll-driven chapters, not a control panel.
- Sticky / sidecar maps where the text advances and the map evolves.
- Metric callouts as quiet typography, not KPI scorecards.
- Parcel / opportunity explorer is secondary to the story — available, not dominant.
- Conceptual futures clearly labelled **Conceptual ecological restoration scenario**.

---

## What “done” looks like for a map frame

A reviewer should be able to say:

> “This feels like a beautiful story about a rainforest landscape — and I trust the numbers.”

Not:

> “This looks like someone exported every layer from a geodatabase.”
