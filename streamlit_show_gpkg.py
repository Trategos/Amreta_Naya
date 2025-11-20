"""
Streamlit app to visualize a (large) GeoPackage (.gpkg) interactively using pydeck.

Usage:
  1. Save this file as `streamlit_show_gpkg.py`.
  2. Install dependencies (recommended in a virtualenv):
       pip install streamlit geopandas pydeck pyogrio shapely rtree
     Note: geopandas installation may require system libs (gdal, GEOS). If you have trouble,
     use `pip install geopandas` or conda: `conda install -c conda-forge geopandas pyogrio`.
  3. Run:
       streamlit run streamlit_show_gpkg.py

Design notes & performance tips:
 - This app reads the GeoPackage using geopandas with the pyogrio engine for speed.
 - For very large files (100+ MB), avoid uploading via browser; put the .gpkg on the same machine
   and use the file path input. Streamlit file uploader forces an upload through the browser which
   can be slow/unstable for big files.
 - The app offers: layer selection, column selection, bounding-box-based read (to limit data),
   geometry simplification (to reduce payload), and sampling / max-features display.
 - If you need full-scale production use, consider PostGIS and serve vector tiles (e.g. via
   tessera / tegola / TileServer GL) and visualize tiles in the browser.

"""

from typing import Optional
import streamlit as st
import geopandas as gpd
import pydeck as pdk
from shapely.geometry import box
import json
import os

# Use caching to avoid reloading every interaction
@st.cache_data(show_spinner=True)
def load_gpkg(path: str, layer: Optional[str] = None, bbox: Optional[tuple] = None, columns: Optional[list] = None):
    """Load a GeoPackage (optionally restricted by layer, bbox, and subset of columns).
    bbox: (minx, miny, maxx, maxy) in the same CRS as the dataset or in lon/lat if we convert.
    Returns a GeoDataFrame in EPSG:4326 (lon/lat).
    """
    # Prefer pyogrio engine if available
    try:
        # geopandas will auto-detect engine if pyogrio is installed; pass layer and bbox when available
        if bbox is not None:
            # geopandas supports bbox parameter as tuple
            gdf = gpd.read_file(path, layer=layer, bbox=bbox)
        else:
            gdf = gpd.read_file(path, layer=layer)
    except Exception as e:
        # fallback: try without bbox
        gdf = gpd.read_file(path, layer=layer)

    # Subset columns if requested
    if columns:
        cols = [c for c in columns if c in gdf.columns]
        if 'geometry' not in cols:
            cols.append('geometry')
        gdf = gdf[cols]

    # Ensure lon/lat for web mapping
    try:
        gdf = gdf.to_crs(epsg=4326)
    except Exception:
        # If already in 4326 or conversion fails, keep as is
        pass

    return gdf


def simplify_gdf(gdf: gpd.GeoDataFrame, tolerance: float) -> gpd.GeoDataFrame:
    """Simplify geometries to reduce payload. tolerance is in degrees (approx) after conversion to WGS84.
    Larger tolerance -> fewer vertices. Use preserve_topology=True to avoid invalid geometries.
    """
    if tolerance <= 0:
        return gdf

    # shapely's simplify can be slow for huge datasets; operate in chunks if needed
    gdf = gdf.copy()
    gdf['geometry'] = gdf['geometry'].simplify(tolerance, preserve_topology=True)
    return gdf


def gdf_to_geojson_feature_collection(gdf: gpd.GeoDataFrame, properties: Optional[list] = None, max_features: Optional[int] = None):
    """Convert GeoDataFrame to a GeoJSON FeatureCollection (dict) ready for pydeck.
    Optionally select properties and limit number of features (useful for previews).
    """
    if max_features is not None and max_features > 0:
        gdf = gdf.head(max_features)

    if properties:
        props = [p for p in properties if p in gdf.columns]
        # ensure geometry retained
        gdf = gdf[['geometry'] + props]

    # Use GeoDataFrame.to_json() which returns a string
    geojson_str = gdf.to_json()
    return json.loads(geojson_str)


st.set_page_config(page_title="Streamlit GPKG Viewer", layout="wide")
st.title("Streamlit GeoPackage Viewer — fast preview of large .gpkg files")

st.markdown(
    """
    **Tips:** For best performance with large files (~100 MB):
    - Put the .gpkg on the same machine and use the local path input (not the uploader).
    - Use bounding-box reads, column subset, simplify tolerance, or sample by rows.
    - For production-level interactivity, serve vector tiles (PostGIS + tile server) and use map tiles.
    """
)

# --- Sidebar controls ---
# GitHub raw URL input
st.sidebar.header("Online Sources")
sharepoint_url = st.sidebar.text_input("https://puprtes-my.sharepoint.com/:u:/r/personal/.../Impacts_building_footprints.gpkg?download=1
")
st.sidebar.header("GitHub Source")
github_url = st.sidebar.text_input("Raw GitHub URL to .gpkg (optional)")

st.sidebar.header("Data source")
use_uploader = st.sidebar.checkbox("Use browser file uploader? (not recommended for 100 MB)", value=False)

gpkg_path = None
layer_name = None
# -- Priority: SharePoint > GitHub > uploader/local
if sharepoint_url:
    import requests, tempfile
    try:
        r = requests.get(sharepoint_url)
        r.raise_for_status()
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".gpkg")
        tmp.write(r.content)
        tmp.close()
        gpkg_path = tmp.name
        st.sidebar.success("Downloaded from SharePoint")
    except Exception as e:
        st.sidebar.error(f"Failed to download from SharePoint: {e}")
        gpkg_path = None
