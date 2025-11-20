"""
Streamlit interactive dashboard for a GeoPackage (.gpkg)
Rewritten: includes a stable vertical continuous colorbar legend (always visible).
"""

import io
import streamlit as st
import geopandas as gpd
import pandas as pd
import fiona
from streamlit_folium import st_folium
import folium
import matplotlib.pyplot as plt
import mapclassify
from branca import colormap as cm

# -----------------------------------------------------------
# CONFIG
# -----------------------------------------------------------
st.set_page_config(layout="wide", page_title="GPKG Explorer")

DEFAULT_REMOTE_URL = (
    "https://huggingface.co/datasets/trategos/flood-gpkg-datasets/resolve/main/"
    "Impacts_aggregated_Current_2029_8percent_no_measures_DESA.gpkg"
)

# -----------------------------------------------------------
# UTIL FUNCTIONS
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

def add_vertical_colormap_to_map(map_obj, cmap, title="Legend", top_px=80, left_px=20):
    import branca
    import folium

    # Build CSS gradient from colormap
    n = 256
    gradient_colors = [
        f"rgb({int(r*255)}, {int(g*255)}, {int(b*255)})"
        for r, g, b, a in (cmap(i/n) for i in range(n))
    ]
    css_gradient = ",".join(gradient_colors)

    legend_html = f"""
    <div id="legend" style="
        position: fixed;
        z-index: 9999;
        top: {top_px}px;
        left: {left_px}px;
        width: 60px;
        padding: 10px 6px;
        background: rgba(255,255,255,0.95);
        border-radius: 14px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.25);
        font-size: 12px;
    ">
        <div style="font-weight:600; text-align:center; margin-bottom:6px;">
            {title}
        </div>

        <div style="
            width: 22px;
            height: 260px;
            margin: 0 auto;
            border-radius: 6px;
            border: 1px solid #999;
            background: linear-gradient(to bottom, {css_gradient});
        ">
        </div>

        <div style="text-align:center; margin-top:6px; font-size:11px;">
            Max
        </div>
        <div style="text-align:center; margin-top:2px; font-size:11px;">
            Min
        </div>
    </div>
    """

    map_obj.get_root().html.add_child(folium.Element(legend_html))

# -----------------------------------------------------------
# SIDEBAR – DATA SOURCE
# -----------------------------------------------------------
st.sidebar.title("Data Source")
load_mode = st.sidebar.radio("Load GPKG from", ["HuggingFace (default)", "Custom URL"])

gpkg_path = (
    st.sidebar.text_input("Remote GPKG URL", DEFAULT_REMOTE_URL)
    if load_mode == "HuggingFace (default)"
    else st.sidebar.text_input("Enter remote GPKG URL", "https://.../file.gpkg")
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
    try:
        geom_types = gdf.geometry.geom_type.value_counts().to_dict()
    except Exception:
        geom_types = {"unknown": len(gdf)}
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
    try:
        minv = float(gdf[chosen_x].min())
        maxv = float(gdf[chosen_x].max())
    except Exception:
        minv, maxv = 0.0, 1.0
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
# CHOROPLETH: Natural breaks and color ramps
# -----------------------------------------------------------
cmap = None
classifier = None

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

    # Ensure numeric values (float) and ignore NaNs in classification
    values = pd.to_numeric(filtered[chosen_x], errors="coerce").dropna().astype(float)

    try:
        # Classification
        if method == "natural_breaks (Jenks)":
            classifier = mapclassify.NaturalBreaks(values, k=bins)
        elif method == "quantiles":
            classifier = mapclassify.Quantiles(values, k=bins)
        else:
            classifier = mapclassify.EqualInterval(values, k=bins)

        # Attach class index to the filtered dataframe (for potential discrete legend)
        # We'll keep the style coloring via continuous colormap (so the map looks smooth)
        filtered["_class"] = pd.to_numeric(filtered[chosen_x], errors="coerce").map(
            lambda v: int(classifier.find_bin(v)) if pd.notna(v) else -1
        )

        # Continuous colormap (branca)
        vmin, vmax = float(values.min()), float(values.max())
        cmap = getattr(cm.linear, palette_name).scale(vmin, vmax)
        cmap.caption = chosen_x

    except Exception as e:
        st.warning(f"Classification failed: {e}")
        filtered["_class"] = -1
        cmap = cm.LinearColormap(["#cccccc", "#cccccc"])
        cmap.caption = chosen_x

# Style function: use chosen_x property's numeric value to get color from cmap
def style_function(feature):
    props = feature.get("properties", {})
    raw_val = props.get(chosen_x)
    try:
        val = float(raw_val) if raw_val is not None else None
    except Exception:
        val = None

    if val is None or cmap is None:
        return {"fillOpacity": 0.3, "color": "black", "weight": 0.3}

    try:
        fill_color = cmap(val)
    except Exception:
        fill_color = "#999999"

    return {
        "fillColor": fill_color,
        "color": "black",
        "weight": 0.25,
        "fillOpacity": 0.85,
    }

# Add GeoJSON layer
popup_fields = st.multiselect(
    "Popup fields", columns_no_geom, default=columns_no_geom[:5]
)

folium.GeoJson(
    filtered.to_json(),
    style_function=style_function,
    tooltip=folium.GeoJsonTooltip(fields=popup_fields),
    popup=folium.GeoJsonPopup(fields=popup_fields, labels=True),
    name=str(chosen_layer),
).add_to(m)

add_vertical_colormap_to_map(m, cmap, title=chosen_x)

# Add layer control
folium.LayerControl().add_to(m)

# Render map
st_data = st_folium(m, height=600, width=1000)

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
    # dropna to avoid plotting errors
    filtered[chosen_x].dropna().astype(float).plot.hist(ax=ax, bins=30)
    ax.set_title(f"Histogram of {chosen_x}")
    st.pyplot(fig)

# -----------------------------------------------------------
# DOWNLOAD
# -----------------------------------------------------------
st.subheader("Download filtered data")
buffer = io.BytesIO()
# Save as GeoJSON to buffer
try:
    filtered.to_file(buffer, driver="GeoJSON")
    buffer.seek(0)
    st.download_button(
        "Download filtered.geojson",
        data=buffer,
        file_name="filtered.geojson",
        mime="application/geo+json",
    )
except Exception as e:
    st.error(f"Failed to prepare download: {e}")

st.success("Dashboard ready. Adjust filters in the sidebar to explore the data.")



