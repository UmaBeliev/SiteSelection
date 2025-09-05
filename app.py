import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import requests

# ==============================
#           API KEYS
# ==============================
GOOGLE_API_KEY = st.secrets["google_api_key"]  # Ensure you have Roads API enabled

# --- Power calculator ---
def calculate_kva(fast, rapid, ultra, fast_kw=22, rapid_kw=60, ultra_kw=150):
    total_kw = fast * fast_kw + rapid * rapid_kw + ultra * ultra_kw
    return round(total_kw / 0.9, 2)  # assume PF = 0.9

# --- Snap to nearest road using Google Roads API ---
def snap_to_road(lat, lon):
    url = f"https://roads.googleapis.com/v1/snapToRoads?path={lat},{lon}&key={GOOGLE_API_KEY}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if "snappedPoints" in data:
            snapped = data["snappedPoints"][0]["location"]
            return snapped["latitude"], snapped["longitude"]
    return lat, lon

# --- Get nearest road name using Google Roads API (optional) ---
def get_nearest_road_name(lat, lon):
    # Use Roads API "nearestRoads" endpoint
    url = f"https://roads.googleapis.com/v1/nearestRoads?points={lat},{lon}&key={GOOGLE_API_KEY}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if "snappedPoints" in data:
            return data["snappedPoints"][0]["originalIndex"]
    return "Unknown"

# --- Main App ---
st.set_page_config(page_title="EV Site App", page_icon="🔋", layout="wide")
st.title("🔋 EV Charger Site Calculator")

# --- Single Site ---
st.subheader("📍 Single Site Analysis")

with st.form("site_form"):
    lat = st.number_input("Latitude", format="%.6f")
    lon = st.number_input("Longitude", format="%.6f")
    fast = st.number_input("Fast Chargers", min_value=0, value=0)
    rapid = st.number_input("Rapid Chargers", min_value=0, value=0)
    ultra = st.number_input("Ultra Chargers", min_value=0, value=0)

    submit = st.form_submit_button("🔍 Analyze Site")

if submit:
    if lat == 0.0 and lon == 0.0:
        st.error("❌ Please enter valid coordinates")
    else:
        # Snap to road
        snapped_lat, snapped_lon = snap_to_road(lat, lon)

        # Calculate power
        kva = calculate_kva(fast, rapid, ultra)

        # Show details
        st.success("✅ Site processed successfully!")
        st.write(f"**Original Latitude:** {lat:.6f}")
        st.write(f"**Original Longitude:** {lon:.6f}")
        st.write(f"**Snapped Latitude:** {snapped_lat:.6f}")
        st.write(f"**Snapped Longitude:** {snapped_lon:.6f}")
        st.write(f"**Chargers:** Fast={fast}, Rapid={rapid}, Ultra={ultra}")
        st.write(f"**Required kVA:** {kva}")

        # Map
        st.subheader("🗺️ Site Map")
        m = folium.Map(location=[snapped_lat, snapped_lon], zoom_start=15)
        folium.Marker(
            [snapped_lat, snapped_lon],
            popup=f"Chargers: F={fast}, R={rapid}, U={ultra}\nPower={kva} kVA"
        ).add_to(m)
        st_folium(m, width=700, height=400)

        # Export
        site_data = {
            "original_latitude": lat,
            "original_longitude": lon,
            "snapped_latitude": snapped_lat,
            "snapped_longitude": snapped_lon,
            "fast": fast,
            "rapid": rapid,
            "ultra": ultra,
            "required_kva": kva
        }
        df = pd.DataFrame([site_data])
        st.download_button("📥 Download CSV", df.to_csv(index=False), "site.csv", "text/csv")
