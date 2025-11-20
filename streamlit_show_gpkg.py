import streamlit as st
import geopandas as gpd
import leafmap.foliumap as leafmap
import gdown
import os

st.set_page_config(page_title="GPKG Live Dashboard", layout="wide")

FILE_ID = "1mm8RVDsImtHyal5h8UuCz4hOVCigolf2"
OUTPUT_PATH = "/tmp/dataset.gpkg"

st.title("📍 Live GPKG Dashboard from Google Drive")
st.write("This app loads the GPKG file directly from Google Drive automatically.")

# ---- DOWNLOAD FROM GOOGLE DRIVE ---- #
@st.cache_data(show_spinner=True)
def download_gpkg():
    if os.path.exists(OUTPUT_PATH):
        return OUTPUT_PATH

    url = f"https://drive.google.com/uc?id={FILE_ID}"
    gdown.download(url, OUTPUT_PATH, quiet=False, fuzzy=True)

    return OUTPUT_PATH

st.info("Downloading file from Google Drive…")
try:
    gpkg_path = download_gpkg()
    st.success(f"GPKG loaded: {gpkg_path}")

    # ---- LIST GPKG LAYERS ---- #
    layers = gpd.io.file.fiona.listlayers(gpkg_path)
    st.subheader("📚 Layers Found")
    st.write(layers)

    layer_choice = st.selectbox("Choose a layer to display:", layers)

    # ---- LOAD SELECTED LAYER ---- #
    gdf = gpd.read_file(gpkg_path, layer=layer_choice)

    st.subheader("🔢 First Rows")
    st.dataframe(gdf.head())

    # ---- MAP ---- #
    st.subheader("🗺️ Map Viewer")
    m = leafmap.Map(center=[-2, 118], zoom=5)
    m.add_gdf(gdf, layer_name=layer_choice)
    m.to_streamlit(width="100%", height=600)

except Exception as e:
    st.error(f"❌ Error reading file: {e}")
