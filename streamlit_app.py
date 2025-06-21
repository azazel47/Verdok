import streamlit as st
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, Polygon
import tempfile
import os
import zipfile
import requests
import gdown
from io import BytesIO
import urllib3
import json

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def dms_to_dd(degree, minute, second, direction):
    dd = degree + minute / 60 + second / 3600
    if direction in ["LS", "BB"]:
        dd *= -1
    return dd

@st.cache_data
def get_kawasan_konservasi_from_arcgis():
    url = "https://kspservices.big.go.id/satupeta/rest/services/PUBLIK/SUMBER_DAYA_ALAM_DAN_LINGKUNGAN/MapServer/35/query"
    params = {
        "where": "1=1",
        "outFields": "*",
        "f": "geojson"
    }
    try:
        response = requests.get(url, params=params, verify=False)
        if response.status_code == 200:
            gdf = gpd.read_file(BytesIO(response.content))
            return gdf
        else:
            st.warning(f"Gagal mengunduh data: status code {response.status_code}")
            return None
    except Exception as e:
        st.warning(f"Gagal mengambil data dari ArcGIS Server: {e}")
        return None

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


def download_shapefile_from_gdrive(gdrive_url):
    try:
        file_id = gdrive_url.split("/d/")[1].split("/")[0]
        download_url = f"https://drive.google.com/uc?id={file_id}"

        with tempfile.TemporaryDirectory() as tmpdirname:
            zip_path = os.path.join(tmpdirname, "12mil.zip")
            gdown.download(download_url, zip_path, quiet=False)

            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(tmpdirname)

            for file in os.listdir(tmpdirname):
                if file.endswith(".shp"):
                    shp_path = os.path.join(tmpdirname, file)
                    gdf = gpd.read_file(shp_path)
                    return gdf
        return None
    except Exception as e:
        st.warning(f"Gagal mengunduh dan membaca shapefile dari Google Drive: {e}")
        return None

def download_sedimentasi_shapefile():
    try:
        sedimentasi_url = "https://drive.google.com/file/d/1ZcruoWPzneMCn11Y7vmgCvIWFyO4Sgg6/view?usp=drive_link"
        file_id = sedimentasi_url.split("/d/")[1].split("/")[0]
        download_url = f"https://drive.google.com/uc?id={file_id}"

        with tempfile.TemporaryDirectory() as tmpdirname:
            zip_path = os.path.join(tmpdirname, "sedimen.zip")
            gdown.download(download_url, zip_path, quiet=False)

            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(tmpdirname)

            for file in os.listdir(tmpdirname):
                if file.endswith(".shp"):
                    shp_path = os.path.join(tmpdirname, file)
                    gdf = gpd.read_file(shp_path)
                    return gdf
        return None
    except Exception as e:
        st.warning(f"Gagal mengunduh dan membaca shapefile Sedimentasi: {e}")
        return None

st.title("Konversi Koordinat dan Analisis Spasial - Verdok")

format_pilihan = st.radio("Pilih format data koordinat:", ("OSS-UTM", "General-Decimal Degree"))

uploaded_file = st.file_uploader("Unggah file Excel", type=["xlsx"])
shp_type = st.radio("Pilih tipe shapefile yang ingin dibuat:", ("Poligon (Polygon)", "Titik (Point)"))
nama_file = st.text_input("➡️Masukkan nama file shapefile (tanpa ekstensi)⬅️", value="nama_shapefile")
cek_sedimentasi = st.checkbox("Sedimentasi 🏖️")

konservasi_gdf = get_kawasan_konservasi_from_arcgis()
mil12_gdf = download_shapefile_from_gdrive("https://drive.google.com/file/d/16MnH27AofcSSr45jTvmopOZx4CMPxMKs/view?usp=sharing")
sedimen_gdf = download_sedimentasi_shapefile() if cek_sedimentasi else None
kkprl_gdf = load_kkprl_json()

if uploaded_file and nama_file:
    df = pd.read_excel(uploaded_file)
    if df.shape[0] > 100:
        st.warning("Koordinat Lebih dari 100.")
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
            joined = gpd.sjoin(gdf, konservasi_gdf[['namobj', 'geometry']], how='left', predicate='within')
            points_in_konservasi = joined[~joined['namobj'].isna()]
            if not points_in_konservasi.empty:
                namobj_string = ", ".join(points_in_konservasi['namobj'].dropna().unique())
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

    else:
        coords = list(zip(df['longitude'], df['latitude']))
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        geometry = [Polygon(coords)]
        gdf = gpd.GeoDataFrame(pd.DataFrame({"id": ["polygon_1"]}), geometry=geometry, crs="EPSG:4326")

        if konservasi_gdf is not None:
            overlay_result = gpd.overlay(gdf, konservasi_gdf[['namobj', 'geometry']], how='intersection')
            if not overlay_result.empty:
                namobj_string = ", ".join(overlay_result['namobj'].dropna().unique())
                st.warning(f"Poligon berada di dalam Kawasan Konservasi {namobj_string} ⚠️⚠️")
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
