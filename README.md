# Robertson Rainforest — community StoryMap

A short, shareable story for people who care about Robertson, NSW.

**What was lost. What we kept. What still lives. How we can care for it.**

This is **not** a GIS product page. It is an educational StoryMap built from real NSW spatial data: rainforest clearing around Robertson, the small Nature Reserve that remains, the wildlife that still uses remnant pockets, and practical ways people can look after living bush — always as ideas to talk about, never as demands on private land.

---

## Why this exists

Robertson Nature Reserve is only about **5 hectares**, yet it holds living **Robertson Rainforest** — a threatened ecological community beside the village. Around it, most of the historic plateau forest (often called the **Yarrawa Brush**) is gone.

This project asks a simple guiding question:

> What ecological role does Robertson Nature Reserve play today, and where could careful care of other small areas around Robertson strengthen that role?

Maps identify **opportunities for conversation**, not acquisition targets or land-use decisions.

---

## The five-page story

| Page | Title | What you will see |
|------|--------|-------------------|
| 1 · **LOSS** | What Was Lost | Then/now rainforest around the reserve — past cover vs what remains |
| 2 · **KEPT** | What We Kept | The reserve as a small protected piece in mostly cleared country, still near other rainforest |
| 3 · **LIFE** | Life That Needs These Pockets | Threatened plants and animals recorded nearby (public records, never dens or nests) |
| 4 · **CARE** | Ways To Care For Land | Protect bush, weed edges, plant creeks, close short gaps — matched to nearby places |
| 5 · **RESPECT** | Acknowledgement of Country | Country first, then the data sources behind the maps |

Spine: **LOSS → KEPT → LIFE → CARE → RESPECT**

---

## Quick start (Windows)

### 1. Prerequisites

