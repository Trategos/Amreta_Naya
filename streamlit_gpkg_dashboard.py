"""
Streamlit interactive dashboard for a GeoPackage (.gpkg)

Features:
- Load GeoPackage from local path (default) or GitHub raw URL
- List available layers and let user pick one
- Quick attribute table preview and column selection
- Numeric / categorical filtering
- Choropleth map with selectable attribute, classification (quantiles/equal interval), bins
- Popups on click and summary charts
- Download filtered GeoJSON

Usage:
1. Install dependencies:
   pip install streamlit geopandas fiona folium streamlit-folium pandas matplotlib
   (optional: pip install mapclassify for extra classification methods)
2. Run:
   streamlit run streamlit_gpkg_dashboard.py

Notes about GitHub:
- If you want Streamlit to load the .gpkg from a GitHub repository, put the file in the repo and use the *raw* URL, e.g.
  https://raw.githubusercontent.com/<username>/<repo>/<branch>/path/to/file.gpkg
- For large .gpkg files GitHub raw URLs may not work well — it's best to host the file in a release or external storage.

Defaults in this script try to use the uploaded file path: 
/mnt/data/Impacts_aggregated_Current_2029_8percent_no_measures_DESA.gpkg

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

st.set_page_config(layout="wide", page_title="GPKG Explorer")

# --- Constants / defaults ---
DEFAULT_LOCAL_PATH = "https://huggingface.co/datasets/trategos/flood-gpkg-datasets/resolve/main/Impacts_aggregated_Current_2029_8percent_no_measures_DESA.gpkg"

# --- Utilities ---
@st.cache_data(show_spinner=False)
def list_layers(path_or_url: str):
    """Return list of layers contained in gpkg. Handles local path or raw URL (if fiona supports)."""
    try:
        return fiona.listlayers(path_or_url)
    except Exception as e:
        # fiona may not handle certain HTTP servers; return empty and let caller handle errors
        st.warning(f"Could not list layers: {e}")
        return []

@st.cache_data(show_spinner=True)
def load_layer(path_or_url: str, layer_name: str = None):
    """Read a layer from gpkg and return GeoDataFrame. Caches result."""
    try:
        # geopandas will forward to fiona
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

# --- Sidebar controls ---
st.sidebar.title("Data source & options")
source_mode = st.sidebar.radio("Load GPKG from:", ("Local path (default)", "GitHub raw URL"))

if source_mode == "Local path (default)":
    gpkg_path = st.sidebar.text_input("Local file path", DEFAULT_LOCAL_PATH)
else:
    gpkg_path = st.sidebar.text_input("GitHub raw URL (raw.githubusercontent.com)", "")

if gpkg_path == "":
    st.sidebar.info("Provide a path or raw URL to a .gpkg file.")

# show available layers
layers = []
if gpkg_path:
    with st.spinner("Listing layers..."):
        layers = list_layers(gpkg_path)

if not layers:
    st.sidebar.warning("No layers found (or listing failed). You can still try to load the default layer by name.")

chosen_layer = st.sidebar.selectbox("Choose layer", options=(layers if layers else [None]))

# map options
st.sidebar.markdown("---")
map_tiles = st.sidebar.selectbox("Base tiles", ["OpenStreetMap", "Stamen Terrain", "Stamen Toner", "CartoDB positron"])
show_centroids = st.sidebar.checkbox("Show centroids (points)", value=False)

# --- Main ---
st.title("GeoPackage (GPKG) Explorer — Streamlit")

if not gpkg_path:
    st.info("Start by selecting a data source in the left sidebar.")
    st.stop()

with st.spinner("Loading layer..."):
    gdf = load_layer(gpkg_path, chosen_layer)

if gdf is None:
    st.stop()

# ensure geometry
if gdf.geometry.is_empty.all():
    st.error("Layer contains no geometry.")
    st.stop()

# Convert to WGS84 for mapping if necessary
gdf = safe_to_crs(gdf, "EPSG:4326")

# show top-level info
col1, col2, col3 = st.columns([3, 1, 1])
with col1:
    st.subheader(f"Layer: {chosen_layer if chosen_layer else '(default)'}")
    st.write(f"Features: {len(gdf):,}")
    st.write(f"CRS: {gdf.crs}")

with col2:
    st.metric("Columns", len(gdf.columns))
    # geometry type summary
    geom_types = gdf.geometry.geom_type.value_counts().to_dict()
    st.write("Geometry types:")
    for gt, ct in geom_types.items():
        st.write(f"- {gt}: {ct}")

with col3:
    if st.button("Show full attribute table (top 200 rows)"):
        st.dataframe(gdf.head(200))

st.markdown("---")

# --- Attribute controls ---
st.sidebar.subheader("Attribute & filter")
columns = list(gdf.columns)
# exclude geometry
columns_no_geom = [c for c in columns if c != gdf.geometry.name]

if not columns_no_geom:
    st.error("No attribute columns found in this layer.")
    st.stop()

chosen_x = st.sidebar.selectbox("Column for choropleth / analysis", options=columns_no_geom, index=0)

# numeric or categorical behaviour
is_numeric = pd.api.types.is_numeric_dtype(gdf[chosen_x])

st.sidebar.markdown("Filters")
filtered = gdf.copy()

# numeric filter
if is_numeric:
    minv = float(gdf[chosen_x].min(skipna=True))
    maxv = float(gdf[chosen_x].max(skipna=True))
    if pd.isnull(minv) or pd.isnull(maxv):
        st.sidebar.write("Selected column has only missing values.")
    else:
        rmin, rmax = st.sidebar.slider(f"Filter {chosen_x}", min_value=minv, max_value=maxv, value=(minv, maxv))
        filtered = filtered[(filtered[chosen_x] >= rmin) & (filtered[chosen_x] <= rmax)]
else:
    unique_vals = sorted(filtered[chosen_x].dropna().unique().tolist())
    sel = st.sidebar.multiselect(f"Select {chosen_x} values", options=unique_vals, default=unique_vals[:10])
    if sel:
        filtered = filtered[filtered[chosen_x].isin(sel)]

# Additional quick filter: text search
text_search_col = st.sidebar.selectbox("Text search column (optional)", options=[None] + columns_no_geom)
if text_search_col:
    q = st.sidebar.text_input(f"Search text in {text_search_col}")
    if q:
        filtered = filtered[filtered[text_search_col].astype(str).str.contains(q, case=False, na=False)]

st.sidebar.markdown("---")

# --- Map building ---
st.subheader("Map")

# center map
try:
    centroid = filtered.geometry.unary_union.centroid
    center = [centroid.y, centroid.x]
except Exception:
    # fallback to first geometry
    first = filtered.geometry.iloc[0]
    center = [first.centroid.y, first.centroid.x]

m = folium.Map(location=center, zoom_start=8, tiles=None)
# tiles
if map_tiles == "OpenStreetMap":
    folium.TileLayer("OpenStreetMap").add_to(m)
elif map_tiles == "Stamen Terrain":
    folium.TileLayer("Stamen Terrain").add_to(m)
elif map_tiles == "Stamen Toner":
    folium.TileLayer("Stamen Toner").add_to(m)
else:
    folium.TileLayer("CartoDB positron").add_to(m)

# Prepare for choropleth if numeric
if is_numeric:
    choropleth_col = chosen_x
    method = st.sidebar.selectbox("Classification method", ["quantiles", "equal_interval"], index=0)
    bins = st.sidebar.slider("Number of classes", min_value=3, max_value=9, value=5)

    # compute classification
    try:
        if method == "quantiles":
            filtered = filtered.dropna(subset=[choropleth_col])
            filtered["__class"] = pd.qcut(filtered[choropleth_col], q=bins, duplicates="drop").astype(str)
            # prepare mapping value per feature id
            data_for_choro = filtered[[choropleth_col]]
            folium.Choropleth(
                geo_data=filtered.__geo_interface__,
                data=filtered,
                columns=[filtered.index.name or 'index', choropleth_col],
                key_on=None,
                fill_opacity=0.7,
                line_opacity=0.2,
            ).add_to(m)
        else:
            # equal interval: create bins with pandas.cut
            filtered = filtered.dropna(subset=[choropleth_col])
            filtered["__class"] = pd.cut(filtered[choropleth_col], bins=bins).astype(str)
            folium.Choropleth(
                geo_data=filtered.__geo_interface__,
                data=filtered,
                columns=[filtered.index.name or 'index', choropleth_col],
                key_on=None,
                fill_opacity=0.7,
                line_opacity=0.2,
            ).add_to(m)
    except Exception as e:
        st.warning(f"Choropleth creation failed: {e}")

# Add GeoJson with popups
popup_fields = st.multiselect("Popup fields (show when click)", options=columns_no_geom, default=columns_no_geom[:4])

def make_popup_html(row):
    parts = []
    for f in popup_fields:
        parts.append(f"<b>{f}</b>: {row.get(f, '')}")
    return "<br/>".join(parts)

folium.GeoJson(
    filtered.to_json(),
    name="data",
    tooltip=folium.GeoJsonTooltip(fields=popup_fields if popup_fields else None),
    popup=folium.GeoJsonPopup(fields=popup_fields if popup_fields else None, labels=True)
).add_to(m)

# optionally show centroids
if show_centroids:
    for idx, row in filtered.iterrows():
        if row.geometry is not None:
            c = row.geometry.centroid
            folium.CircleMarker(location=[c.y, c.x], radius=3, fill=True, opacity=0.8).add_to(m)

folium.LayerControl().add_to(m)

# display map
st_data = st_folium(m, width=1000, height=600)

# --- Summary charts and stats ---
st.subheader("Summary & charts")
colA, colB = st.columns([1, 1])
with colA:
    st.write("Data preview (top 10)")
    st.dataframe(filtered.head(10))

with colB:
    st.write("Statistics")
    st.write(filtered.describe(include='all'))

# histogram for numeric
if is_numeric:
    fig, ax = plt.subplots()
    filtered[chosen_x].plot.hist(ax=ax, bins=30)
    ax.set_title(f"Histogram of {chosen_x}")
    st.pyplot(fig)

# --- Download filtered data ---
st.markdown("---")
st.subheader("Download")

# prepare bytes
out_geojson = filtered.to_file(driver="GeoJSON", filename="/tmp/filtered.geojson")
# instead of writing to disk then reading, produce in-memory
buffer = io.BytesIO()
filtered.to_file(buffer, driver="GeoJSON")
buffer.seek(0)

st.download_button(
    label="Download filtered GeoJSON",
    data=buffer,
    file_name="filtered.geojson",
    mime="application/geo+json"
)

st.success("Finished rendering. Use the controls on the left to change source, layer, and filters.")

