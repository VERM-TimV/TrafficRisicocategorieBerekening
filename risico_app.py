"""
risico_app.py — Risico Categorie Berekening (Streamlit UI)
===========================================================
Web interface voor risico_categorie_berekenen.py, gestyled naar vermeulengroep.com.

Uitvoeren:
    streamlit run risico_app.py

Vereisten:
    pip install streamlit pandas geopandas folium pyproj shapely openrouteservice python-dotenv numpy streamlit-folium
"""

import os
import io
import tempfile
import logging
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()  # Loads ORS_KEY (and any other vars) from .env in the project root

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# ---------------------------------------------------------------------------
# Static file paths — edit these to match your server layout
# ---------------------------------------------------------------------------

STATIC_DIR        = Path("Static Inputs")
WEGVAKKEN_PATH    = STATIC_DIR / "Wegvakken.gpkg"
HECTOPUNTEN_PATH  = STATIC_DIR / "Hectopunten.gpkg"
WERKDAG_PATH      = STATIC_DIR / "werkdag_gemiddelde_intensiteiten_in_2024_h.csv"


def load_static_gis(wegvakken_upload=None, hectopunten_upload=None):
    """Load wegvakken + hectopunten from upload or disk. 
    
    Args:
        wegvakken_upload: Uploaded file object or None (uses disk fallback)
        hectopunten_upload: Uploaded file object or None (uses disk fallback)
    
    Returns:
        (wegvakken_gdf, hectopunten_gdf, error_message)
    """
    import geopandas as gpd

    # Try to load Wegvakken
    wegvakken_gdf = None
    hectopunten_gdf = None
    
    try:
        if wegvakken_upload:
            wegvakken_source = io.BytesIO(wegvakken_upload.read())
            wegvakken_upload.seek(0)
        elif WEGVAKKEN_PATH.exists():
            wegvakken_source = str(WEGVAKKEN_PATH)
        else:
            return None, None, "Wegvakken-bestand niet gevonden"

        wegvakken_gdf = gpd.read_file(
            wegvakken_source,
            columns=['WVK_ID', 'WEGNR_HMP', 'HECTO_LTTR', 'POS_TV_WOL',
                     'BEGINKM', 'EINDKM', 'JTE_ID_BEG', 'JTE_ID_END', 'geometry'],
        )
        wegvakken_gdf = wegvakken_gdf[
            wegvakken_gdf['WEGNR_HMP'].str.match(r'^[AN]\d+$', na=False)
        ].copy()
        wegvakken_gdf.to_crs(epsg=4326, inplace=True)
    except Exception as e:
        return None, None, f"Fout bij laden Wegvakken: {str(e)}"

    # Try to load Hectopunten
    try:
        if hectopunten_upload:
            hectopunten_source = io.BytesIO(hectopunten_upload.read())
            hectopunten_upload.seek(0)
        elif HECTOPUNTEN_PATH.exists():
            hectopunten_source = str(HECTOPUNTEN_PATH)
        else:
            return None, None, "Hectopunten-bestand niet gevonden"

        hectopunten_gdf = gpd.read_file(
            hectopunten_source,
            columns=['WVK_ID', 'HECTOMTRNG', 'ZIJDE', 'HECTO_LTTR'],
        )
        hectopunten_gdf.to_crs(epsg=4326, inplace=True)
    except Exception as e:
        return None, None, f"Fout bij laden Hectopunten: {str(e)}"

    return wegvakken_gdf, hectopunten_gdf, None

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Risicoberekening | Vermeulen Groep",
    page_icon="🚧",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# CSS — Vermeulengroep style
