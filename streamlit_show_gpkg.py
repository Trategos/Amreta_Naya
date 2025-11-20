import streamlit as st
import sqlite3
import os
import geopandas as gpd
import leafmap.foliumap as leafmap
import tempfile
import requests

st.title("GPKG Deep Diagnostic Viewer")

FILE_URL = "https://huggingface.co/datasets/trategos/flood-gpkg-datasets/resolve/main/Impacts_building_footprints_Current_2029_8percent_no_measures.gpkg"

# --- Download file ---
response = requests.get(FILE_URL, stream=True)
tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".gpkg")
with open(tmp.name, "wb") as f:
    for chunk in response.iter_content(8192):
        f.write(chunk)

gpkg = tmp.name
st.success(f"Downloaded: {gpkg}")

# --- 1) CHECK SIGNATURE ---
with open(gpkg, "rb") as f:
    header = f.read(16)

if header.startswith(b"SQLite format 3"):
    st.write("✅ SQLite signature confirmed")
else:
    st.error("❌ Not a valid SQLite/GPKG file")

# --- 2) INSPECT RAW SQL STRUCTURE ---
st.subheader("SQLite Tables Inside GPKG")

try:
    conn = sqlite3.connect(gpkg)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]
    st.write(tables)
except Exception as e:
    st.error(f"SQLite read error: {e}")

# --- 3) CHECK GPKG CONTENTS TABLE ---
if "gpkg_contents" in tables:
    st.subheader("gpkg_contents table:")
    cur.execute("SELECT table_name, data_type, identifier FROM gpkg_contents")
    contents = cur.fetchall()
    st.write(contents)
else:
    st.warning("⚠️ gpkg_contents missing → INVALID GPKG structure")

# --- 4) TRY TO LIST LAYERS WITH GEOPANDAS ---
st.subheader("Geopandas layer listing")

try:
    layers = gpd.io.file.fiona.listlayers(gpkg)
    st.success(layers)
except Exception as e:
    st.error(f"❌ Fiona cannot read layers: {e}")
