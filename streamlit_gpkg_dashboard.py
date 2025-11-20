"""
Streamlit interactive dashboard for a GeoPackage (.gpkg)
Updated to use HuggingFace-hosted GPKG as default source.

Features:
- Load GeoPackage from remote HuggingFace URL or manual URL
- List available layers and let user pick one
- Quick attribute table preview and column selection
- Numeric / categorical filtering
- Choropleth map with classification options
- Popups and centroid overlays
- Download filtered data as GeoJSON

Run:
    streamlit run streamlit_gpkg_dashboard.py

Dependencies in requirements.txt:
    streamlit
    geopandas
    fiona
    folium
    streamlit-folium
    pandas
    matplotlib
    mapclassify
    shapely
    pyproj
    rtree
"""

import streamlit as st
import geopandas as gpd
import pandas as pd
import fiona
import io
import os
from streamlit_folium import st_folium
import folium
import matplotlib.pyplot as plt

# -----------------------------------------------------------
# CONFIG
# -----------------------------------------------------------
st.set_page_config(layout="wide", page_title="GPKG Explorer")

DEFAULT_REMOTE_URL = (
    "https://huggingface.co/datasets/trategos/flood-gpkg-datasets/resolve/main/"
    "Impacts_aggregated_Current_2029_8percent_no_measures_DESA.gpkg"
)

# -----------------------------------------------------------
# FUNCTIONS
# -----------------------------------------------------------
@st.cache_data(show_spinner=False)
def list_layers(path_or_url: str):
    try:
        return fiona.listlayers(path_or_url)
    except Exception as e:
        st.warning(f"Could not list layers: {e}")
        return []

@st.cache_data(show_spinner=True)
def load_layer(path_or_url: str, layer_name: str = None):
    try:
        if layer_name:
            gdf = gpd.read_file(path_or_url, layer=layer_name)
        else:
            gdf = gpd.read_file(path_or_url)
        return gdf
    except Exception as e:
        st.error(f"Failed to read file or layer: {e}")
        return None

def safe_to_crs(gdf, crs="EPSG:4326"):
    try:
        return gdf.to_crs(crs)
    except Exception:
        return gdf

# -----------------------------------------------------------
# SIDEBAR – DATA SOURCE
# -----------------------------------------------------------
st.sidebar.title("Data Source")
load_mode = st.sidebar.radio("Load GPKG from", ["HuggingFace (default)", "Custom URL"])

if load_mode == "HuggingFace (default)":
    gpkg_path = st.sidebar.text_input("Remote GPKG URL", DEFAULT_REMOTE_URL)
else:
    gpkg_path = st.sidebar.text_input(
        "Enter any raw/remote GPKG URL", "https://.../file.gpkg"
    )

if not gpkg_path:
    st.stop()

# -----------------------------------------------------------
# LOAD LAYERS
# -----------------------------------------------------------
st.sidebar.markdown("---")
st.sidebar.write("### Layer selection")

with st.spinner("Listing layers..."):
    layers = list_layers(gpkg_path)

if not layers:
    st.sidebar.warning("No layers found or could not read layer list.")
    chosen_layer = None
else:
    chosen_layer = st.sidebar.selectbox("Choose layer", layers)

# -----------------------------------------------------------
# LOAD SELECTED LAYER
# -----------------------------------------------------------
st.title("GeoPackage (GPKG) Explorer — Interactive Dashboard")

with st.spinner("Loading selected layer…"):
    gdf = load_layer(gpkg_path, chosen_layer)

if gdf is None:
    st.stop()

# Ensure geometries exist
gdf = safe_to_crs(gdf)

# -----------------------------------------------------------
# TOP INFO
# -----------------------------------------------------------
col1, col2, col3 = st.columns([3, 1.5, 1.5])
with col1:
    st.subheader(f"Layer: {chosen_layer}")
    st.write(f"Features: {len(gdf):,}")
    st.write(f"CRS: {gdf.crs}")

with col2:
    st.metric("Columns", len(gdf.columns))
    geom_types = gdf.geometry.geom_type.value_counts().to_dict()
    st.write("Geometry types:")
    for gt, ct in geom_types.items():
        st.write(f"- {gt}: {ct}")

