import streamlit as st
import geopandas as gpd
import leafmap.foliumap as leafmap
import gdown
import os
import time


# ================================================================
# GOOGLE DRIVE CONFIG (YOUR FILE)
# ================================================================
FILE_ID = "1mm8RVDsImtHyal5h8UuCz4hOVCigolf2"
OUTPUT_PATH = "/tmp/dataset.gpkg"
TIMESTAMP_PATH = "/tmp/dataset_timestamp.txt"


# ================================================================
# FORCE DOWNLOAD CONTROL
# ================================================================
force_refresh = st.sidebar.button("🔄 Force Re-download GPKG")


# ================================================================
# DOWNLOAD FUNCTION
# ================================================================
@st.cache_data(show_spinner=True)
def download_gpkg(force=False):
    """Download the GPKG from Google Drive unless forced."""
    
    # If file already exists and refresh not requested → keep cached
    if os.path.exists(OUTPUT_PATH) and not force:
        return OUTPUT_PATH

    # Google Drive direct download link
    url = f"https://drive.google.com/uc?id={FILE_ID}"

    # Download file
    gdown.download(url, OUTPUT_PATH, quiet=False, fuzzy=True)

    # Save timestamp
    with open(TIMESTAMP_PATH, "w") as f:
        f.write(str(time.time()))

    return OUTPUT_PATH


# ================================================================
# EXECUTE DOWNLOAD
# ================================================================
gpkg_path = download_gpkg(force_refresh)

# Timestamp display
if os.path.exists(TIMESTAMP_PATH):
    last_download = float(open(TIMESTAMP_PATH).read())
    st.sidebar.success(
        f"📥 GPKG last downloaded:\n"
        f"**{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(last_download))}**"
    )
else:
    st.sidebar.info("GPKG not downloaded yet.")


# ================================================================
# APP TITLE
# ================================================================
st.title("📍 GPKG Viewer from Google Drive (Streamlit + Leafmap)")


# ================================================================
# LOAD LAYERS
# ================================================================
try:
    layers = gpd.io.file.fiona.listlayers(gpkg_path)
except Exception as e:
    st.error(f"Failed to read layers: {e}")
    st.stop()

layer = st.selectbox("Choose a layer", layers)


# ================================================================
# LOAD SELECTED LAYER
# ================================================================
@st.cache_data(show_spinner=True)
def load_layer(path, layername):
    gdf = gpd.read_file(path, layer=layername)
    try:
        gdf = gdf.to_crs(4326)
    except:
        pass
    return gdf


with st.spinner("Loading GeoDataFrame..."):
    gdf = load_layer(gpkg_path, layer)

st.subheader("📄 Data Preview")
st.dataframe(gdf.head())


# ================================================================
# MAP VIEW
# ================================================================
st.subheader("🗺️ Map Viewer")

if gdf.empty:
    st.warning("Layer contains no features.")
else:
    m = leafmap.Map(center=[gdf.geometry.centroid.y.mean(),
                            gdf.geometry.centroid.x.mean()],
                    zoom=10)

    m.add_gdf(gdf, layer_name=layer)
    m.to_streamlit(height=600)
