import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
from pyproj import Transformer
import time

# --- CONFIG ---
GOOGLE_API_KEY = "YOUR_GOOGLE_API_KEY"  # 🔑 Put your Google API key here

# --- CACHED API FUNCTIONS ---
@st.cache_data
def get_postcode_info(lat: float, lon: float):
    """Get UK postcode information"""
    try:
        response = requests.get(
            f"https://api.postcodes.io/postcodes?lon={lon}&lat={lat}",
            timeout=5
        )
        data = response.json()
        if data.get("status") == 200 and data["result"]:
            result = data["result"][0]
            return (
                result.get("postcode", "N/A"),
                result.get("admin_ward", "N/A"),
                result.get("admin_district", "N/A")
            )
    except:
        pass
    return "N/A", "N/A", "N/A"


@st.cache_data
def get_street_name(lat: float, lon: float) -> str:
    """Get street name via Nominatim, fallback to Google Maps if available"""
    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={
                "format": "json", "lat": lat, "lon": lon,
                "zoom": 18, "addressdetails": 1
            },
            headers={"User-Agent": "EV-Site-App"},
            timeout=5
        )
        data = response.json()
        address = data.get("address", {})
        for key in ["road", "pedestrian", "residential", "footway", "path", "neighbourhood", "suburb"]:
            if key in address:
                return address[key]
    except:
        pass

    # --- FALLBACK: Google Maps ---
    if GOOGLE_API_KEY and GOOGLE_API_KEY != "YOUR_GOOGLE_API_KEY":
        try:
            g_url = f"https://maps.googleapis.com/maps/api/geocode/json?latlng={lat},{lon}&key={GOOGLE_API_KEY}"
            g_res = requests.get(g_url, timeout=5).json()
            if g_res.get("status") == "OK":
                return g_res["results"][0]["formatted_address"]
        except:
            pass

    return "Unknown"


# --- COORDINATE CONVERTER ---
@st.cache_resource
def get_transformer():
    return Transformer.from_crs("epsg:4326", "epsg:27700")

def convert_to_british_grid(lat: float, lon: float):
    """Convert to British National Grid"""
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


def process_single_site(lat, lon, fast, rapid, ultra, fast_kw, rapid_kw, ultra_kw):
    """Process a single site and return all data"""
    easting, northing = convert_to_british_grid(lat, lon)
    postcode, ward, district = get_postcode_info(lat, lon)
    street = get_street_name(lat, lon)
    kva = calculate_kva(fast, rapid, ultra, fast_kw, rapid_kw, ultra_kw)

    return {
        "latitude": lat,
        "longitude": lon,
        "easting": easting,
        "northing": northing,
        "postcode": postcode,
        "ward": ward,
        "district": district,
        "street": street,
        "fast_chargers": fast,
        "rapid_chargers": rapid,
        "ultra_chargers": ultra,
        "required_kva": kva
    }


# --- MAP FUNCTIONS ---
def create_single_map(site_data):
    m = folium.Map(location=[site_data["latitude"], site_data["longitude"]], zoom_start=15)
    popup_text = f"{site_data['street']}, {site_data['postcode']}<br>Power: {site_data['required_kva']} kVA"
    folium.Marker(
        [site_data["latitude"], site_data["longitude"]],
        popup=popup_text,
        tooltip="EV Charging Site"
    ).add_to(m)
    return m


def create_batch_map(sites):
    if not sites:
        return None
    center_lat = sum(s["latitude"] for s in sites) / len(sites)
    center_lon = sum(s["longitude"] for s in sites) / len(sites)
    m = folium.Map(location=[center_lat, center_lon], zoom_start=6)

    for i, site in enumerate(sites):
        popup_html = f"""
        <div style="font-family: Arial; width: 200px;">
            <h4>🔋 Site {i+1}</h4>
            <p><b>Street:</b> {site['street']}</p>
            <p><b>Postcode:</b> {site['postcode']}</p>
            <p><b>Chargers:</b> F:{site['fast_chargers']} R:{site['rapid_chargers']} U:{site['ultra_chargers']}</p>
            <p><b>Power:</b> {site['required_kva']} kVA</p>
        </div>
        """
        folium.Marker(
            [site["latitude"], site["longitude"]],
            popup=folium.Popup(popup_html, max_width=250),
            tooltip=f"Site {i+1}",
            icon=folium.Icon(color="blue")
        ).add_to(m)
    return m


