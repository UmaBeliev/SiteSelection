import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
from pyproj import Transformer
import time
import random

# --- GOOGLE API KEY ---
GOOGLE_API_KEY = st.secrets["google_api_key"]

# --- CACHE: Postcode info ---
@st.cache_data
def get_postcode_info(lat: float, lon: float):
    """Get UK postcode information"""
    try:
        response = requests.get(f"https://api.postcodes.io/postcodes?lon={lon}&lat={lat}", timeout=10)
        data = response.json()
        if data.get("status") == 200 and data["result"]:
            result = data["result"][0]
            return result.get("postcode", "N/A"), result.get("admin_ward", "N/A"), result.get("admin_district", "N/A")
    except Exception as e:
        return "Error", "Error", str(e)
    return "N/A", "N/A", "N/A"

# --- CACHE: Street name lookup ---
@st.cache_data
def get_street_name(lat: float, lon: float, debug=False) -> str:
    """Get street name using Google Maps Reverse Geocoding"""
    try:
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {
            "latlng": f"{lat},{lon}",
            "key": GOOGLE_API_KEY,
            "result_type": "street_address|route|premise"
        }
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            return f"Error: HTTP {response.status_code}"
        data = response.json()

        if debug:
            st.info(f"Google API Status: {data.get('status')}")

        status = data.get("status")
        if status == "OK":
            results = data.get("results", [])
            if results:
                for result in results:
                    street_name, street_number = None, None
                    for comp in result.get("address_components", []):
                        types = comp.get("types", [])
                        if "route" in types:
                            street_name = comp["long_name"]
                        elif "street_number" in types:
                            street_number = comp["long_name"]
                    if street_name:
                        return f"{street_number} {street_name}" if street_number else street_name
                return results[0].get("formatted_address", "Unknown")
        elif status == "ZERO_RESULTS":
            return "No address found"
        elif status == "OVER_QUERY_LIMIT":
            return "Quota exceeded"
        elif status == "REQUEST_DENIED":
            return "API denied"
        return f"API Error: {status}"
    except requests.exceptions.Timeout:
        return "Timeout"
    except Exception as e:
        return f"Error: {str(e)}"

# --- COORDINATE CONVERTER ---
@st.cache_resource
def get_transformer():
    return Transformer.from_crs("epsg:4326", "epsg:27700")

def convert_to_british_grid(lat: float, lon: float):
    try:
        transformer = get_transformer()
        easting, northing = transformer.transform(lat, lon)
        return round(easting), round(northing)
    except:
        return None, None

# --- CALCULATOR ---
def calculate_kva(fast, rapid, ultra, fast_kw=22, rapid_kw=60, ultra_kw=150):
    total_kw = fast * fast_kw + rapid * rapid_kw + ultra * ultra_kw
    return round(total_kw / 0.9, 2)

def process_site(lat, lon, fast, rapid, ultra, fast_kw, rapid_kw, ultra_kw, debug=False):
    """Process a single site and return all data"""
    easting, northing = convert_to_british_grid(lat, lon)
    postcode, ward, district = get_postcode_info(lat, lon)
    street = get_street_name(lat, lon, debug)
    kva = calculate_kva(fast, rapid, ultra, fast_kw, rapid_kw, ultra_kw)
    return {
        "latitude": lat, "longitude": lon, "easting": easting, "northing": northing,
        "postcode": postcode, "ward": ward, "district": district, "street": street,
        "fast_chargers": fast, "rapid_chargers": rapid, "ultra_chargers": ultra,
        "required_kva": kva
    }

# --- MAP HELPERS ---
def add_google_traffic_layer(m):
    folium.TileLayer(
        tiles=f"https://mt1.google.com/vt/lyrs=h,traffic&x={{x}}&y={{y}}&z={{z}}&key={GOOGLE_API_KEY}",
        attr="Google Traffic", name="Traffic"
    ).add_to(m)

def add_osm_layer(m):
    folium.TileLayer(
        tiles="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        attr="OpenStreetMap", name="OSM"
    ).add_to(m)

def create_map(center, zoom=14, traffic=False, osm=False):
    m = folium.Map(
        location=center,
        zoom_start=zoom,
        tiles=f"https://mt1.google.com/vt/lyrs=m&x={{x}}&y={{y}}&z={{z}}&key={GOOGLE_API_KEY}",
        attr="Google Maps"
    )
    if traffic:
        add_google_traffic_layer(m)
    if osm:
        add_osm_layer(m)
    folium.LayerControl().add_to(m)
    return m

def create_single_map(site, traffic=False, osm=False):
    m = create_map([site["latitude"], site["longitude"]], zoom=15, traffic=traffic, osm=osm)
    popup = f"{site['street']}<br>{site['postcode']}<br>Power: {site['required_kva']} kVA"
    folium.Marker([site["latitude"], site["longitude"]], popup=popup, tooltip="EV Site").add_to(m)
    return m

def create_batch_map(sites, traffic=False, osm=False):
    if not sites: return None
    center_lat = sum(s["latitude"] for s in sites) / len(sites)
    center_lon = sum(s["longitude"] for s in sites) / len(sites)
    m = create_map([center_lat, center_lon], zoom=6, traffic=traffic, osm=osm)
    for i, site in enumerate(sites):
        popup = f"Site {i+1}: {site['street']}<br>Power: {site['required_kva']} kVA"
        folium.Marker([site["latitude"], site["longitude"]], popup=popup, tooltip=f"Site {i+1}").add_to(m)
    return m