elif github_url:
    # Download gpkg from GitHub raw URL
    import requests, tempfile
    try:
        r = requests.get(github_url)
        r.raise_for_status()
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".gpkg")
        tmp.write(r.content)
        tmp.close()
        gpkg_path = tmp.name
        st.sidebar.success("Downloaded from GitHub")
    except Exception as e:
        st.sidebar.error(f"Failed to download: {e}")
        gpkg_path = None
elif use_uploader:
    uploaded = st.sidebar.file_uploader("Upload a .gpkg file (browser upload)", type=['gpkg'])
    if uploaded is not None:
        # Save to a temp file
        tmp_path = os.path.join("/tmp", uploaded.name)
        with open(tmp_path, 'wb') as f:
            f.write(uploaded.getbuffer())
        gpkg_path = tmp_path
else:
    gpkg_path = st.sidebar.text_input("Local path to .gpkg (recommended for large files)")

if gpkg_path:
    # list layers
    try:
        layers = gpd.io.file.fiona.listlayers(gpkg_path)
    except Exception:
        layers = []

    if layers:
        layer_name = st.sidebar.selectbox("Layer (table) to load", options=layers)
    else:
        layer_name = st.sidebar.text_input("Layer name (if you know it)")

# --- Read options ---
st.sidebar.header("Load options")
col1, col2 = st.sidebar.columns(2)
with col1:
    max_rows = st.sidebar.number_input("Max features to read (0 = all)", min_value=0, value=0)
with col2:
    simplify_tolerance = st.sidebar.number_input("Simplify tolerance (deg, 0 = none)", min_value=0.0, value=0.0001, format="%.6f")

# Bounding box inputs (optional) — in lon/lat
st.sidebar.markdown("**Optional bounding box to limit read (lon/lat)**")
minx = st.sidebar.number_input("min lon", value=0.0, format="%.6f")
miny = st.sidebar.number_input("min lat", value=0.0, format="%.6f")
maxx = st.sidebar.number_input("max lon", value=0.0, format="%.6f")
maxy = st.sidebar.number_input("max lat", value=0.0, format="%.6f")
use_bbox = st.sidebar.checkbox("Use bounding box?", value=False)

# Column subset selection (after preview of columns)
st.sidebar.markdown("---")
st.sidebar.caption("After loading, you can choose properties to show in popup")

# --- Main area: load and show preview ---
if not gpkg_path:
    st.info("Provide a local path, a GitHub raw URL, or use the uploader in the sidebar to start.")
    st.stop()

load_button = st.sidebar.button("Load data")
if load_button:
    with st.spinner("Reading layer metadata..."):
        try:
            # If user provided bbox, construct shapely box (note: must match file CRS; we'll read full and crop for simplicity)
            bbox_tuple = None
            if use_bbox:
                bbox_tuple = (minx, miny, maxx, maxy)

            gdf = load_gpkg(gpkg_path, layer=layer_name, bbox=bbox_tuple)
        except Exception as e:
            st.error(f"Failed to read file: {e}")
            st.stop()

    st.success(f"Loaded layer with {len(gdf)} features")

    # Show columns and let user pick properties
    st.subheader("Data preview")
    st.write(gdf.head())

    props = st.multiselect("Properties to include in popup (limit for performance)", options=[c for c in gdf.columns if c != 'geometry'], default=None)

    # Apply max rows and sampling
    if max_rows and max_rows > 0 and len(gdf) > max_rows:
        st.warning(f"Limiting to first {max_rows} features for display (data length: {len(gdf)})")
        gdf = gdf.head(max_rows)

    # Simplify geometries
    if simplify_tolerance and simplify_tolerance > 0:
        with st.spinner("Simplifying geometries..."):
            gdf = simplify_gdf(gdf, tolerance=simplify_tolerance)

    # Convert to GeoJSON
    with st.spinner("Converting to GeoJSON for web map..."):
        feature_collection = gdf_to_geojson_feature_collection(gdf, properties=props, max_features=None)

    # Determine center
    try:
        center = [gdf.geometry.centroid.y.mean(), gdf.geometry.centroid.x.mean()]
    except Exception:
        # fallback center
        center = [0, 0]

    st.subheader("Map view")

    # Create pydeck map using GeoJsonLayer
    geojson_layer = pdk.Layer(
        "GeoJsonLayer",
        data=feature_collection,
        pickable=True,
        stroked=False,
        filled=True,
        get_fill_color="[180, 0, 200, 140]",
        get_line_color=[0, 0, 0],
        point_radius_min_pixels=2,
        auto_highlight=True,
        tooltip=True,
    )

    view_state = pdk.ViewState(latitude=center[0], longitude=center[1], zoom=6, bearing=0, pitch=0)
    deck = pdk.Deck(layers=[geojson_layer], initial_view_state=view_state, map_style='light')
    st.pydeck_chart(deck)

    st.markdown("---")
    st.write("You can download the displayed (possibly simplified/trimmed) GeoJSON for use elsewhere:")
    st.download_button(label="Download GeoJSON", data=json.dumps(feature_collection), file_name="preview.geojson", mime="application/json")

    st.info("If the map is slow or doesn't load, try increasing the simplify tolerance, reducing max features, or using a bbox to limit reading.")
else:
    st.info("Click 'Load data' in the sidebar after specifying the gpkg path and options.")


# Footer notes
st.caption("Built with Streamlit + GeoPandas + pydeck. For very large datasets, consider serving vector tiles (PostGIS + tileserver) for best web performance.")