with col3:
    if st.button("Show attribute table (first 200 rows)"):
        st.dataframe(gdf.head(200))

st.markdown("---")

# -----------------------------------------------------------
# SIDEBAR – ATTRIBUTES & FILTERS
# -----------------------------------------------------------
st.sidebar.write("### Attribute Visualization")

columns = list(gdf.columns)
columns_no_geom = [c for c in columns if c != gdf.geometry.name]

chosen_x = st.sidebar.selectbox("Column for choropleth & analysis", columns_no_geom)

is_numeric = pd.api.types.is_numeric_dtype(gdf[chosen_x])

filtered = gdf.copy()
st.sidebar.write("### Filters")

if is_numeric:
    minv = float(gdf[chosen_x].min())
    maxv = float(gdf[chosen_x].max())
    rmin, rmax = st.sidebar.slider(
        f"Filter {chosen_x}", minv, maxv, (minv, maxv)
    )
    filtered = filtered[(filtered[chosen_x] >= rmin) & (filtered[chosen_x] <= rmax)]
else:
    unique_vals = sorted(filtered[chosen_x].dropna().unique().tolist())
    sel = st.sidebar.multiselect(f"Select values in {chosen_x}", unique_vals)
    if sel:
        filtered = filtered[filtered[chosen_x].isin(sel)]

# Optional text search
text_col = st.sidebar.selectbox("Optional text search column", [None] + columns_no_geom)
if text_col:
    q = st.sidebar.text_input("Search text")
    if q:
        filtered = filtered[filtered[text_col].astype(str).str.contains(q, case=False)]

# -----------------------------------------------------------
# MAP
# -----------------------------------------------------------
st.subheader("Interactive Map")

# Center map
try:
    c = filtered.geometry.unary_union.centroid
    center = [c.y, c.x]
except Exception:
    center = [0, 0]

map_tiles = st.sidebar.selectbox(
    "Base tiles", ["OpenStreetMap", "Stamen Terrain", "Stamen Toner", "CartoDB positron"]
)

m = folium.Map(location=center, zoom_start=8, tiles=map_tiles)

# Choropleth (numeric only)
if is_numeric and len(filtered) > 0:
    method = st.sidebar.selectbox("Classification method", ["quantiles", "equal_interval"])
    bins = st.sidebar.slider("Classes", 3, 9, 5)

    try:
        if method == "quantiles":
            filtered["_class"] = pd.qcut(filtered[chosen_x], bins, duplicates="drop").astype(str)
        else:
            filtered["_class"] = pd.cut(filtered[chosen_x], bins).astype(str)
    except Exception:
        filtered["_class"] = "NA"

# Add GeoJSON with tooltip
popup_fields = st.multiselect(
    "Popup fields", columns_no_geom, default=columns_no_geom[:5]
)

folium.GeoJson(
    filtered.to_json(),
    tooltip=folium.GeoJsonTooltip(fields=popup_fields),
    popup=folium.GeoJsonPopup(fields=popup_fields, labels=True),
).add_to(m)

st_folium(m, width=1000, height=600)

# -----------------------------------------------------------
# STATS & CHARTS
# -----------------------------------------------------------
st.subheader("Statistics & Charts")
colA, colB = st.columns(2)

with colA:
    st.write("Preview (top 10)")
    st.dataframe(filtered.head(10))

with colB:
    st.write("Describe")
    st.write(filtered.describe(include="all"))

if is_numeric:
    fig, ax = plt.subplots()
    filtered[chosen_x].plot.hist(ax=ax, bins=30)
    ax.set_title(f"Histogram of {chosen_x}")
    st.pyplot(fig)

# -----------------------------------------------------------
# DOWNLOAD
# -----------------------------------------------------------
st.subheader("Download filtered data")
buffer = io.BytesIO()
filtered.to_file(buffer, driver="GeoJSON")
buffer.seek(0)

st.download_button(
    "Download filtered.geojson",
    data=buffer,
    file_name="filtered.geojson",
    mime="application/geo+json",
)

st.success("Dashboard ready. Adjust filters in the sidebar to explore the data.")
