# Evolving map choreography

The Streamlit StoryMap uses **one Folium map** that updates as chapters advance
(ArcGIS StoryMap sidecar pattern).

## Source of truth

[`dashboard/story_v1.py`](../dashboard/story_v1.py) → `CHAPTER_MAP_RECIPES`

Each chapter declares:

| Field | Role |
|-------|------|
| `fit` | `close` → `near` → `context` → `aoi` (grow the map) |
| `layers` | Default visible layers |
| `hero` / `context` | Paint emphasis |
| `basemap` | Soft paper (shared); Satellite only for Ch01 |
| `legend_beats` | Must match what is painted |
| `map_sentence` | Thesis shown above the map |

## Runtime

[`dashboard/app.py`](../dashboard/app.py)

- `render_map_thesis_bar` — sentence + legend
- `render_evolving_map` — Folium map from recipe + optional Explore toggles
- PNG story plates are **not** the live media path

## ArcGIS StoryMap later

Rebuild the same chapter list as a Sidecar: same extents, layer visibility, and
legend copy, loading layers from `robertson_conservation.gpkg`.
