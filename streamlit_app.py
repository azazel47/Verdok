import streamlit as st
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, Polygon
import tempfile
import os
import requests
from io import BytesIO
import json
import datetime
import zipfile
import folium
from shapely.geometry import Point as ShapelyPoint
from streamlit_folium import st_folium

def get_last_modified(filepath):
    try:
        timestamp = os.path.getmtime(filepath)
        dt = datetime.datetime.fromtimestamp(timestamp)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        return f"❌ Gagal membaca waktu modifikasi: {e}"

def dms_to_dd(degree, minute, second, direction):
    dd = degree + minute / 60 + second / 3600
    if direction in ["LS", "BB"]:
        dd *= -1
    return dd

def load_shapefile_local(path):
    try:
        gdf = gpd.read_file(path)
        return gdf
    except Exception as e:
        st.warning(f"Gagal memuat shapefile lokal dari {path}: {e}")
        return None

@st.cache_data
def load_kkprl_json():
    try:
        with open("kkprl.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        features = []
        for feat in data["features"]:
            if "geometry" in feat and "rings" in feat["geometry"]:
                features.append({
                    "type": "Feature",
                    "properties": feat["attributes"],
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": feat["geometry"]["rings"]
                    }
                })

        if not features:
            st.warning("❌ Tidak ada fitur valid yang dapat diproses.")
            return None

        gdf = gpd.GeoDataFrame.from_features(features)
        gdf.set_crs(epsg=4326, inplace=True)
        return gdf

    except Exception as e:
        st.warning(f"Gagal membaca file KKPRL JSON: {e}")
        return None


# Konfigurasi halaman
st.set_page_config(
    page_title="Verdok - Konversi Koordinat",
    page_icon="📝",
    layout="centered"
)

st.markdown(
    "<h1 style='text-align: center;'>Konversi Koordinat dan Analisis Spasial - Verdok (Ver 1.2)</h1>",
    unsafe_allow_html=True
)

update_time = get_last_modified("kkprl.json")
st.markdown(f"🕒 **Data KKPRL terakhir diperbarui:** {update_time}")

format_pilihan = st.radio("Pilih format data koordinat:", ("OSS-UTM", "General-Decimal Degree"))
uploaded_file = st.file_uploader("Unggah file Excel", type=["xlsx"])
shp_type = st.radio("Pilih tipe shapefile yang ingin dibuat:", ("Poligon (Polygon)", "Titik (Point)"))
nama_file = st.text_input("➡️Masukkan nama file shapefile (tanpa ekstensi)⬅️", value="nama_shapefile")

col1, col2, col3, col4 = st.columns(4)
with col1:
    cek_sedimentasi = st.checkbox("Sedimentasi 🏖️")
with col2:
    cek_pertambangan = st.checkbox("Pertambangan ⛏️")
with col3:
    cek_migas = st.checkbox("MIGAS🛢️")
with col4:
    cek_rumpon = st.checkbox("Rumpon🪝")

konservasi_gdf = load_shapefile_local("data/Kawasan Konservasi 2022 update.shp")
mil12_gdf = load_shapefile_local("data/12_Mil.shp")
sedimen_gdf = load_shapefile_local("data/LokasiPrioritasPengumuman_15maret2024_AR.shp") if cek_sedimentasi else None
kkprl_gdf = load_kkprl_json()
tambang_gdf = load_shapefile_local("data/IUP.shp") if cek_pertambangan else None
migas_gdf = load_shapefile_local("data/MIGAS.shp") if cek_migas else None
rumpon_gdf = load_shapefile_local("data/Rumpon_Full.shp") if cek_rumpon else None

if uploaded_file and nama_file:
    df = pd.read_excel(uploaded_file)
    if df.shape[0] > 300:
        st.warning("Koordinat Lebih dari 300.")
        df = df.head(300)

    if format_pilihan == "OSS-UTM":
        df['longitude'] = df.apply(lambda row: dms_to_dd(row['bujur_derajat'], row['bujur_menit'], row['bujur_detik'], row['BT_BB']), axis=1)
        df['latitude'] = df.apply(lambda row: dms_to_dd(row['lintang_derajat'], row['lintang_menit'], row['lintang_detik'], row['LU_LS']), axis=1)
    else:
        df.rename(columns={'x': 'longitude', 'y': 'latitude'}, inplace=True)

    if shp_type == "Titik (Point)":
        geometry = [Point(xy) for xy in zip(df['longitude'], df['latitude'])]
        gdf = gpd.GeoDataFrame(df[['id']], geometry=geometry, crs="EPSG:4326")
    else:
        coords = list(zip(df['longitude'], df['latitude']))
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        geometry = [Polygon(coords)]
        gdf = gpd.GeoDataFrame(pd.DataFrame({"id": ["polygon_1"]}), geometry=geometry, crs="EPSG:4326")

    # tampilkan hasil konversi tabel
    st.subheader("Hasil Konversi")
    st.dataframe(df[['id', 'longitude', 'latitude']])

    # 🔹 Visualisasi peta
    if not gdf.empty:
        centroid = gdf.unary_union.centroid
        if not isinstance(centroid, ShapelyPoint):
            lon = gdf.geometry.centroid.x.mean()
            lat = gdf.geometry.centroid.y.mean()
        else:
            lon, lat = centroid.x, centroid.y

        if pd.isna(lon) or pd.isna(lat):
            lon, lat = 118, -2.5  # fallback ke Indonesia

        m = folium.Map(location=[lat, lon], zoom_start=6, tiles="OpenStreetMap")

        valid_cols = [c for c in gdf.columns if c != "geometry"]
        if valid_cols:
            folium.GeoJson(
                gdf,
                name="Hasil Analisis",
                tooltip=folium.GeoJsonTooltip(fields=valid_cols, aliases=valid_cols)
            ).add_to(m)
        else:
            folium.GeoJson(gdf, name="Hasil Analisis").add_to(m)

        st.subheader("Visualisasi Peta")
        st_folium(m, width=700, height=500)

    # 🔹 Export shapefile zip
    with tempfile.TemporaryDirectory() as tmpdirname:
        shp_path = os.path.join(tmpdirname, f"{nama_file}.shp")
        gdf.to_file(shp_path)
        zip_path = os.path.join(tmpdirname, f"{nama_file}.zip")
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for ext in ['shp', 'shx', 'dbf', 'cpg', 'prj']:
                fpath = shp_path.replace('.shp', f'.{ext}')
                if os.path.exists(fpath):
                    zipf.write(fpath, arcname=os.path.basename(fpath))
        with open(zip_path, "rb") as f:
            st.download_button("📥 Unduh Shapefile (ZIP)", f, file_name=f"{nama_file}.zip")
