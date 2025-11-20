import streamlit as st
import os
import geopandas as gpd
from folium import Map, GeoJson
from streamlit_folium import st_folium
import requests
import tempfile

st.set_page_config(page_title="GPKG Viewer", layout="wide")

def download_from_gdrive(url):
    """Download a Google Drive large file using file ID token."""
    if "id=" in url:
        file_id = url.split("id=")[1]
    elif "/d/" in url:
        file_id = url.split("/d/")[1].split("/")[0]
    else:
        raise ValueError("Invalid Google Drive link format.")

    download_url = f"https://drive.google.com/uc?export=download&id={file_id}"

    session = requests.Session()
    response = session.get(download_url, stream=True)

    # Handle large-file confirmation token
    for key, value in response.cookies.items():
        if key.startswith("download_warning"):
            download_url = f"https://drive.google.com/uc?export=download&id={file_id}&confirm={value}"
            response = session.get(download_url, stream=True)
            break

    # Save to temp file
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".gpkg")
    with open(tmp.name, "wb") as f:
        for chunk in response.iter_content(32768):
            if chunk:
                f.write(chunk)

    return tmp.name


def load_gpkg_layers(gpkg_path):
    """Return list of layer names and the first layer GeoDataFrame."""
    try:
        layers = gpd.io.file.fiona.listlayers(gpkg_path)
        return layers
    except Exception as e:
        st.error(f"❌ Failed to read layers: {e}")
        return None


def load_layer(gpkg_path, layer_name):
    try:
        return gpd.read_file(gpkg_path, layer=layer_name)
    except Exception as e:
        st.error(f"❌ Failed loading layer: {e}")
        return None


st.title("🌍 GPKG File Viewer (Google Drive)")

url = st.text_input("Enter Google Drive link:", 
    "https://drive.google.com/file/d/1yXLhlEOvd7AVHc9-9n8ZjLFCLjCR1C6y/view?usp=drive_link")

if st.button("Load GPKG"):
    with st.spinner("Downloading from Google Drive…"):
        gpkg_path = download_from_gdrive(url)

    st.success(f"GPKG downloaded: {gpkg_path}")

    layers = load_gpkg_layers(gpkg_path)

    if layers:
        st.success(f"Available layers: {layers}")
        layer_name = st.selectbox("Select a layer", layers)

        gdf = load_layer(gpkg_path, layer_name)

        if gdf is not None and not gdf.empty:

            center = [gdf.geometry.iloc[0].centroid.y, gdf.geometry.iloc[0].centroid.x]
            m = Map(location=center, zoom_start=11)

            GeoJson(gdf).add_to(m)

            st_folium(m, width=1000, height=600)
        else:
            st.error("Layer loaded but empty or invalid.")