# --- STREAMLIT APP ---
st.set_page_config(page_title="EV Charger Site Generator", page_icon="🔋", layout="wide")
st.title("🔋 EV Charger Site Generator")

if not GOOGLE_API_KEY or GOOGLE_API_KEY == "your_api_key_here":
    st.error("⚠️ Google API key not configured.")
    st.stop()

with st.sidebar:
    st.header("⚙️ Settings")
    fast_kw = st.number_input("Fast Charger Power (kW)", value=22)
    rapid_kw = st.number_input("Rapid Charger Power (kW)", value=60)
    ultra_kw = st.number_input("Ultra Charger Power (kW)", value=150)
    show_traffic = st.checkbox("Show Google Traffic Layer", value=False)
    show_osm = st.checkbox("Add OpenStreetMap Layer", value=False)
    debug_mode = st.checkbox("Enable Debug Mode", value=False)

# --- SINGLE SITE TAB ---
tab1, tab2 = st.tabs(["📍 Single Site", "📁 Batch Processing"])

with tab1:
    st.subheader("Analyze Single Site")
    with st.form("single_site_form"):
        col1, col2 = st.columns(2)
        with col1:
            lat = st.text_input("Latitude (e.g. 51.5074)")
            fast = st.number_input("Fast Chargers", min_value=0, value=0)
            ultra = st.number_input("Ultra Chargers", min_value=0, value=0)
        with col2:
            lon = st.text_input("Longitude (e.g. -0.1278)")
            rapid = st.number_input("Rapid Chargers", min_value=0, value=0)
        submitted = st.form_submit_button("🔍 Analyze Site")

    if submitted:
        try:
            lat, lon = float(lat), float(lon)
            site = process_site(lat, lon, fast, rapid, ultra, fast_kw, rapid_kw, ultra_kw, debug_mode)
            st.session_state["single_site"] = site
        except ValueError:
            st.error("❌ Invalid coordinates")

    if "single_site" in st.session_state:
        site = st.session_state["single_site"]
        st.success("✅ Site processed successfully!")
        col1, col2, col3 = st.columns(3)
        with col1: st.metric("Latitude", f"{site['latitude']:.6f}")
        with col2: st.metric("Longitude", f"{site['longitude']:.6f}")
        with col3: st.metric("Required kVA", site["required_kva"])
        st.write(f"**Street:** {site['street']}, **Postcode:** {site['postcode']}, **Ward:** {site['ward']}")
        st_folium(create_single_map(site, show_traffic, show_osm), width=700, height=400)
        st.download_button("📥 Download CSV", pd.DataFrame([site]).to_csv(index=False), "ev_site.csv")

# --- BATCH TAB ---
with tab2:
    st.subheader("Process Multiple Sites")
    template = pd.DataFrame({
        "latitude": [51.5074, 53.4808, 55.9533],
        "longitude": [-0.1278, -2.2426, -3.1883],
        "fast": [2, 3, 1], "rapid": [1, 2, 2], "ultra": [1, 0, 1]
    })
    st.download_button("📥 Download Template", template.to_csv(index=False), "template.csv")
    uploaded = st.file_uploader("Upload CSV", type="csv")

    if uploaded:
        df_in = pd.read_csv(uploaded)
        required = {"latitude", "longitude", "fast", "rapid", "ultra"}
        if not required.issubset(df_in.columns):
            st.error("❌ Missing columns")
        else:
            if st.button("🚀 Process All Sites"):
                results, errors = [], []
                delay = 0.2
                for i, row in df_in.iterrows():
                    try:
                        site = process_site(
                            float(row["latitude"]), float(row["longitude"]),
                            int(row.get("fast", 0)), int(row.get("rapid", 0)), int(row.get("ultra", 0)),
                            fast_kw, rapid_kw, ultra_kw
                        )
                        results.append(site)
                        if site["street"] in ["Quota exceeded", "API denied", "Timeout"]:
                            errors.append({"Site": i+1, "Error": site["street"]})
                            delay = min(delay*2, 5.0)  # adaptive backoff
                    except Exception as e:
                        errors.append({"Site": i+1, "Error": str(e)})
                        results.append({})
                        delay = min(delay*2, 5.0)
                    time.sleep(delay + random.uniform(0, 0.2))  # jitter

                st.session_state["batch_results"] = results
                if errors:
                    st.warning("⚠️ Some sites had issues")
                    st.dataframe(pd.DataFrame(errors))

    if "batch_results" in st.session_state:
        df_out = pd.DataFrame(st.session_state["batch_results"])
        st.metric("Total Sites", len(df_out))
        st.metric("Total Chargers", df_out[["fast_chargers","rapid_chargers","ultra_chargers"]].sum().sum())
        st.metric("Total Power (kVA)", f"{df_out['required_kva'].sum():,.0f}")
        st.dataframe(df_out)
        st_folium(create_batch_map(st.session_state["batch_results"], show_traffic, show_osm), width=700, height=500)
        st.download_button("📥 Download Results", df_out.to_csv(index=False), "batch_results.csv")
