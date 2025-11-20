import streamlit as st
import geopandas as gpd
import requests
import tempfile
import leafmap.foliumap as leafmap

st.set_page_config(page_title="GPKG Viewer — HF", layout="wide")
st.title("GPKG Viewer from HuggingFace")

FILE_URL = (
    "https://huggingface.co/datasets/trategos/flood-gpkg-datasets/"
    "resolve/main/Impacts_building_footprints_Current_2029_8percent_no_measures.gpkg"
)

st.markdown(f"**Using file URL**: `{FILE_URL}`")

# --- Download the file ---
st.subheader("Step 1 — Download GPKG")

try:
    response = requests.get(FILE_URL, stream=True)
    response.raise_for_status()
except Exception as e:
    st.error(f"❌ Failed to start download: {e}")
    st.stop()

# Save to temp
tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".gpkg")
with open(tmp.name, "wb") as f:
    for chunk in response.iter_content(8192):
        if chunk:
            f.write(chunk)

gpkg_path = tmp.name
st.success(f"GPKG saved to: `{gpkg_path}`")

# --- Validate first bytes (check SQLite signature) ---
st.subheader("Step 2 — Validate File Signature")

with open(gpkg_path, "rb") as f:
    header = f.read(16)

# GPKG (SQLite) files start with: "SQLite format 3\0"
if not header.startswith(b"SQLite format 3"):
    st.error("❌ File signature mismatch: Not a valid SQLite / GPKG file.")
    st.code(header)
    st.stop()
else:
    st.write("✅ Signature looks good for a GPKG (SQLite format).")

# --- List layers ---
st.subheader("Step 3 — List Layers Inside GPKG")

try:
    layers = gpd.io.file.fiona.listlayers(gpkg_path)
    if not layers:
        st.error("❌ No layers found in the GPKG.")
        st.stop()
    st.write("Found layers:", layers)
except Exception as e:
    st.error(f"❌ Error listing layers: {e}")
    st.stop()

# --- Choose a layer ---
selected = st.selectbox("Select layer to display", layers)

# --- Load GeoDataFrame ---
st.subheader("Step 4 — Load Selected Layer")

try:
    gdf = gpd.read_file(gpkg_path, layer=selected)
    st.success(f"Loaded {len(gdf)} features from layer `{selected}`")
    st.dataframe(gdf.head())
except Exception as e:
    st.error(f"❌ Failed to read layer: {e}")
    st.stop()

# --- Map Visualization ---
st.subheader("Step 5 — Display Map")

if gdf.empty:
    st.warning("⚠️ Layer is empty, nothing to display on map.")
else:
    # Reproject if needed
    try:
        if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(4326)
    except Exception:
        pass

    m = leafmap.Map(
        center=[gdf.geometry.centroid.y.mean(), gdf.geometry.centroid.x.mean()],
        zoom=11,
    )
    m.add_gdf(gdf, layer_name=selected)
    m.to_streamlit(height=600)
