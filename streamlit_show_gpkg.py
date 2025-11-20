import streamlit as st
import geopandas as gpd
import pydeck as pdk
import requests
import tempfile
from shapely.geometry import mapping

st.set_page_config(page_title="GPKG Viewer", layout="wide")

# ---------------------------
# Google Drive downloader
# ---------------------------
def download_from_google_drive(url, output_path):
    session = requests.Session()
    response = session.get(url, stream=True)

    # Check for Google Drive download confirmation token
    token = None
    for key, value in response.cookies.items():
        if key.startswith("download_warning"):
            token = value

    if token:
        url = url + "&confirm=" + token
        response = session.get(url, stream=True)

    with open(output_path, "wb") as f:
        for chunk in response.iter_content(32768):
            if chunk:
                f.write(chunk)

    return output_path


# ---------------------------
# Sidebar
# ---------------------------
st.sidebar.header("Online Sources")

drive_url = st.sidebar.text_input(
    "Google Drive direct download link (uc?export=download&id=...)",
    value="https://drive.google.com/uc?export=download&id=1mm8RVDsImtHyal5h8UuCz4hOVCigolf2"
)

use_uploader = st.sidebar.checkbox(
    "Use browser file uploader? (for small files < 100MB)",
    value=False
)

st.title("🌍 GPKG Viewer (Google Drive Compatible)")


# ---------------------------
# File input logic
# ---------------------------
gpkg_file = None

if use_uploader:
    uploaded = st.file_uploader("Upload a .gpkg file", type=["gpkg"])
    if uploaded:
        temp = tempfile.NamedTemporaryFile(delete=False, suffix=".gpkg")
        temp.write(uploaded.read())
        gpkg_file = temp.name
else:
    if st.sidebar.button("Download from Google Drive"):
        with st.spinner("Downloading .gpkg from Google Drive..."):
            temp = tempfile.NamedTemporaryFile(delete=False, suffix=".gpkg")
            gpkg_path = download_from_google_drive(drive_url, temp.name)
            gpkg_file = gpkg_path
        st.success("Download completed!")


# ---------------------------
# Process and display
# ---------------------------
if gpkg_file:
    st.info(f"Reading file: **{gpkg_file}**")

    try:
        gdf = gpd.read_file(gpkg_file)
        st.success("File loaded successfully!")

        st.subheader("GeoDataFrame Preview")
        st.write(gdf.head())

        # Convert geometries to GeoJSON-friendly structure
        gdf_json = gdf.to_json()

        st.subheader("Map Viewer")
        initial_view_state = pdk.ViewState(
            latitude=gdf.geometry.centroid.y.mean(),
            longitude=gdf.geometry.centroid.x.mean(),
            zoom=11,
            pitch=45
        )

        layer = pdk.Layer(
            "GeoJsonLayer",
            gdf_json,
            pickable=True,
            stroked=True,
            filled=True,
            lineWidthMinPixels=1,
        )

        st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=initial_view_state))

    except Exception as e:
        st.error(f"Error reading GPKG: {e}")
