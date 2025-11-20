"""
Streamlit interactive dashboard for a GeoPackage (.gpkg)
Updated: Removed text search, fixed interactive color scaling,
added natural breaks & color palettes, and a show/hide legend (bottom-left).
"""

import streamlit as st
import geopandas as gpd
import pandas as pd
import fiona
import io
from streamlit_folium import st_folium
import folium
import matplotlib.pyplot as plt
import mapclassify
from branca import colormap as cm
import numpy as np

# -----------------------------------------------------------
# CONFIG
# -----------------------------------------------------------
st.set_page_config(layout="wide", page_title="GPKG Explorer")

# NOTE: developer provided local uploaded file path — included as default per your environment.
DEFAULT_REMOTE_URL = "/mnt/data/ecb74d08-ca6a-48fc-8adc-66dad5f06722.png"
# You can keep the HF URL if you want the remote GPKG by default:
# DEFAULT_REMOTE_URL = (
#     "https://huggingface.co/datasets/trategos/flood-gpkg-datasets/resolve/main/"
#     "Impacts_aggregated_Current_2029_8percent_no_measures_DESA.gpkg"
# )

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
        return gpd.read_file(path_or_url, layer=layer_name)
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
load_mode = st.sidebar.radio("Load GPKG from", ["HuggingFace (default)", "Custom URL", "Local file (uploaded)"])

if load_mode == "HuggingFace (default)":
    gpkg_path = st.sidebar.text_input("Remote GPKG URL", DEFAULT_REMOTE_URL)
elif load_mode == "Custom URL":
    gpkg_path = st.sidebar.text_input("Enter remote GPKG URL", "https://.../file.gpkg")
else:
    # Use uploaded local path as default placeholder (developer-provided)
    gpkg_path = st.sidebar.text_input("Local file path", DEFAULT_REMOTE_URL)

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
    st.sidebar.warning("No layers found.")
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

# Numeric filtering
if is_numeric:
    minv = float(gdf[chosen_x].min())
    maxv = float(gdf[chosen_x].max())
    # Protect against identical min/max
    if minv == maxv:
        rmin, rmax = minv, maxv
    else:
        rmin, rmax = st.sidebar.slider(f"Filter {chosen_x}", minv, maxv, (minv, maxv))
    filtered = filtered[(filtered[chosen_x] >= rmin) & (filtered[chosen_x] <= rmax)]
else:
    unique_vals = sorted(filtered[chosen_x].dropna().unique().tolist())
    sel = st.sidebar.multiselect(f"Select values in {chosen_x}", unique_vals)
    if sel:
        filtered = filtered[filtered[chosen_x].isin(sel)]

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
    "Base tiles",
    ["OpenStreetMap", "Stamen Terrain", "Stamen Toner", "CartoDB positron"]
)

m = folium.Map(location=center, zoom_start=8, tiles=map_tiles)

# -----------------------------------------------------------
# USER OPTION: show/hide legend (bottom-left)
# -----------------------------------------------------------
show_legend = st.sidebar.checkbox("Show legend", value=True)

# -----------------------------------------------------------
# CHOROPLETH: Natural breaks and color ramps
# -----------------------------------------------------------
cmap = None
classifier = None
values = None

if is_numeric and len(filtered) > 0:

    st.sidebar.markdown("### Choropleth Options")

    method = st.sidebar.selectbox(
        "Classification method",
        ["natural_breaks (Jenks)", "quantiles", "equal_interval"],
        index=0
    )

    bins = st.sidebar.slider("Number of classes", 3, 9, 5)

    palette_name = st.sidebar.selectbox(
        "Color palette",
        [
            "Blues_09", "Reds_09", "YlOrRd_09",
            "Viridis_09", "PuBu_09", "YlGn_09", "GnBu_09"
        ],
        index=0
    )

    # Extract numeric values for classification (drop NA)
    try:
        values = filtered[chosen_x].astype(float).dropna()
        if len(values) == 0:
            raise ValueError("No numeric values available for chosen column.")
    except Exception as e:
        st.warning(f"Could not convert values to numeric: {e}")
        values = None

    if values is not None:
        try:
            # Classification
            if method == "natural_breaks (Jenks)":
                classifier = mapclassify.NaturalBreaks(values, k=bins)
            elif method == "quantiles":
                classifier = mapclassify.Quantiles(values, k=bins)
            else:
                classifier = mapclassify.EqualInterval(values, k=bins)

            # Attach class id to filtered copy (for possible use)
            filtered["_class"] = classifier.yb.astype(int)

            # Colormap
            vmin, vmax = float(values.min()), float(values.max())
            cmap = getattr(cm.linear, palette_name).scale(vmin, vmax)

        except Exception as e:
            st.warning(f"Classification failed: {e}")
            classifier = None
            cmap = cm.LinearColormap(['#cccccc', '#cccccc'])

