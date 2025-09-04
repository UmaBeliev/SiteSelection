import streamlit as st
import requests
import pandas as pd
import folium
from streamlit_folium import st_folium
import time

# ==============================
#       API KEY
# ==============================
TOMTOM_API_KEY = st.secrets["tomtom_api_key"]  # Store your key securely in Streamlit secrets

# ==============================
#       APP LAYOUT
# ==============================
st.set_page_config(page_title="EV Charging Stations Finder", layout="wide")
st.title("⚡ EV Charging Stations Finder")

# User input for location
lat = st.number_input("Latitude", value=51.5074)
lon = st.number_input("Longitude", value=-0.1278)
radius = st.number_input("Radius (meters)", value=5000, step=500)

# Connector type filter
connector_type = st.selectbox("Connector Type (optional)", ["All", "Type2", "CCS", "CHAdeMO"])

# Search button
if st.button("Find EV Stations"):
    url = "https://api.tomtom.com/search/2/evChargingAvailability.json"
    params = {
        "key": TOMTOM_API_KEY,
        "lat": lat,
        "lon": lon,
        "radius": radius
    }

    if connector_type != "All":
        params["connectorType"] = connector_type

    # Retry logic in case of temporary failures
    max_retries = 3
    for attempt in range(max_retries):
        response = requests.get(url, params=params)
        if response.status_code == 200:
            break
        else:
            st.warning(f"Attempt {attempt + 1}: API unavailable, retrying...")
            time.sleep(2)

    if response.status_code != 200:
        st.error(f"API request failed: {response.status_code}")
    else:
        data = response.json()
        stations = data.get("results", [])

        if stations:
            # Prepare DataFrame
            df = pd.DataFrame([{
                "Name": s.get("poi", {}).get("name"),
                "Address": s.get("address", {}).get("freeformAddress"),
                "Lat": s.get("position", {}).get("lat"),
                "Lon": s.get("position", {}).get("lon"),
                "Available Chargers": ", ".join(s.get("evChargerInfo", {}).get("availableConnectorTypes", []))
            } for s in stations])

            st.subheader("EV Charging Stations Table")
            st.dataframe(df)

            # Map visualization
            m = folium.Map(location=[lat, lon], zoom_start=13)
            for _, row in df.iterrows():
                folium.Marker(
                    [row["Lat"], row["Lon"]],
                    popup=f"<b>{row['Name']}</b><br>{row['Address']}<br>{row['Available Chargers']}"
                ).add_to(m)

            st.subheader("Map of EV Charging Stations")
            st_folium(m, width=700, height=500)
        else:
            st.warning("No EV charging stations found in this area.")