# ---------------------------------------------------------------------------

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', 'Segoe UI', Arial, sans-serif !important;
    color: #333333;
}
.stApp { background-color: #f5f6f7; }
#MainMenu, footer { visibility: hidden; }
[data-testid="collapsedControl"] { visibility: visible !important; }

/* Ensure sidebar is visible */
[data-testid="stSidebarNav"] { visibility: visible !important; display: block !important; }

/* Nav */
.vg-nav {
    background: #ffffff;
    border-bottom: 1px solid #e2e5e9;
    padding: 13px 0 11px;
    margin-bottom: 28px;
    display: flex;
    align-items: center;
    gap: 10px;
}
.vg-nav-brand { font-size: 13px; font-weight: 700; color: #1a1a1a; letter-spacing: 0.02em; }
.vg-sep       { color: #e2e5e9; }
.vg-crumb     { font-size: 13px; color: #6b7280; }

/* Cards */
.vg-card {
    background: #ffffff;
    border: 1px solid #e2e5e9;
    border-radius: 6px;
    padding: 18px 20px;
    margin-bottom: 14px;
}
.vg-card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid #e2e5e9;
    padding-bottom: 10px;
    margin-bottom: 16px;
}
.vg-card-title { font-size: 13px; font-weight: 600; color: #1a1a1a; }

/* Typography */
.vg-label { font-size: 11px; font-weight: 600; color: #6b7280; letter-spacing: 0.06em; text-transform: uppercase; margin-bottom: 4px; }
.vg-value { font-size: 16px; font-weight: 600; color: #1a1a1a; line-height: 1.4; }
.vg-small { font-size: 12px; color: #6b7280; }

/* Risk category badges */
.badge-A { background:#fef2f2; color:#b91c1c; border-radius:4px; padding:4px 12px; font-size:14px; font-weight:700; display:inline-block; }
.badge-B { background:#fff7ed; color:#c2670e; border-radius:4px; padding:4px 12px; font-size:14px; font-weight:700; display:inline-block; }
.badge-C { background:#fefce8; color:#a16207; border-radius:4px; padding:4px 12px; font-size:14px; font-weight:700; display:inline-block; }
.badge-D { background:#eff6ff; color:#1d4ed8; border-radius:4px; padding:4px 12px; font-size:14px; font-weight:700; display:inline-block; }
.badge-E { background:#f0fdf4; color:#16803c; border-radius:4px; padding:4px 12px; font-size:14px; font-weight:700; display:inline-block; }
.badge-N { background:#f5f6f7; color:#6b7280; border-radius:4px; padding:4px 12px; font-size:14px; font-weight:700; display:inline-block; }

/* Status pills */
.pill-ok    { background:#f0fdf4; color:#16803c; border-radius:3px; padding:3px 9px; font-size:11px; font-weight:600; }
.pill-warn  { background:#fff3e0; color:#c2670e; border-radius:3px; padding:3px 9px; font-size:11px; font-weight:600; }
.pill-error { background:#fef2f2; color:#b91c1c; border-radius:3px; padding:3px 9px; font-size:11px; font-weight:600; }

/* Banners */
.vg-warn { background:#fff7ed; border:1px solid #fed7aa; border-radius:5px; padding:11px 16px; color:#c2670e; font-size:13px; margin-bottom:14px; }
.vg-ok   { background:#f0fdf4; border:1px solid #bbf7d0; border-radius:5px; padding:11px 16px; color:#16803c; font-size:13px; margin-bottom:14px; }
.vg-info { background:#eff6ff; border:1px solid #bfdbfe; border-radius:5px; padding:11px 16px; color:#1d4ed8; font-size:13px; margin-bottom:14px; }

/* Footer note */
.vg-note { background:#ffffff; border:1px solid #e2e5e9; border-radius:5px; padding:11px 14px; font-size:12px; color:#6b7280; line-height:1.65; margin-top:20px; }

/* Summary metrics */
.metric-box {
    background: #ffffff;
    border: 1px solid #e2e5e9;
    border-radius: 6px;
    padding: 16px 18px;
    text-align: center;
}
.metric-number { font-size: 28px; font-weight: 700; color: #1a1a1a; line-height: 1.1; }
.metric-label  { font-size: 11px; font-weight: 600; color: #6b7280; letter-spacing: 0.06em; text-transform: uppercase; margin-top: 4px; }

/* Progress row */
.progress-row { display:flex; align-items:center; gap:10px; margin:4px 0; font-size:13px; }

/* Streamlit overrides */
.stButton > button {
    background-color: #1d6fa4 !important;
    color: white !important;
    border: none !important;
    border-radius: 5px !important;
    font-family: 'Inter', sans-serif !important;
    font-weight: 600 !important;
    font-size: 13px !important;
    width: 100% !important;
}
.stButton > button:hover    { background-color: #155d8c !important; }
.stButton > button:disabled { background-color: #e2e5e9 !important; color: #6b7280 !important; }

[data-testid="stFileUploader"] { background:white; border:2px dashed #e2e5e9; border-radius:6px; padding:8px; }

.stTabs [data-baseweb="tab-list"] { gap:0; border-bottom:1px solid #e2e5e9; }
.stTabs [data-baseweb="tab"]      { font-size:13px !important; font-weight:500 !important; color:#6b7280 !important; border-radius:0 !important; padding:8px 16px !important; }
.stTabs [aria-selected="true"]    { color:#1d6fa4 !important; border-bottom:2px solid #1d6fa4 !important; font-weight:600 !important; }

div[data-testid="stDataFrame"] { border: 1px solid #e2e5e9; border-radius: 6px; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Nav bar
# ---------------------------------------------------------------------------

st.markdown("""
<div class="vg-nav">
  <span class="vg-nav-brand">VERMEULEN GROEP</span>
  <span class="vg-sep">|</span>
  <span class="vg-crumb">Traffic</span>
  <span class="vg-sep">›</span>
  <span class="vg-crumb">Risicocategorie Berekening</span>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Lazy imports with error messaging
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def import_heavy_deps():
    missing = []
    mods = {}
    for name, pkg in [("geopandas", "geopandas"), ("folium", "folium"),
                      ("pyproj", "pyproj"), ("shapely", "shapely"),
                      ("openrouteservice", "openrouteservice")]:
        try:
            import importlib
            mods[name] = importlib.import_module(name)
        except ImportError:
            missing.append(pkg)
    return mods, missing

deps, missing_deps = import_heavy_deps()

if missing_deps:
    st.error(
        f"**Ontbrekende packages:** `{', '.join(missing_deps)}`\n\n"
        f"Installeer via: `pip install {' '.join(missing_deps)}`"
    )

# ---------------------------------------------------------------------------
# Sidebar — configuration
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### ⚙️ Instellingen")

    ors_key = st.text_input(
        "OpenRouteService API-sleutel",
        value=os.getenv("ORS_KEY", ""),
        type="password",
        help="Verplicht. Verkrijgbaar via openrouteservice.org",
    )

    st.markdown("---")
    st.markdown("#### Statische bestanden")

    for label, path in [
        ("Wegvakken", WEGVAKKEN_PATH),
        ("Hectopunten", HECTOPUNTEN_PATH),
        ("Werkdag intensiteiten", WERKDAG_PATH),
    ]:
        exists = path.exists()
        icon   = "✅" if exists else "❌"
        color  = "#16803c" if exists else "#b91c1c"
        st.markdown(
            f"<div style='font-size:12px;color:{color};padding:2px 0'>"
            f"{icon} <strong>{label}</strong><br>"
            f"<span style='color:#6b7280;font-size:11px'>{path}</span></div>",
            unsafe_allow_html=True,
        )

    st.markdown("---")
    st.markdown("#### Upload (optioneel)")

    wegvakken_upload = st.file_uploader(
        "Wegvakken overschrijven (GPKG)",
        type=["gpkg"],
        key="wegvakken",
        help="Optioneel. Laat leeg om het bestand uit 'Static Inputs' te gebruiken.",
    )

    hectopunten_upload = st.file_uploader(
        "Hectopunten overschrijven (GPKG)",
        type=["gpkg"],
        key="hectopunten",
        help="Optioneel. Laat leeg om het bestand uit 'Static Inputs' te gebruiken.",
    )

    werkdag_file = st.file_uploader(
        "Werkdag intensiteiten overschrijven (CSV)",
        type=["csv"],
        key="werkdag",
        help="Optioneel. Laat leeg om het bestand uit 'Static Inputs' te gebruiken.",
    )

    st.markdown("---")
    st.markdown("#### Opties")

    hm_marge = st.slider("Hectometer marge (km)", 0.5, 5.0, 1.0, 0.5,
                         help="Zoekbereik rond hectometerwaarde bij het opzoeken van wegvakken.")

    show_maps = st.checkbox("Kaarten tonen per afzetting", value=True,
                            help="Interactieve Folium kaart per rij. Kan verwerking vertragen bij grote datasets.")

    st.markdown("---")
    st.markdown(
        "<small style='color:#6b7280'>"
        "Routering via OpenRouteService API.<br>"
        "Coördinaten worden omgezet naar EPSG:4326."
        "</small>",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Main header
# ---------------------------------------------------------------------------

st.markdown("## Risicocategorie Berekening")
st.markdown(
    "<p style='font-size:13px;color:#6b7280;line-height:1.65;margin-bottom:24px'>"
    "Upload een CSV met afzettingen (kolommen: <code>Afzetting locatie</code>, optioneel <code>Omleiding via</code>). "
    "Het systeem berekent per afzetting de vertraging, intensiteit en risico categorie (A–E) "
    "via de OpenRouteService API en het Nationaal Wegenbestand."
    "</p>",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Risk matrix explanation
# ---------------------------------------------------------------------------

with st.expander("ℹ️  Risicomatrix & methodiek"):
    col_l, col_r = st.columns([1, 1])
    with col_l:
        st.markdown(
            """
**Hinderklasse** (vertraging t.o.v. normale route)
| Klasse | Vertraging |
|--------|-----------|
| 1 | < 5 min |
| 2 | 5 – 10 min |
| 3 | 10 – 30 min |
| 4 | > 30 min |
            """
        )
    with col_r:
        st.markdown(
            """
**Risicomatrix** (Hinderklasse × Intensiteit)

| | < 1.000 | 1.000–10.000 | 10.000–100.000 | > 100.000 |
|---|---|---|---|---|
| **1** | E | D | C | B |
| **2** | D | C | C | B |
| **3** | C | B | A | A |
| **4** | C | B | A | A |
            """
        )
    st.markdown(
        "<p class='vg-small'>Categorie A = hoogste risico, E = laagste risico. "
        "Berekening op basis van gemiddelde dagelijkse intensiteit (werkdag) en reistijdverschil via ORS API.</p>",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# File upload — afzettingen CSV
# ---------------------------------------------------------------------------

st.markdown("### 1. Laad afzettingenbestand")
afzettingen_file = st.file_uploader(
    "Sleep het CSV-bestand hierheen of klik om te kiezen  (scheidingsteken: puntkomma)",
    type=["csv"],
    key="afzettingen",
)

# Preview CSV
if afzettingen_file:
    try:
        preview_df = pd.read_csv(afzettingen_file, sep=';', nrows=5)
        afzettingen_file.seek(0)
        st.markdown('<div class="vg-card">', unsafe_allow_html=True)
        st.markdown(
            '<div class="vg-card-header">'
            '<span class="vg-card-title">Voorbeeld — eerste 5 rijen</span>'
            f'<span class="pill-ok">{len(preview_df)} getoond</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        st.dataframe(preview_df, use_container_width=True, hide_index=True)
        st.markdown('</div>', unsafe_allow_html=True)

        # Column check
        required_cols = ["Afzetting locatie"]
        missing_cols = [c for c in required_cols if c not in preview_df.columns]
        if missing_cols:
            st.markdown(
                f'<div class="vg-warn">⚠️ Verwachte kolom(men) ontbreken: <strong>{", ".join(missing_cols)}</strong>. '
                f'Aanwezige kolommen: {", ".join(preview_df.columns.tolist())}</div>',
                unsafe_allow_html=True,
            )
    except Exception as e:
        st.error(f"Fout bij lezen CSV: {e}")

# ---------------------------------------------------------------------------
# Pre-load static GIS data
# ---------------------------------------------------------------------------

wegvakken_gdf_cached, hectopunten_gdf_cached, gis_load_error = load_static_gis(
    wegvakken_upload=wegvakken_upload,
    hectopunten_upload=hectopunten_upload,
)

if gis_load_error:
    st.markdown(
        f'<div class="vg-warn">⚠️ <strong>GIS-bestanden niet beschikbaar:</strong> {gis_load_error}<br>'
        f'Upload alternatieve bestanden via de sectie <strong>"Upload (optioneel)"</strong> in het zijpaneel.</div>',
        unsafe_allow_html=True,
    )

# Werkdag: use uploaded override, else fall back to file on disk
def get_werkdag_bytes():
    if werkdag_file:
        data = werkdag_file.read(); werkdag_file.seek(0)
        return data
    if WERKDAG_PATH.exists():
        return WERKDAG_PATH.read_bytes()
    return None

werkdag_bytes = get_werkdag_bytes()

# ---------------------------------------------------------------------------
# Readiness check
# ---------------------------------------------------------------------------

ready = all([
    afzettingen_file,
    werkdag_bytes,
    wegvakken_gdf_cached is not None,
    hectopunten_gdf_cached is not None,
    ors_key,
    not missing_deps,
])

if not ready:
    missing_items = []
    if not ors_key:                           missing_items.append("ORS API-sleutel")
    if not afzettingen_file:                  missing_items.append("Afzettingen CSV")
    if not werkdag_bytes:                     missing_items.append("Werkdag intensiteiten (niet gevonden in Static Inputs)")
    if wegvakken_gdf_cached is None:          missing_items.append("Wegvakken (niet gevonden in Static Inputs)")
    if hectopunten_gdf_cached is None:        missing_items.append("Hectopunten (niet gevonden in Static Inputs)")
    if missing_deps:                          missing_items.append(f"Packages: {', '.join(missing_deps)}")

    st.markdown(
        f'<div class="vg-info">ℹ️ Nog niet gereed. Ontbreekt: <strong>{" · ".join(missing_items)}</strong></div>',
        unsafe_allow_html=True,
    )

st.markdown("### 2. Start berekening")
run = st.button(
    "▶  Risicocategorie berekenen",
    disabled=not ready,
)

# ---------------------------------------------------------------------------
# Core processing — wraps risico_categorie_berekenen functions inline
# ---------------------------------------------------------------------------

def parse_coordinaten(x):
    if pd.isna(x) or str(x).strip() == '':
        return None
    try:
        x = str(x).strip()
        if x.startswith('[') and x.endswith(']'):
            x = x[1:-1]
            coords = [float(v.strip()) for v in x.split(',')]
            return coords
        return None
    except ValueError:
        return None


def run_berekening(afzettingen_bytes, werkdag_bytes, wegvakken_gdf_in, hectopunten_gdf_in, ors_key_val, hm_marge_val):
    """Full pipeline — returns (results_df, maps_dict, log_lines).

    wegvakken_gdf_in / hectopunten_gdf_in are pre-loaded, cached GeoDataFrames
    passed in from load_static_gis() — no file I/O happens here.
    """
    import re
    import geopandas as gpd
    import pyproj
    from shapely import geometry
    from shapely.geometry import Point
    from openrouteservice import client

    log_lines = []

    def log(msg, level="INFO"):
        log_lines.append(f"[{level}] {msg}")

    # --- ORS client ---
    ors_client = client.Client(key=ors_key_val)

    # --- Load afzettingen ---
    wegen_afzettingen = pd.read_csv(
        io.BytesIO(afzettingen_bytes), sep=';',
        converters={'Omleiding via': parse_coordinaten}
    )

    # --- Load werkdag ---
    werkdag_df = pd.read_csv(
        io.BytesIO(werkdag_bytes), sep=',',
        usecols=['vbn_oms_bp', 'wegnrhmp_b', 'bpszijde_b', 'hectoltr_b', 'hm_midden', 'al_e_wr']
    )

    # --- Use pre-loaded GIS (already cached, no disk read) ---
    wegvakken_gdf   = wegvakken_gdf_in.copy()
    hectopunten_gdf = hectopunten_gdf_in.copy()

    nwb_gdf = wegvakken_gdf[['WVK_ID', 'WEGNR_HMP', 'HECTO_LTTR', 'POS_TV_WOL', 'BEGINKM', 'EINDKM']].merge(
        hectopunten_gdf[['WVK_ID', 'HECTOMTRNG', 'ZIJDE', 'geometry']],
        on='WVK_ID', how='inner')
    nwb_gdf = gpd.GeoDataFrame(nwb_gdf, geometry='geometry', crs='EPSG:4326')
    log(f"Data geladen: {len(werkdag_df)} intensiteitsrecords, {len(nwb_gdf)} geografische features")

    # ---- helpers ----

    def parse_weg_data(input_weg):
        try:
            pattern = r'^([AN]\d{1,3})\s+(?:HMP|KM)\s+([\d.]+)(?:\s+(Re|Li))?(?:\s+(.+))?$'
            match = re.match(pattern, input_weg.strip())
            if not match:
                log(f"Kan niet parsen: {input_weg}", "ERROR")
                return None
            wegnummer  = match.group(1)
            hectometer = float(match.group(2))
            zijde      = match.group(3) if match.group(3) else ''
            afrit      = match.group(4) if match.group(4) else ''
            if zijde and len(zijde) == 1 and zijde not in ['Re', 'Li']:
                afrit, zijde = zijde, ''
            return {"wegnummer": wegnummer, "hectometer": hectometer, "zijde": zijde, "afrit": afrit}
        except Exception as e:
            log(f"Fout bij parsen weg data: {e}", "ERROR")
            return None

    def weg_data_naar_coordinaten(weg_data, hmp):
        try:
            mask = (
                (nwb_gdf['WEGNR_HMP'] == weg_data['wegnummer']) &
                ((nwb_gdf['POS_TV_WOL'].eq(weg_data['zijde'][0]) | nwb_gdf['POS_TV_WOL'].isna())
                    if weg_data['zijde'] != '' else pd.Series(True, index=nwb_gdf.index)) &
                ((nwb_gdf['HECTO_LTTR'] == weg_data['afrit']) if weg_data['afrit']
                    else (nwb_gdf['HECTO_LTTR'] == '#')) &
                (nwb_gdf[['BEGINKM', 'EINDKM']].min(axis=1) - hm_marge_val <= hmp) &
                (hmp <= nwb_gdf[['BEGINKM', 'EINDKM']].max(axis=1) + hm_marge_val) &
                (abs((nwb_gdf['HECTOMTRNG'] / 10) - hmp) <= hm_marge_val) &
                ((nwb_gdf['ZIJDE'].eq(weg_data['zijde']) | nwb_gdf['ZIJDE'].isna())
                    if weg_data['zijde'] != '' else pd.Series(True, index=nwb_gdf.index))
            )
            matching = nwb_gdf[mask]
            if len(matching) == 0:
                log(f"Geen match voor {weg_data['wegnummer']} HMP {hmp}", "WARN")
                return None
            if len(matching) > 1:
                matching = matching.copy()
                matching['dist'] = matching.apply(
                    lambda r: min(
                        abs(r['BEGINKM'] - hmp) if pd.notna(r['BEGINKM']) else float('inf'),
                        abs(r['EINDKM']  - hmp) if pd.notna(r['EINDKM'])  else float('inf')
                    ), axis=1)
                matching = matching.sort_values('dist')
            best = matching.iloc[0]
            weg_data['wegvak_id'] = best['WVK_ID']
            if weg_data['zijde'] == '' and pd.notna(best['POS_TV_WOL']):
                weg_data['zijde'] = 'Re' if best['POS_TV_WOL'] == 'R' else 'Li' if best['POS_TV_WOL'] == 'L' else ''
            return [best.geometry.y, best.geometry.x]
        except Exception as e:
            log(f"Fout bij coördinaten ophalen: {e}", "ERROR")
            return None

    def calculate_intensiteit(afzetting_data):
        try:
            mask = (
                (werkdag_df['wegnrhmp_b'] == afzetting_data['wegnummer']) &
                (abs(werkdag_df['hm_midden'] - afzetting_data['hectometer']) <= hm_marge_val) &
                ((werkdag_df['bpszijde_b'].eq(afzetting_data['zijde']) | werkdag_df['bpszijde_b'].isna())
                    if afzetting_data['zijde'] != '' else pd.Series(True, index=werkdag_df.index)) &
                (werkdag_df['hectoltr_b'].isna() |
                    (werkdag_df['hectoltr_b'].eq(afzetting_data['afrit'])
                        if afzetting_data['afrit'] else pd.Series(False, index=werkdag_df.index)))
            )
            rows = werkdag_df[mask]
            if len(rows) == 0:
                log(f"Geen intensiteit voor {afzetting_data['wegnummer']} HMP {afzetting_data['hectometer']}", "WARN")
                return None
            if len(rows) > 1:
                rows = rows.copy()
                rows['hm_diff'] = abs(rows['hm_midden'] - afzetting_data['hectometer'])
                rows = rows.sort_values('hm_diff')
            return rows.iloc[0]['al_e_wr']
        except Exception as e:
            log(f"Fout bij intensiteit berekenen: {e}", "ERROR")
            return None

    def vind_coordinaat_via_junctie(wegvak_id, richting, stappen=5):
        huidig = wegvakken_gdf[wegvakken_gdf['WVK_ID'] == wegvak_id]
        if huidig.empty:
            return None
        for _ in range(stappen):
            if richting == 'voor':
                junctie   = huidig.iloc[0]['JTE_ID_BEG']
                kandidaten = wegvakken_gdf[wegvakken_gdf['JTE_ID_END'] == junctie]
            else:
                junctie   = huidig.iloc[0]['JTE_ID_END']
                kandidaten = wegvakken_gdf[wegvakken_gdf['JTE_ID_BEG'] == junctie]
            kandidaten = kandidaten[kandidaten['WVK_ID'] != huidig.iloc[0]['WVK_ID']]
            if len(kandidaten) == 0:
                break
            zelfde = kandidaten[kandidaten['WEGNR_HMP'] == huidig.iloc[0]['WEGNR_HMP']]
            huidig = zelfde.iloc[[0]] if not zelfde.empty else kandidaten.iloc[[0]]
        geom = huidig.iloc[0].geometry.interpolate(0.5, normalized=True)
        return [geom.y, geom.x]

    def calculate_normale_rit_data(afzetting_data):
        data = afzetting_data.copy()
        wegvak_id = afzetting_data.get('wegvak_id')
        if not wegvak_id:
            return None
        if data['zijde'] == 'Li':
            data['begin'] = vind_coordinaat_via_junctie(wegvak_id, 'na')
            data['eind']  = vind_coordinaat_via_junctie(wegvak_id, 'voor')
        elif data['zijde'] == 'Re':
            data['begin'] = vind_coordinaat_via_junctie(wegvak_id, 'voor')
            data['eind']  = vind_coordinaat_via_junctie(wegvak_id, 'na')
        else:
            return None
        if data['begin'] is None or data['eind'] is None:
            return None
        return data

    def ors_route(coords_list):
        try:
            return ors_client.directions(
                coordinates=coords_list,
                format_out='geojson',
                profile='driving-car',
                preference='fastest',
                instructions='false',
            )
        except Exception as e:
            log(f"ORS fout: {e}", "ERROR")
            return None

    def maak_buffer_polygon(coordinaten, resolution=10, radius=10, for_api=False):
        convert      = pyproj.Transformer.from_crs("epsg:4326", "epsg:32632")
        convert_back = pyproj.Transformer.from_crs("epsg:32632", "epsg:4326")
        proj = convert.transform(*coordinaten)
        buf  = Point(proj).buffer(radius, resolution=resolution)
        poly = []
        for pt in buf.exterior.coords:
            back = convert_back.transform(*pt)
            poly.append([back[1], back[0]] if for_api else [back[0], back[1]])
        return poly

    def calculate_omleiding_route(rit_data, afzetting_data, omleiding_via=None):
        if omleiding_via:
            coords = [
                list(reversed(rit_data['begin'])),
                list(reversed(omleiding_via)),
                list(reversed(rit_data['eind'])),
            ]
            return ors_route(coords)
        else:
            buf_coords = maak_buffer_polygon(afzetting_data['coordinaten'], for_api=True)
            buf_poly   = geometry.Polygon(buf_coords)
            try:
                return ors_client.directions(
                    coordinates=[list(reversed(rit_data['begin'])), list(reversed(rit_data['eind']))],
                    format_out='geojson',
                    profile='driving-car',
                    preference='fastest',
                    instructions='false',
                    options={'avoid_polygons': geometry.mapping(buf_poly)},
                )
            except Exception as e:
                log(f"ORS omleiding fout: {e}", "ERROR")
                return None

    def calculate_risico_categorie(afzetting_data, intensiteit, route_normaal, route_omleiding):
        if not all([intensiteit, route_normaal, route_omleiding]):
            return None
        try:
            delay_min     = (route_omleiding['features'][0]['properties']['summary']['duration'] -
                             route_normaal['features'][0]['properties']['summary']['duration']) / 60
            hinderklasse  = int(np.searchsorted([5, 10, 30], delay_min) + 1)
            int_index     = int(np.searchsorted([1000, 10000, 100000], intensiteit))
            matrix = {1: ['E','D','C','B'], 2: ['D','C','C','B'], 3: ['C','B','A','A'], 4: ['C','B','A','A']}
            return matrix[hinderklasse][int_index]
        except Exception as e:
            log(f"Fout risico categorie: {e}", "ERROR")
            return None

    def maak_folium_kaart(afzetting_data, route_normaal, route_omleiding):
        import folium
        m = folium.Map(location=afzetting_data['coordinaten'], zoom_start=12)
        folium.GeoJson(
            route_normaal,
            name='Normale route',
            style_function=lambda x: {'color': '#15FF00', 'weight': 5, 'opacity': 0.9},
        ).add_to(m)
        folium.GeoJson(
            route_omleiding,
            name='Omleidingsroute',
            style_function=lambda x: {'color': '#FF9900', 'weight': 5, 'opacity': 0.9},
        ).add_to(m)
        folium.Marker(
            location=afzetting_data['coordinaten'],
            popup=f"{afzetting_data['wegnummer']} HMP {afzetting_data['hectometer']} "
                  f"{afzetting_data['zijde']} {afzetting_data['afrit']}",
            icon=folium.Icon(color='red', icon='info-sign'),
        ).add_to(m)
        if not afzetting_data.get('Omleiding via'):
            folium.Polygon(
                locations=maak_buffer_polygon(afzetting_data['coordinaten'], resolution=10, radius=10),
                color='#FF6767', fill=True, fill_opacity=0.2,
                popup='Bufferzone afzetting',
            ).add_to(m)
        folium.LayerControl().add_to(m)
        return m._repr_html_()

    # ---- main loop ----
    results  = []
    maps_html = {}

    total = len(wegen_afzettingen)
    for idx, weg_row in wegen_afzettingen.iterrows():
        row_result = {
            'Afzetting locatie':  weg_row.get('Afzetting locatie', ''),
            'Omleiding via':      str(weg_row.get('Omleiding via', '')),
            'wegnummer': None, 'hectometer': None, 'zijde': None, 'afrit': None,
            'coordinaten': None,
            'intensiteit': None,
            'normale_reistijd_min': None,
            'omleiding_reistijd_min': None,
            'vertraging_min': None,
            'risico_categorie': None,
            'status': 'OK',
            'fout': '',
        }
        try:
            afzetting_data = weg_row.to_dict()
            parsed = parse_weg_data(str(weg_row['Afzetting locatie']))
            if not parsed:
                row_result['status'] = 'FOUT'
                row_result['fout']   = 'Kan locatiestring niet parsen'
                results.append(row_result)
                continue

            afzetting_data.update(parsed)
            row_result.update({k: parsed[k] for k in ['wegnummer', 'hectometer', 'zijde', 'afrit']})

            coords = weg_data_naar_coordinaten(afzetting_data, afzetting_data['hectometer'])
            if not coords:
                row_result['status'] = 'FOUT'
                row_result['fout']   = 'Geen coördinaten gevonden in NWB'
                results.append(row_result)
                continue

            afzetting_data['coordinaten'] = coords
            row_result['coordinaten'] = f"{coords[0]:.5f}, {coords[1]:.5f}"

            intensiteit = calculate_intensiteit(afzetting_data)
            row_result['intensiteit'] = intensiteit

            rit_data = calculate_normale_rit_data(afzetting_data)
            if not rit_data:
                row_result['status'] = 'FOUT'
                row_result['fout']   = 'Normale rit data kon niet bepaald worden'
                results.append(row_result)
                continue

            route_normaal = ors_route([
                list(reversed(rit_data['begin'])),
                list(reversed(rit_data['eind'])),
            ])
            if not route_normaal:
                row_result['status'] = 'FOUT'
                row_result['fout']   = 'ORS: normale route niet beschikbaar'
                results.append(row_result)
                continue

            omleiding_via = afzetting_data.get('Omleiding via')
            route_omleiding = calculate_omleiding_route(rit_data, afzetting_data, omleiding_via=omleiding_via)
            if not route_omleiding:
                row_result['status'] = 'FOUT'
                row_result['fout']   = 'ORS: omleidingsroute niet beschikbaar'
                results.append(row_result)
                continue

            dur_n = route_normaal['features'][0]['properties']['summary']['duration'] / 60
            dur_o = route_omleiding['features'][0]['properties']['summary']['duration'] / 60
            row_result['normale_reistijd_min']    = round(dur_n, 1)
            row_result['omleiding_reistijd_min']  = round(dur_o, 1)
            row_result['vertraging_min']           = round(dur_o - dur_n, 1)

            cat = calculate_risico_categorie(afzetting_data, intensiteit, route_normaal, route_omleiding)
            row_result['risico_categorie'] = cat

            if show_maps:
                maps_html[idx] = maak_folium_kaart(afzetting_data, route_normaal, route_omleiding)

            log(f"[{idx+1}/{total}] {afzetting_data['wegnummer']} HMP {afzetting_data['hectometer']} → categorie {cat}")

        except Exception as e:
            row_result['status'] = 'FOUT'
            row_result['fout']   = str(e)
            log(f"[{idx+1}/{total}] onverwachte fout: {e}", "ERROR")

        results.append(row_result)

    return pd.DataFrame(results), maps_html, log_lines


# ---------------------------------------------------------------------------
# Run processing
# ---------------------------------------------------------------------------

if run and ready:
    afzettingen_bytes = afzettingen_file.read(); afzettingen_file.seek(0)

    with st.spinner("Routes berekenen via ORS API…"):
        try:
            results_df, maps_html, log_lines = run_berekening(
                afzettingen_bytes, werkdag_bytes,
                wegvakken_gdf_cached, hectopunten_gdf_cached,
                ors_key, hm_marge,
            )
            st.session_state["results_df"] = results_df
            st.session_state["maps_html"]  = maps_html
            st.session_state["log_lines"]  = log_lines
        except Exception as e:
            st.error(f"**Fout bij verwerking:** {e}")
            st.stop()

# ---------------------------------------------------------------------------
# Render results
# ---------------------------------------------------------------------------

if "results_df" in st.session_state:
    results_df = st.session_state["results_df"]
    maps_html  = st.session_state["maps_html"]
    log_lines  = st.session_state["log_lines"]

    st.markdown("---")
    st.markdown("### 3. Resultaten")

    # ---- Summary metrics ----
    total_rows = len(results_df)
    ok_rows    = len(results_df[results_df['status'] == 'OK'])
    err_rows   = total_rows - ok_rows

    cat_counts = results_df['risico_categorie'].value_counts().to_dict()

    col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
    for col, (label, val, color) in zip(
        [col1, col2, col3, col4, col5, col6, col7],
        [
            ("Totaal", total_rows, "#1a1a1a"),
            ("Geslaagd", ok_rows, "#16803c"),
            ("Fouten", err_rows, "#b91c1c"),
            ("Cat A", cat_counts.get('A', 0), "#b91c1c"),
            ("Cat B", cat_counts.get('B', 0), "#c2670e"),
            ("Cat C", cat_counts.get('C', 0), "#a16207"),
            ("Cat D/E", (cat_counts.get('D', 0) + cat_counts.get('E', 0)), "#1d4ed8"),
        ]
    ):
        with col:
            st.markdown(
                f'<div class="metric-box">'
                f'<div class="metric-number" style="color:{color}">{val}</div>'
                f'<div class="metric-label">{label}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)

    # ---- Results table ----
    tab_tabel, tab_kaarten, tab_log = st.tabs(["📋  Resultatenlijst", "🗺️  Kaarten", "📄  Log"])

    with tab_tabel:
        def style_categorie(val):
            colors = {'A': '#fef2f2', 'B': '#fff7ed', 'C': '#fefce8', 'D': '#eff6ff', 'E': '#f0fdf4'}
            return f"background-color: {colors.get(str(val), 'white')}; font-weight: bold;"

        display_cols = [
            'Afzetting locatie', 'wegnummer', 'hectometer', 'zijde',
            'coordinaten', 'intensiteit',
            'normale_reistijd_min', 'omleiding_reistijd_min', 'vertraging_min',
            'risico_categorie', 'status', 'fout',
        ]
        display_cols = [c for c in display_cols if c in results_df.columns]
        styled = results_df[display_cols].style.applymap(style_categorie, subset=['risico_categorie'])
        st.dataframe(styled, use_container_width=True, hide_index=True)

        # Download button
        csv_buf = io.StringIO()
        results_df.to_csv(csv_buf, index=False, sep=';')
        st.download_button(
            label="⬇  Download resultaten (CSV)",
            data=csv_buf.getvalue(),
            file_name="risicoberekening_output.csv",
            mime="text/csv",
        )

    with tab_kaarten:
        if not maps_html:
            st.markdown(
                '<div class="vg-info">ℹ️ Kaarten zijn uitgeschakeld. Activeer "Kaarten tonen" in de zijbalk.</div>',
                unsafe_allow_html=True,
            )
        else:
            for idx, html in maps_html.items():
                row = results_df.iloc[idx]
                cat  = row.get('risico_categorie') or 'N'
                badge_cls = f"badge-{cat}" if cat in 'ABCDE' else "badge-N"
                st.markdown(
                    f'<div class="vg-card-header" style="margin-top:16px">'
                    f'<span class="vg-card-title">📍 {row["Afzetting locatie"]}</span>'
                    f'<span class="{badge_cls}">Categorie {cat}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    st.markdown(f'<div class="vg-label">Vertraging</div><div class="vg-value">{row.get("vertraging_min", "—")} min</div>', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'<div class="vg-label">Intensiteit</div><div class="vg-value">{int(row["intensiteit"]) if pd.notna(row.get("intensiteit")) else "—"} vrt/dag</div>', unsafe_allow_html=True)
                with col_c:
                    st.markdown(f'<div class="vg-label">Coördinaten</div><div class="vg-value">{row.get("coordinaten", "—")}</div>', unsafe_allow_html=True)
                components.html(html, height=400, scrolling=False)
                st.markdown("<br>", unsafe_allow_html=True)

    with tab_log:
        st.markdown(
            '<div class="vg-card"><div class="vg-card-header">'
            '<span class="vg-card-title">Verwerkingslog</span>'
            f'<span class="pill-ok">{len(log_lines)} regels</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        log_text = "\n".join(log_lines)
        st.text_area("", value=log_text, height=300, label_visibility="collapsed")
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown(
        '<div class="vg-note"><strong style="color:#333">Werkwijze:</strong> '
        "Afzettinglocaties worden geparsed uit de kolom 'Afzetting locatie' en opgezocht in het NWB (wegvakken + hectopunten). "
        "Via junctie-traversal worden begin- en eindpunten bepaald. "
        "OpenRouteService berekent de normale route en omleidingsroute. "
        "Het reistijdverschil en de intensiteit (werkdag gemiddelde 2024) bepalen de risico categorie A–E. "
        "Resultaten zijn indicatief — valideer met uw GIS-systeem.</div>",
        unsafe_allow_html=True,
    )