# Style function
def style_function(feature):
    try:
        value = feature["properties"].get(chosen_x)
    except Exception:
        value = None

    if cmap is None or value is None:
        return {"fillOpacity": 0.3, "color": "black", "weight": 0.3}

    # If value cannot be cast to float, use fallback color
    try:
        return {
            "fillColor": cmap(float(value)),
            "color": "black",
            "weight": 0.25,
            "fillOpacity": 0.85,
        }
    except Exception:
        return {"fillOpacity": 0.3, "color": "black", "weight": 0.3}

# Add GeoJSON
popup_fields = st.multiselect(
    "Popup fields", columns_no_geom, default=columns_no_geom[:5]
)

folium.GeoJson(
    filtered.to_json(),
    style_function=style_function,
    tooltip=folium.GeoJsonTooltip(fields=popup_fields),
    popup=folium.GeoJsonPopup(fields=popup_fields, labels=True),
).add_to(m)

# -----------------------------------------------------------
# CLEAN STACKED LEGEND (bottom-left) — only if user wants it
# -----------------------------------------------------------
if show_legend and cmap is not None and values is not None:

    # Try to get class breaks from classifier; fallback to equal-interval bins
    try:
        bins_list = list(classifier.bins)
    except Exception:
        # fallback: create evenly spaced bins
        vmin, vmax = float(values.min()), float(values.max())
        bins_list = list(np.linspace(vmin, vmax, num=5)[1:])  # default 4 breaks

    # Build readable labels (prev – current)
    labels = []
    prev = float(values.min())
    for b in bins_list:
        labels.append((prev, float(b)))
        prev = float(b)
    # Add final class upperbound if desired (last bin to max)
    if len(labels) == 0:
        labels = [(float(values.min()), float(values.max()))]

    # Build legend HTML (stacked, bottom-left)
    legend_items_html = ""
    for i, (low, high) in enumerate(labels):
        # midpoint for color sampling
        mid = (low + high) / 2.0
        try:
            color = cmap(mid)
        except Exception:
            color = "#cccccc"
        low_s = f"{low:,.0f}"
        high_s = f"{high:,.0f}"
        legend_items_html += f"""
            <div style="display:flex; align-items:center; margin-bottom:6px;">
                <div style="width:18px; height:18px; background:{color}; opacity:0.85; border:1px solid #666; margin-right:8px;"></div>
                <div style="font-size:12px;">{low_s} — {high_s}</div>
            </div>
        """

    # Final legend HTML block positioned bottom-left
    legend_html = f"""
        <div id="gpkg-legend" style="
            position: fixed;
            bottom: 20px;
            left: 20px;
            z-index: 9999;
            background-color: white;
            padding: 10px 12px;
            border: 1px solid rgba(0,0,0,0.15);
            border-radius: 6px;
            box-shadow: 0 2px 6px rgba(0,0,0,0.15);
            max-width: 220px;
            font-family: Arial, sans-serif;
        ">
            <div style="font-weight:600; margin-bottom:8px; font-size:13px;">{chosen_x}</div>
            {legend_items_html}
            <div style="font-size:11px; color:#666; margin-top:6px;">Classification: {method}</div>
        </div>
    """

    m.get_root().html.add_child(folium.Element(legend_html))

# -----------------------------------------------------------
# If using the default branca colormap (optional), keep it hidden
# -----------------------------------------------------------
# We do not call cmap.add_to(m) to avoid the horizontal messy legend.
# If desired for debugging, uncomment the following line:
# if cmap: cmap.add_to(m)

# Render map
st_folium(m, height=600, width=1000)

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

# Histogram
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
