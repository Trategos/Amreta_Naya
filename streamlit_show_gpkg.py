import streamlit as st
import geopandas as gpd
import pydeck as pdk
import requests
import tempfile
import re

st.set_page_config(page_title="GPKG Viewer", layout="wide")

# ------------------------------------------------------------
# Google Drive Downloader (WORKS FOR LARGE FILES 100MB+)
# ------------------------------------------------------------
def download_from_google_drive(file_id, destination):
    """
    Downloads ANY file size from Google Drive using file ID.
    Handles confirmation tokens (for large files).
    """
    URL = "https://drive.google.com/uc?export=download"
    session = requests.Session()

    response = session.get(URL, params={'id': file_id}, stream=True)

    # Extract confirmation token
    token = None
    for key, value in response.cookies.items():
        if key.startswith("download_warning"):
            token = value
            break

    if token:
        params = {'id': file_id, 'confirm': token}
        response = session.get(URL, params=params, stream=True)

    # Write binary file
    with open(destination, "wb") as f:
        for chunk in response.iter_content(32768):
            if chunk:
                f.write(chunk)

    return destination


# ------------------------------------------------------------
# Extract File ID from ANY Google Drive link
# ------------------------------------------------------------
def extract_drive_id(url):
    """
    Extracts Google Drive file ID from different URL formats.
    """
    patterns = [
        r"https://drive\.google\.com/file/d/([a-zA-Z0-9_-]+)",  # main format
        r"id=([a-zA-Z0-9_-]+)",  # uc?export=download&id=
    ]

    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)

    return None


# ------------------------------------------------------------
# SIDEBAR UI
# ------------------------------------------------------------
st.sidebar.header("Google Drive Input")

default_url = "https://drive.google.com/file/d/1mm8RVDsImtHyal5h8UuCz4hOVCigolf2/view?usp=drive_link"

drive_url = st.sidebar.text_input("Google Drive File URL:", value=default_url)

use_uploader = st.sidebar.checkbox("Use browser uploader? (Small files only)", value=False)

st.title("🌍 GPKG Viewer — Google Drive Compatible")


# ------------------------------------------------------------
# File source selection
# ------------------------------------------------------------
gpkg_file = None

# Option 1 — Upload
if use_uploader:
    uploaded_file = st.file_uploader("Upload .gpkg file", type=["gpkg"])
    if uploaded_file:
        temp = tempfile.NamedTemporaryFile(delete=False, suffix=".gpkg")
        temp.write(uploaded_file.read())
        gpkg_file = temp.name

# Option 2 — Google Drive
else:
    file_id = extract_drive_id(drive_url)

    if not file_id:
        st.sidebar.error("❌ Could not detect Google Drive File ID from the URL.")
    else:
        st.sidebar.success(f"📄 File ID detected: {file_id}")
        if st.sidebar.button("Download from Google Drive"):
            with st.spinner("Downloading .gpkg from Google Drive..."):
                temp = tempfile.NamedTemporaryFile(delete=False, suffix=".gpkg")
                gpkg_path = download_from_google_drive(file_id, temp.name)
                gpkg_file = gpkg_path
            st.success("Download completed!")


# ------------------------------------------------------------
# Read and Display GPKG Map
# ------------------------------------------------------------
if gpkg_file:
    st.info(f"Reading file from: **{gpkg_file}**")

    try:
        gdf = gpd.read_file(gpkg_file)

        st.success("File loaded successfully!")

        st.subheader("📋 Data Preview")
        st.write(gdf.head())

        # Convert to JSON for PyDeck
        gdf_json = gdf.to_json()

        st.subheader("🗺️ Map Viewer")

        centroid = gdf.geometry.centroid
        view_state = pdk.ViewState(
            latitude=centroid.y.mean(),
            longitude=centroid.x.mean(),
            zoom=12,
            pitch=45,
        )

        layer = pdk.Layer(
            "GeoJsonLayer",
            gdf_json,
            pickable=True,
            stroked=True,
            filled=True,
            lineWidthMinPixels=1,
        )

        st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state))

    except Exception as e:
        st.error(f"❌ Error reading GPKG: {e}")
