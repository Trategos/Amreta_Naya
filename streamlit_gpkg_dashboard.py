"""
Streamlit interactive dashboard for a GeoPackage (.gpkg)
Updated: Removed text search, fixed interactive color scaling,
added natural breaks & color palettes.
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
import streamlit.components.v1 as components
import os
import requests

# -----------------------------------------------------------
# CONFIG
# -----------------------------------------------------------
st.set_page_config(layout="wide", page_title="Amreta Naya Dashboard")

# Manually list the GPKG files you want to offer
GPKG_OPTIONS = {
    "2029 – 8% No Measures":
        "https://huggingface.co/datasets/trategos/flood-gpkg-datasets/resolve/main/"
        "Impacts_aggregated_Current_2029_8percent_no_measures_DESA.gpkg",

    "2029 – 5% No Measures":
        "https://huggingface.co/datasets/trategos/flood-gpkg-datasets/resolve/main/"
        "Impacts_aggregated_Current_2029_5percent_no_measures_DESA.gpkg",

    "2029 – 8% NbS":
        "https://huggingface.co/datasets/trategos/flood-gpkg-datasets/resolve/main/"
        "Impacts_aggregated_Current_2029_8percent_NBS_easternrivers_DESA.gpkg",

    "2029 – 5% NbS":
        "https://huggingface.co/datasets/trategos/flood-gpkg-datasets/resolve/main/"
        "Impacts_aggregated_Current_2029_5percent_NBS_easternrivers_DESA.gpkg",

    "2029 – 8% Grey+Green":
        "https://huggingface.co/datasets/trategos/flood-gpkg-datasets/resolve/main/"
        "Impacts_aggregated_Current_2029_8percent_Strategi_BBWS_All_DESA.gpkg",

    "2029 – 5% Grey+Green":
        "https://huggingface.co/datasets/trategos/flood-gpkg-datasets/resolve/main/"
        "Impacts_aggregated_Current_2029_5percent_Strategi_BBWS_All_DESA.gpkg"
}

DEFAULT_LABEL = "2029 – 8% No Measures"

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

def extract_scenario_name(gpkg_url: str):
    """
    Convert GPKG filename into scenario name.
    Example:
        Impacts_aggregated_Current_2029_5percent_NBS_easternrivers_DESA.gpkg
    →   Current_2029_5percent_NBS_easternrivers
    """
    fn = os.path.basename(gpkg_url)
    fn = fn.replace("Impacts_aggregated_", "").replace("_DESA.gpkg", "")
    return fn

# -----------------------------------------------------------
# SIDEBAR – DATA SOURCE
# -----------------------------------------------------------
st.sidebar.title("Data Source")

mode = st.sidebar.radio("Load GPKG from", ["Choose from list", "Custom URL"])

if mode == "Choose from list":
    labels = list(GPKG_OPTIONS.keys())
    default_index = labels.index(DEFAULT_LABEL) if DEFAULT_LABEL in labels else 0
    selected_label = st.sidebar.selectbox("Select dataset", labels, index=default_index)
    gpkg_path = GPKG_OPTIONS[selected_label]
else:
    gpkg_path = st.sidebar.text_input("Enter remote GPKG URL", "")

if not gpkg_path:
    st.stop()

# -----------------------------------------------------------
# LOAD LAYERS
# -----------------------------------------------------------
st.sidebar.markdown("---")
st.sidebar.write("### Layer selection")

with st.spinner("Listing layers..."):
    layers = list_layers(gpkg_path)

if layers:
    chosen_layer = st.sidebar.selectbox("Choose layer", layers)
else:
    st.sidebar.warning("No layers found.")
    chosen_layer = None

# -----------------------------------------------------------
# LOAD SELECTED LAYER
# -----------------------------------------------------------
st.title("Amreta Naya Interactive Dashboard")

with st.spinner("Loading selected layer…"):
    gdf = load_layer(gpkg_path, chosen_layer)

if gdf is None:
    st.stop()

gdf = safe_to_crs(gdf)

# -----------------------------------------------------------
# LOAD METRICS HTML (LOCAL FIRST, HF FALLBACK)
# -----------------------------------------------------------
scenario = extract_scenario_name(gpkg_path)
metrics_filename = f"{scenario}_metrics.html"

local_path = f"/mnt/data/{metrics_filename}"
hf_url = (
    "https://huggingface.co/datasets/trategos/flood-gpkg-datasets/resolve/main/"
    + metrics_filename
)

st.markdown("## Flood Risk Information")

html_content = None

# 1️⃣ Try local metrics file
if os.path.exists(local_path):
    with open(local_path, "r", encoding="utf-8") as f:
        html_content = f.read()

# 2️⃣ Try HuggingFace fallback
else:
    try:
        r = requests.get(hf_url)
        if r.status_code == 200:
            html_content = r.text
    except:
        pass

# 3️⃣ Show HTML (bigger box to prevent map layout issues)

if html_content:
    # Add left padding to avoid cropping
    padded_html = f"""
    <div style="padding-left: 100px; width:100%;">
    {html_content}
    </div>
    """
    components.html(padded_html, height=750, scrolling=True)
else:
    st.info(f"No metrics file found for: {metrics_filename}")

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
    rmin, rmax = st.sidebar.slider(f"Filter {chosen_x}", minv, maxv, (minv, maxv))
    filtered = filtered[(filtered[chosen_x] >= rmin) & (filtered[chosen_x] <= rmax)]
else:
    unique_vals = sorted(filtered[chosen_x].dropna().unique().tolist())
    sel = st.sidebar.multiselect(f"Select values in {chosen_x}", unique_vals)
    if sel:
        filtered = filtered[filtered[chosen_x].isin(sel)]
# -----------------------------------------------------------
# FLOOD EVENT VIDEO TOGGLE (LOCAL FIRST, HF FALLBACK)
# -----------------------------------------------------------
st.markdown("### Flood Event Animation")

show_video = st.checkbox("▶ Show the Flood Event", value=False)

VIDEO_LOCAL = "/mnt/data/Latest.mp4"
VIDEO_HF = (
    "https://huggingface.co/datasets/trategos/flood-gpkg-datasets/"
    "resolve/main/Latest.mp4"
)

if show_video:
    if os.path.exists(VIDEO_LOCAL):
        # Play local video
        st.video(VIDEO_LOCAL, format="video/mp4")
        st.caption("Flood event animation (local file).")
    else:
        # Play video from HuggingFace
        st.video(VIDEO_HF)
        st.caption("Flood event animation loaded from Hugging Face.")

# -----------------------------------------------------------
# MAP
# -----------------------------------------------------------
st.subheader("Interactive Map")

try:
    c = filtered.geometry.unary_union.centroid
    center = [c.y, c.x]
except:
    center = [0, 0]

map_tiles = st.sidebar.selectbox(
    "Base tiles",
    ["OpenStreetMap", "Stamen Terrain", "Stamen Toner", "CartoDB positron"]
)

m = folium.Map(location=center, zoom_start=8, tiles=map_tiles)

cmap = None

if is_numeric and len(filtered) > 0:
    st.sidebar.markdown("### Choropleth Options")

    method = st.sidebar.selectbox(
        "Classification method",
        ["natural_breaks (Jenks)", "quantiles", "equal_interval"], index=0
    )

    bins = st.sidebar.slider("Number of classes", 3, 9, 5)

    palette_name = st.sidebar.selectbox(
        "Color palette",
        ["Blues_09", "Reds_09", "YlOrRd_09", "Viridis_09",
         "PuBu_09", "YlGn_09", "GnBu_09"],
        index=0
    )

    values = filtered[chosen_x].astype(float)

    try:
        if method == "natural_breaks (Jenks)":
            classifier = mapclassify.NaturalBreaks(values, k=bins)
        elif method == "quantiles":
            classifier = mapclassify.Quantiles(values, k=bins)
        else:
            classifier = mapclassify.EqualInterval(values, k=bins)

        filtered["_class"] = classifier.yb
        cmap = getattr(cm.linear, palette_name).scale(values.min(), values.max())

    except:
        filtered["_class"] = -1
        cmap = cm.LinearColormap(["#cccccc", "#cccccc"])

def style_function(feature):
    v = feature["properties"].get(chosen_x)
    if cmap is None or v is None:
        return {"fillOpacity": 0.3, "color": "black", "weight": 0.3}
    return {"fillColor": cmap(v), "color": "black", "weight": 0.25, "fillOpacity": 0.85}

popup_fields = st.multiselect("Popup fields", columns_no_geom, default=columns_no_geom[:5])

folium.GeoJson(
    filtered.to_json(),
    style_function=style_function,
    tooltip=folium.GeoJsonTooltip(fields=popup_fields),
    popup=folium.GeoJsonPopup(fields=popup_fields, labels=True),
).add_to(m)

if cmap:
    cmap.add_to(m)

st_folium(m, height=600, width=1000)

# -----------------------------------------------------------
# STATS & CHARTS
# -----------------------------------------------------------
st.subheader("Statistics & Charts")
colA, colB = st.columns(2)

with colA:
    st.dataframe(filtered.head(10))

with colB:
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
    buffer,
    "filtered.geojson",
    "application/geo+json",
)

st.success("Dashboard ready. Adjust filters in the sidebar to explore the data.")

# -----------------------------------------------------------
# BEAUTIFUL INTERACTIVE DONUT CHART BCR CALCULATOR
# -----------------------------------------------------------
import plotly.graph_objects as go

st.markdown("## Benefit–Cost Ratio (BCR) Calculator")

# Load BCR.csv from HuggingFace
BCR_URL = "https://huggingface.co/datasets/trategos/flood-gpkg-datasets/resolve/main/BCR.csv"

try:
    bcr_df = pd.read_csv(BCR_URL, sep=";")
except Exception as e:
    st.error(f"Failed to load BCR.csv from HuggingFace: {e}")
    st.stop()

# Identify scenario key to match with CSV
scenario_key = extract_scenario_name(gpkg_path)

matched = bcr_df[bcr_df["Skenario"]
                 .str.contains(scenario_key, case=False, na=False)]

if matched.empty:
    st.warning(f"No BCR record found for: {scenario_key}")
else:
    row = matched.iloc[0]

    # Convert Rp text → number
    def parse_rupiah(x):
        if isinstance(x, str):
            x = x.replace("Rp", "").replace(".", "").replace(",", "").strip()
        try:
            return float(x)
        except:
            return None

    # Extract from CSV
    benefit = parse_rupiah(row["Benefit"])
    baseline_bcr = float(row["Nilai BCR"])   # CSV already includes BCR
    base_cost = benefit / baseline_bcr  # Derive cost

    # Display baseline values
    st.write(f"**Benefit (CSV):** Rp {benefit:,.0f}")
    st.write(f"**Baseline Cost (derived):** Rp {base_cost:,.0f}")
    st.metric("Baseline BCR", f"{baseline_bcr:.3f}")

    st.markdown("---")

    # -------------------------------------------------------
    # INTERACTIVE DONUT CHART FUNCTION (Plotly)
    # -------------------------------------------------------
    def draw_donut(benefit_val, cost_val, bcr_value, title):
        labels = ["Benefit", "Cost"]
        values = [benefit_val, cost_val]
        colors = ["green", "red"]

        fig = go.Figure(data=[go.Pie(
            labels=labels,
            values=values,
            hole=0.55,
            marker=dict(colors=colors),
            hovertemplate="<b>%{label}</b><br>Rp %{value:,.0f}<extra></extra>",
            textinfo="none"
        )])

        fig.add_annotation(
            x=0.5, y=0.5,
            text=f"<b>{bcr_value:.2f}</b>",
            showarrow=False,
            font=dict(size=22)
        )

        fig.update_layout(
            title=dict(text=title, x=0.5),
            height=360, width=360,
            margin=dict(l=10, r=10, t=50, b=10)
        )

        st.plotly_chart(fig, use_container_width=False)

    # -------------------------------------------------------
    # BASELINE DONUT
    # -------------------------------------------------------
    st.subheader("Baseline BCR (from dataset)")
    draw_donut(benefit, base_cost, baseline_bcr, "Baseline BCR")

    st.markdown("---")

    # -------------------------------------------------------
    # USER UPDATED BCR CALCULATION
    # -------------------------------------------------------
    user_cost_string = st.text_input(
        "Enter your estimated CAPEX (Rp)",
        placeholder="e.g. 1500000000000"
    )

    if user_cost_string:
        new_cost = parse_rupiah(user_cost_string)

        if new_cost is None:
            st.error("Invalid CAPEX format. Enter a proper number or Rp text.")
        else:
            new_bcr = benefit / new_cost

            st.subheader("Updated BCR (with your CAPEX)")
            st.write(f"**Your Cost:** Rp {new_cost:,.0f}")

            draw_donut(benefit, new_cost, new_bcr, "Updated BCR")
















