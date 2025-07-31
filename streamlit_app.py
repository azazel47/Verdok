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

        # Konversi format ArcGIS (attributes + rings) menjadi GeoJSON (properties + coordinates)
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

import streamlit as st

# Konfigurasi halaman: judul dan ikon
st.set_page_config(
    page_title="Verdok - Konversi Koordinat",
    page_icon="📝", 
    layout="centered"
)

# Judul halaman di tengah
st.markdown(
    "<h1 style='text-align: center;'>Konversi Koordinat dan Analisis Spasial - Verdok (Ver 1.2)</h1>",
    unsafe_allow_html=True
)


update_time = get_last_modified("kkprl.json")
st.markdown(f"🕒 **Data KKPRL terakhir diperbarui:** `{update_time}`")

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
rumpon_gdf = load_shapefile_local("data/Rumpon_Full.shp") if cek_migas else None

if uploaded_file and nama_file:
    df = pd.read_excel(uploaded_file)
    if df.shape[0] > 200:
        st.warning("Koordinat Lebih dari 200.")
        df = df.head(50)

    if format_pilihan == "OSS-UTM":
        df['longitude'] = df.apply(lambda row: dms_to_dd(row['bujur_derajat'], row['bujur_menit'], row['bujur_detik'], row['BT_BB']), axis=1)
        df['latitude'] = df.apply(lambda row: dms_to_dd(row['lintang_derajat'], row['lintang_menit'], row['lintang_detik'], row['LU_LS']), axis=1)
    else:
        df.rename(columns={'x': 'longitude', 'y': 'latitude'}, inplace=True)

    if shp_type == "Titik (Point)":
        geometry = [Point(xy) for xy in zip(df['longitude'], df['latitude'])]
        gdf = gpd.GeoDataFrame(df[['id']], geometry=geometry, crs="EPSG:4326")

        if konservasi_gdf is not None:
            joined = gpd.sjoin(gdf, konservasi_gdf[['NAMA_KK', 'geometry']], how='left', predicate='within')
            points_in_konservasi = joined[~joined['NAMA_KK'].isna()]
            if not points_in_konservasi.empty:
                namobj_string = ", ".join(points_in_konservasi['NAMA_KK'].dropna().unique())
                st.warning(f"{len(points_in_konservasi)} titik berada di dalam Kawasan Konservasi {namobj_string} ⚠️⚠️")
            else:
                st.success("Tidak ada titik yang berada di kawasan konservasi ✅✅")

        if mil12_gdf is not None:
            joined_mil = gpd.sjoin(gdf, mil12_gdf[['WP', 'geometry']], how='left', predicate='within')
            points_in_mil = joined_mil[~joined_mil['WP'].isna()]
            if not points_in_mil.empty:
                wp_string = ", ".join(points_in_mil['WP'].dropna().unique())
                st.success(f"{len(points_in_mil)} Titik berada di dalam wilayah 12 Mil Laut ✅✅")
                st.write(f"Berada di Provinsi: {wp_string}")
            else:
                st.warning("Titik di luar wilayah 12 Mil Laut ⚠️⚠️")

        if kkprl_gdf is not None:
            joined_kkprl = gpd.sjoin(gdf, kkprl_gdf[["NO_KKPRL", "NAMA_SUBJ", "geometry"]], how='left', predicate='within')
            points_in_kkprl = joined_kkprl[~joined_kkprl['NO_KKPRL'].isna()]
            if not points_in_kkprl.empty:
                st.warning(f"{len(points_in_kkprl)} Titik overlap dengan KKPRL terbit ⚠️⚠️")
                st.write(points_in_kkprl[['id', 'NO_KKPRL', 'NAMA_SUBJ']])
            else:
                st.success("Titik tidak overlap dengan KKPRL terbit")

        if sedimen_gdf is not None:
            joined_sedimen = gpd.sjoin(gdf, sedimen_gdf[['geometry']], how='left', predicate='within')
            points_in_sedimen = joined_sedimen[~joined_sedimen.index_right.isna()]
            if not points_in_sedimen.empty:
                st.success(f"{len(points_in_sedimen)} Titik berada di Lokasi Prioritas Sedimentasi ✅✅")
            else:
                st.warning("Titik diluar Lokasi Prioritas Sedimentasi ⚠️⚠️")
                
        if tambang_gdf is not None:
            joined_tambang = gpd.sjoin(gdf, tambang_gdf[['nama_usaha','geometry']], how='left', predicate='within')
            points_in_tambang = joined_tambang[~joined_tambang['nama_usaha'].isna()]
            if not points_in_tambang.empty:
                iup_string = ", ".join(points_in_tambang['nama_usaha'].dropna().unique())
                st.success(f"{len(points_in_tambang)} Titik berada di dalam WIUP ✅✅")
                st.write(f"Berada di WIUP milik: {iup_string}")
            else:
                st.warning("Titik di luar area WIUP ⚠️⚠️")    
                
        if migas_gdf is not None:
            st.write(f"Jumlah fitur MIGAS: {len(migas_gdf)}")  # debug
            joined_migas = gpd.sjoin(gdf, migas_gdf[['oprblk','geometry']], how='left', predicate='within')
            points_in_migas = joined_migas[~joined_migas['oprblk'].isna()]
            if not points_in_migas.empty:
                oprblk_string = ", ".join(points_in_migas['oprblk'].dropna().unique())
                st.success(f"{len(points_in_migas)} Titik berada di dalam WK ✅✅")
                st.write(f"Berada di WK milik: {oprblk_string}")
            else:
                st.warning("Titik di luar area WK ⚠️⚠️")   
                
        if rumpon_gdf is not None:
            joined_rumpon = gpd.sjoin(gdf, rumpon_gdf[['ID_Rumpon','geometry']], how='left', predicate='within')
            points_in_rumpon = joined_rumpon[~joined_rumpon['oprblk'].isna()]
            if not points_in_rumpon.empty:
                rumpon_string = ", ".join(points_in_rumpon['ID_Rumpon'].dropna().unique())
                st.success(f"{len(points_in_rumpon)} Titik berada di dalam grid Rumpon ✅✅")
                st.write(f"Berada di grid rumpon kode: {rumpon_string}")
            else:
                st.warning("Titik di luar area grid Rumpon ⚠️⚠️")  
    else:
        coords = list(zip(df['longitude'], df['latitude']))
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        geometry = [Polygon(coords)]
        gdf = gpd.GeoDataFrame(pd.DataFrame({"id": ["polygon_1"]}), geometry=geometry, crs="EPSG:4326")

        if konservasi_gdf is not None:
            overlay_konservasi = gpd.overlay(gdf, konservasi_gdf[['NAMA_KK', 'geometry']], how='intersection')
            if not overlay_konservasi.empty:
                NAMA_KK_string = ", ".join(overlay_result['NAMA_KK'].dropna().unique())
                st.warning(f"Poligon berada di dalam Kawasan Konservasi {NAMA_KK_string} ⚠️⚠️")
            else:
                st.success("Poligon tidak berada di kawasan konservasi ✅✅")

        if mil12_gdf is not None:
            overlay_mil = gpd.overlay(gdf, mil12_gdf[['WP', 'geometry']], how='intersection')
            if not overlay_mil.empty:
                wp_string = ", ".join(overlay_mil['WP'].dropna().unique())
                st.success(f"Poligon berada di dalam wilayah 12 Mil Laut: {wp_string} ✅✅")
            else:
                st.warning("Poligon di luar wilayah 12 Mil Laut ⚠️⚠️")

        if kkprl_gdf is not None:
            overlay_kkprl = gpd.overlay(gdf, kkprl_gdf[['NO_KKPRL', 'NAMA_SUBJ', 'geometry']], how='intersection')
            if not overlay_kkprl.empty:
                st.warning(f"Poligon Overlap dengan KKPRL Terbit ⚠️⚠️")
                st.write(overlay_kkprl[['NO_KKPRL', 'NAMA_SUBJ']])
            else:
                st.success("Poligon tidak Overlap")

        if sedimen_gdf is not None:
            overlay_sedimen = gpd.overlay(gdf, sedimen_gdf[['geometry']], how='intersection')
            if not overlay_sedimen.empty:
                st.success("Poligon berada di Lokasi Prioritas Sedimentasi ✅✅")
            else:
                st.warning("Poligon diuar Lokasi Prioritas Sedimentasi ⚠️⚠️")
    
        if tambang_gdf is not None:
            overlay_iup = gpd.overlay(gdf, tambang_gdf[['nama_usaha', 'geometry']], how='intersection')
            if not overlay_iup.empty:
                iup_string = ", ".join(overlay_iup['nama_usaha'].dropna().unique())
                st.success(f"Poligon berada di dalam WIUP: {iup_string} ✅✅")
            else:
                st.warning("Poligon di luar WIUP ⚠️⚠️")
                
        if migas_gdf is not None:
            overlay_migas = gpd.overlay(gdf, migas_gdf[['oprblk', 'geometry']], how='intersection')
            if not overlay_migas.empty:
                oprblk_string = ", ".join(overlay_migas['oprblk'].dropna().unique())
                st.success(f"Poligon berada di dalam WK: {oprblk_string} ✅✅")
            else:
                st.warning("Poligon di luar WK ⚠️⚠️")
                
        if rumpon_gdf is not None:
            overlay_rumpon = gpd.overlay(gdf, rumpon_gdf[['ID_Rumpon', 'geometry']], how='intersection')
            if not overlay_rumpon.empty:
                rumpon_string = ", ".join(overlay_rumpon['ID_Rumpon'].dropna().unique())
                st.success(f"Poligon berada di area grid rumpon kode: {rumpon_string} ✅✅")
            else:
                st.warning("Poligon di luar grid rumpon ⚠️⚠️")
    
    st.subheader("Hasil Konversi")
    st.dataframe(df[['id', 'longitude', 'latitude']])

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
            st.download_button("Unduh Shapefile (ZIP)", f, file_name=f"{nama_file}.zip")