# --- STREAMLIT APP ---
st.set_page_config(page_title="EV Charger Site Generator", page_icon="🔋", layout="wide")
st.title("🔋 EV Charger Site Generator")

with st.sidebar:
    st.header("⚙️ Charger Power Settings")
    fast_kw = st.number_input("Fast Charger Power (kW)", value=22)
    rapid_kw = st.number_input("Rapid Charger Power (kW)", value=60)
    ultra_kw = st.number_input("Ultra Charger Power (kW)", value=150)

tab1, tab2 = st.tabs(["📍 Single Site", "📁 Batch Processing"])

# --- SINGLE SITE ---
with tab1:
    st.subheader("Analyze Single Site")

    with st.form("single_site_form"):
        lat = st.text_input("Latitude (e.g. 51.5074)")
        lon = st.text_input("Longitude (e.g. -0.1278)")
        fast = st.number_input("Fast Chargers", min_value=0, value=0)
        rapid = st.number_input("Rapid Chargers", min_value=0, value=0)
        ultra = st.number_input("Ultra Chargers", min_value=0, value=0)
        submitted = st.form_submit_button("🔍 Analyze Site")

    if submitted:
        try:
            lat = float(lat)
            lon = float(lon)
            site_data = process_single_site(lat, lon, fast, rapid, ultra, fast_kw, rapid_kw, ultra_kw)
            st.session_state["single_site"] = site_data
        except ValueError:
            st.error("❌ Enter valid numbers for latitude and longitude")

    if "single_site" in st.session_state:
        site = st.session_state["single_site"]
        st.success("✅ Site processed successfully!")

        st.write(site)
        site_map = create_single_map(site)
        st_folium(site_map, width=700, height=400)
        df = pd.DataFrame([site])
        st.download_button("📥 Download Site Data (CSV)", df.to_csv(index=False), "ev_site.csv")


# --- BATCH SITES ---
with tab2:
    st.subheader("Process Multiple Sites")

    template = pd.DataFrame({
        "latitude": [51.5074, 53.4808, 55.9533],
        "longitude": [-0.1278, -2.2426, -3.1883],
        "fast": [2, 3, 1],
        "rapid": [1, 2, 2],
        "ultra": [1, 0, 1]
    })
    st.download_button("📥 Download Template", template.to_csv(index=False), "template.csv")

    uploaded = st.file_uploader("Upload CSV", type="csv")

    if uploaded:
        df_in = pd.read_csv(uploaded)
        required_cols = {"latitude", "longitude", "fast", "rapid", "ultra"}
        if not required_cols.issubset(df_in.columns):
            st.error(f"❌ Missing required columns: {', '.join(required_cols - set(df_in.columns))}")
        else:
            results = []
            for _, row in df_in.iterrows():
                site_data = process_single_site(
                    float(row["latitude"]), float(row["longitude"]),
                    int(row["fast"]), int(row["rapid"]), int(row["ultra"]),
                    fast_kw, rapid_kw, ultra_kw
                )
                results.append(site_data)
                time.sleep(1)  # avoid rate limit

            df_out = pd.DataFrame(results)
            st.dataframe(df_out)
            batch_map = create_batch_map(results)
            if batch_map:
                st_folium(batch_map, width=700, height=500)
            st.download_button("📥 Download Batch Results (CSV)", df_out.to_csv(index=False), "batch_results.csv")
