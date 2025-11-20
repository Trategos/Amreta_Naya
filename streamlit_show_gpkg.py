import streamlit as st
import requests
import tempfile
import geopandas as gpd
import pydeck as pdk
import json
import os

# ----------------------------------------------------
# GOOGLE DRIVE DOWNLOADER (robust + handles HTML pages)
# ----------------------------------------------------
def download_from_google_drive(file_id, destination):
    """
    Downloads a file from Google Drive, handling large-file confirmation
    and blocking HTML pages. Ensures binary output before writing to disk.
    """
    session = requests.Session()

    base_url = "https://drive.google.com/uc?export=download"
    response = session.get(base_url, params={'id': file_id}, stream=True)

    # If Drive returns HTML (login page / permissions issue)
    if "text/html" in response.headers.get("Content-Type", ""):
        raise Exception(
            "Google Drive returned HTML instead of file. "
            "Please ensure the file is shared as: Anyone with the link → Viewer."
        )

    # Look for confirmation token for large files
    token = None
    for key, value in response.cookies.items():
        if key.startswith("download_warning"):
            token = value
            break

    # If token found, repeat request with confirmation
    if token:
        response = session.get(
            base_url, params={'id': file_id, 'confirm': token}, stream=True
        )

    # Final HTML check (should never be HTML now)
    if "text/html" in response.headers.get("Content-Type", ""):
        raise Exception(
            "Download blocked by Google Drive. File may not be shared publicly."
        )

    # Write binary GPKG to disk
    with open(destination, "wb") as f:
        for chunk in response.iter_content(32768):
            if chunk:
                f.write(chunk)

    return destination


# ----------------------------------------------------
# LOADING GEO PACKAGE
# ----------------------------------------------------
def load_gpkg(path, layer=None):
    """Load a GPKG and auto-convert to EPSG:4326."""
    gdf = gpd.read_file(path, layer=layer)

    try:
        gdf = gdf.to_crs(4326)
    except:
        pass

    return gdf


# ----------------------------------------------------
# STREAMLIT UI
# ----------------------------------------------------
st.set_page_config(page_title="GPKG Dashboard", layout="wide")
st.title("Google Drive → Streamlit GPKG Viewer")

st.markdown("""
Upload a `.gpkg` file stored in Google Drive and display it on an interactive dashboard.
""")

# DEFAULT YOUR FILE ID
default_id = "1mm8RVDsImtHyal5h8UuCz4hOVCigolf2"

file_id = st.text_input("Google Drive File ID", value=default_id)

if st.button("Load GPKG"):
    try:
        with st.spinner("Downloading from Google Drive..."):
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".gpkg")
            download_from_google_drive(file_id, tmp.name)
            gpkg_path = tmp.name

        st.success("Download successful!")

        # List layers
        import fiona
        layers = fiona.listlayers(gpkg_path)
        layer = st.selectbox("Choose GPKG Layer", layers)

        with st.spinner("Reading GeoPackage..."):
            gdf = load_gpkg(gpkg_path, layer=layer)

        st.success(f"Loaded {len(gdf)} features from layer '{layer}'")
        st.write(gdf.head())

        # Convert to GeoJSON for map
        geojson = json.loads(gdf.to_json())

        # Compute map center
        centroid = gdf.geometry.centroid
        center_lat = float(centroid.y.mean())
        center_lon = float(centroid.x.mean())

        # Display map
        st.subheader("Map View")

        layer = pdk.Layer(
            "GeoJsonLayer",
            data=geojson,
            pickable=True,
            stroked=False,
            filled=True,
            get_fill_color="[200, 30, 0, 160]",
            auto_highlight=True,
        )

        view_state = pdk.ViewState(
            latitude=center_lat, longitude=center_lon, zoom=10
        )

        deck = pdk.Deck(layers=[layer], initial_view_state=view_state)
        st.pydeck_chart(deck)

    except Exception as e:
        st.error(f"❌ Error: {e}")

st.caption("Built with Streamlit + GeoPandas + Google Drive API workaround.")