- Python 3.11+ recommended  
- Git + [Git LFS](https://git-lfs.com/) (needed for the master GeoPackage)  
- About **2 GB** free disk for the virtual environment and data

### 2. Clone and install

```powershell
git lfs install
git clone https://github.com/EPR-dev/robertson-ripple-effect.git
cd robertson-ripple-effect
git lfs pull

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Confirm the master data file is present

The StoryMap needs:

`outputs/geopackage/robertson_conservation.gpkg`

If you cloned with Git LFS, this file should download automatically.  
If it is missing, ask the project owner for the GeoPackage (about 170 MB).

### 4. Launch the StoryMap

```powershell
.\start-dashboard.ps1
```

Or:

```powershell
.\.venv\Scripts\python.exe -m streamlit run dashboard\app.py --server.headless true
```

Open the URL Streamlit prints (often `http://localhost:8501`).

---

## How to give feedback

You do **not** need GIS skills. Please walk the five pages and note:

1. **Clarity** — Does each page make one clear idea? Anything confusing?
2. **Tone** — Does it sound like a community story, or like a technical report?
3. **Trust** — Are the honesty notes enough (modelled past forest, public wildlife records, no private-land instructions)?
4. **CARE page** — Are the land-care options useful? Missing anything local people would recognise?
5. **What to cut** — If we had to remove one section, which one?
6. **What to add** — Photos, local stories, group contacts (with permission)?

Send feedback as comments in email, a shared doc, or GitHub Issues — whatever is easiest.

---

## What the maps are based on (plain language)

| Theme | Sources (examples) |
|--------|---------------------|
| Rainforest past / present | NSW State Vegetation Type Map (SVTM) |
| Nature Reserve | NSW NPWS estate |
| Roads, water, boundaries | NSW Spatial Services |
| Wildlife records | NSW BioNet (public extracts; sensitive locations removed) |
| Elevation | Copernicus GLO-30 |
| Basemaps | OpenStreetMap / CARTO, Esri imagery |

Numbers are labelled carefully:

- **Seen on maps** — present in trusted public layers  
- **Published** — from literature or listings  
- **Measured** — calculated from the maps  
- **Modelled** — informed estimate (e.g. pre-clear rainforest), not a field survey  

Important limits:

- Pre-clear rainforest is a **model**, not a surveyed historic Yarrawa Brush boundary.  
- Wildlife maps use **public aggregated records** — never dens, nests, or precise sensitive sites.  
- CARE places are **ideas to check**, not instructions for private land.  
- Public / Crown land on the map is **not** automatic permission to plant.

Logo credits: `dashboard/assets/acknowledgement/CREDITS.txt`

---

## Project structure

```text
robertson-ripple-effect/
├── README.md                 ← you are here
├── requirements.txt
├── start-dashboard.ps1       ← launch the StoryMap
├── config/settings.yaml      ← paths and download settings
├── dashboard/
│   ├── app.py                ← Streamlit StoryMap
│   ├── story_v1.py           ← chapter text and map recipes
│   └── assets/               ← logos, photos, acknowledgement art
├── data/
│   ├── raw/                  ← downloads (not in Git)
│   ├── interim/              ← working files (not in Git)
│   ├── processed/            ← processed layers (not in Git)
│   └── reference/            ← data inventory CSVs (in Git)
├── src/                      ← Python prep pipeline
├── outputs/
│   ├── geopackage/           ← master GPKG (Git LFS)
│   ├── csv/                  ← summaries / story JSON
│   ├── reports/              ← phase notes and QA
│   └── twin_lakes/           ← optional living-feed package
└── docs/                     ← design notes, runbooks, handoffs
```

---

## For reviewers who only want the story

1. Install Python + Git LFS, clone, `pip install -r requirements.txt`.  
2. Run `.\start-dashboard.ps1`.  
3. Click **Begin the story** and move through LOSS → RESPECT.  
4. Use **Story map** vs **Satellite photo** above the maps when you want to ground-check.

You do not need ArcGIS Pro to review the community StoryMap.

---

## For geospatial practitioners

| Topic | Where to look |
|--------|----------------|
| Analysis CRS | **EPSG:7856** (GDA2020 / MGA Zone 56) — metres for distance and area |
| Master package | `outputs/geopackage/robertson_conservation.gpkg` |
| Data inventory | `data/reference/data_sources.csv` |
| Reserve profile | `outputs/reports/reserve_ecological_profile.md` |
| Implementation plan | `docs/implementation-plan.md` |
| Cartographic art standard | `docs/CARTOGRAPHIC_ART_STANDARD.md` |
| Optional ArcGIS corridors | `docs/arcgis_handoff.md` / `docs/PHASE7_ARCGIS_PRO_RUNBOOK.md` |

Rebuild pipeline (only if regenerating data):

```powershell
.\.venv\Scripts\Activate.ps1
# Run numbered scripts in src/ as documented in docs/implementation-plan.md
python src/07_export_master.py
.\start-dashboard.ps1
```

Optional living feeds refresh:

```powershell
.\refresh-living-feeds.ps1
```

---

## Sharing this repo

### Already using Git LFS?

Large files (especially `*.gpkg`) are tracked with **Git LFS**. After clone:

```powershell
git lfs pull
```

### Publishing to GitHub (project owner)

Public repo (already published):

https://github.com/EPR-dev/robertson-ripple-effect

Tell reviewers to install Git LFS before cloning.

### If someone cannot use Git LFS

Zip and share privately (OneDrive / USB):

- `outputs/geopackage/robertson_conservation.gpkg`  
- optionally `outputs/twin_lakes/living_layers.gpkg`

They can drop those files into the matching folders after cloning the code.

---

## Honesty principles (please keep these if you reuse the story)

1. Do not invent a historic Yarrawa Brush boundary.  
2. Do not show dens, nests, or sensitive wildlife locations.  
3. Do not present CARE places as orders for private land.  
4. Do not invent tourism dollar figures without local evidence.  
5. Separate **extraction → transformation → analysis → story**.  
6. Prefer plain language for the public StoryMap; keep technical detail in `docs/`.

---

## Status

| Area | Status |
|------|--------|
| Community StoryMap (5 pages) | Ready for feedback |
| Master GeoPackage + reports | Built locally; GPKG via Git LFS |
| Optional ArcGIS corridor scenarios | Documented; not required for review |
| Local photos / artist credits | Partial — confirm licences before wide public release |

---

## Contact / next steps after feedback

After a few people have walked the story, typical next steps are:

1. Tighten wording from reviewer notes  
2. Add licensed local photos (CARE / acknowledgement)  
3. Decide whether a public hosting option (Streamlit Cloud, council intranet, etc.) is wanted  
4. Only then consider ArcGIS Online / Esri StoryMaps packaging if needed  

Thank you for reading carefully and for helping keep the story honest for Robertson.
