import streamlit as st
import geopandas as gpd
import gdown
import os
import fiona
import leafmap.foliumap as leafmap

st.set_page_config(page_title="GPKG Live Dashboard", layout="wide")

FILE_ID = "1mm8RVDsImtHyal5h8UuCz4hOVCigolf2"
OUTPUT_PATH = "/tmp/dataset.gpkg"

st.title("📍 Live GPKG Dashboard from Google Drive")
st.write("Loads large GPKG directly from Google Drive.")

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

    layers = fiona.listlayers(gpkg_path)
    st.subheader("📚 Layers in GPKG")
    st.write(layers)

    layer_choice = st.selectbox("Choose a layer:", layers)

    # ---- LOAD LAYER ----
    gdf = gpd.read_file(gpkg_path, layer=layer_choice)

    # ---- FIX GEOMETRIES ----
    if gdf.crs is None:
        st.warning("CRS missing → assuming EPSG:4326")
        gdf = gdf.set_crs("EPSG:4326")
    else:
        gdf = gdf.to_crs("EPSG:4326")

    gdf["geometry"] = gdf["geometry"].buffer(0)

    st.subheader("🔢 Data Preview")
    st.dataframe(gdf.head())

    # ---- DEBUG CHECK ----
    st.write("Geometry type:", gdf.geom_type.unique())
    st.write("CRS:", gdf.crs)
    st.write("Non-null geometries:", gdf.geometry.notnull().sum())

    if gdf.geometry.notnull().sum() == 0:
        st.error("❌ No valid geometries found. Map cannot render.")
    else:
        # ---- MAP VIEW ----
        st.subheader("🗺️ Map Viewer")
        m = leafmap.Map()

        # Zoom to data extent
        bounds = gdf.total_bounds   # [minx, miny, maxx, maxy]
        center = [(bounds[1]+bounds[3])/2, (bounds[0]+bounds[2])/2]

        m.set_center(center[1], center[0], zoom=14)
        m.add_gdf(gdf, layer_name=layer_choice)

        m.to_streamlit(width="100%", height=600)

except Exception as e:
    st.error(f"❌ Error: {e}")
