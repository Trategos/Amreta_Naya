import streamlit as st
import geopandas as gpd
import tempfile
import requests
import leafmap.foliumap as leafmap

st.set_page_config(page_title="GPKG Viewer", layout="wide")

st.title("🌍 GPKG Web Viewer (HuggingFace Dataset)")
st.markdown("Loads and displays a `.gpkg` directly from HuggingFace.")

# ---------------------------------------------------------
# 1. File URL (HuggingFace)
# ---------------------------------------------------------
FILE_URL = "https://huggingface.co/datasets/trategos/flood-gpkg-datasets/resolve/main/Impacts_building_footprints_Current_2029_8percent_no_measures.gpkg"

st.info(f"Using dataset from HuggingFace:\n{FILE_URL}")

# ---------------------------------------------------------
# 2. Download GPKG
# ---------------------------------------------------------
st.subheader("Step 1 — Downloading GPKG…")

try:
    r = requests.get(FILE_URL, stream=True)
    r.raise_for_status()

    # Detect HTML (means the URL is wrong)
    if r.headers.get("Content-Type", "").startswith("text/html"):
        st.error("❌ ERROR: HuggingFace returned HTML, not the GPKG file.")
        st.stop()

    # Save to temp file
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".gpkg")
    for chunk in r.iter_content(chunk_size=8192):
        if chunk:
            tmp.write(chunk)
    tmp.flush()

    gpkg_path = tmp.name
    st.success(f"GPKG downloaded to: {gpkg_path}")

except Exception as e:
    st.error(f"❌ Failed to download: {e}")
    st.stop()

# ---------------------------------------------------------
# 3. Read available layers
# ---------------------------------------------------------
st.subheader("Step 2 — Reading Layers…")

try:
    layers = gpd.io.file.fiona.listlayers(gpkg_path)
    st.write("Found layers:", layers)
except Exception as e:
    st.error(f"❌ Failed to list layers: {e}")
    st.stop()

# ---------------------------------------------------------
# 4. Select layer
# ---------------------------------------------------------
selected = st.selectbox("Choose a layer to display:", layers)

# ---------------------------------------------------------
# 5. Load selected layer
# ---------------------------------------------------------
st.subheader("Step 3 — Loading Layer…")

try:
    gdf = gpd.read_file(gpkg_path, layer=selected)
    st.success(f"Loaded {len(gdf):,} features.")
    st.write(gdf.head())
except Exception as e:
    st.error(f"❌ Error loading layer: {e}")
    st.stop()

# ---------------------------------------------------------
# 6. Display on map
# ---------------------------------------------------------
st.subheader("Step 4 — Interactive Map")

try:
    m = leafmap.Map(center=[-2, 118], zoom=5)

    m.add_gdf(gdf, layer_name=selected)

    m.to_streamlit(height=700)

except Exception as e:
    st.error(f"❌ Failed to render map: {e}")
