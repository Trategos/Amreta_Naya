import streamlit as st
import geopandas as gpd
import folium
from folium.plugins import Fullscreen
from streamlit_folium import st_folium
import tempfile
import requests
from pathlib import Path

st.set_page_config(page_title="GPKG Viewer", layout="wide")

st.title("📦 GPKG Viewer from GitHub LFS")

# -----------------------------------------------------------
# Function to download file from GitHub LFS (direct media link)
# -----------------------------------------------------------
def download_from_github_lfs(url):
    try:
        st.info("Downloading file from GitHub LFS…")
        r = requests.get(url, allow_redirects=True, stream=True)

        if r.status_code != 200:
            st.error(f"Failed to download file. HTTP Status: {r.status_code}")
            return None

        # Save to temporary file
        tmp_path = Path(tempfile.gettempdir()) / "dataset.gpkg"
        with open(tmp_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        st.success(f"GPKG downloaded: {tmp_path}")
        return str(tmp_path)

    except Exception as e:
        st.error(f"❌ Error downloading file: {e}")
        return None


# -----------------------------------------------------------
# GitHub LFS Link Input
# -----------------------------------------------------------
default_url = (
    "https://media.githubusercontent.com/media/Trategos/Amreta_Naya/main/"
    "Impacts_building_footprints_Current_2029_8percent_no_measures.gpkg"
)

url = st.text_input("GitHub LFS GPKG URL:", value=default_url)

if st.button("Load GPKG"):
    gpkg_path = download_from_github_lfs(url)

    if gpkg_path:
        try:
            st.info("Reading GPKG layers…")

            # List layers safely
            layers = gpd.io.file.fiona.listlayers(gpkg_path)

            if not layers:
                st.error("No layers found inside the GPKG.")
                st.stop()

            selected_layer = st.selectbox("Select layer:", layers)

            gdf = gpd.read_file(gpkg_path, layer=selected_layer)
            st.success(f"Loaded layer: {selected_layer}")

            # Show DataFrame preview
            st.subheader("📊 Data Preview")
            st.dataframe(gdf.head())

            # -----------------------------------------------------------
            # MAP VIEWER
            # -----------------------------------------------------------
            st.subheader("🗺️ Map Viewer")

            # Reproject to WGS84 for web mapping
            if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
                gdf = gdf.to_crs(4326)

            # Create map
            centroid = gdf.geometry.iloc[0].centroid
            m = folium.Map(location=[centroid.y, centroid.x], zoom_start=12)
            Fullscreen().add_to(m)

            folium.GeoJson(
                gdf,
                name="GPKG Layer",
                tooltip=folium.GeoJsonTooltip(fields=gdf.columns[:5].tolist())
            ).add_to(m)

            st_folium(m, height=600, width=1200)

        except Exception as e:
            st.error(f"❌ Failed to read GPKG: {e}")
