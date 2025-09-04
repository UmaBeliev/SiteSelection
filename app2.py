import streamlit as st
import requests
import pandas as pd
import folium
from streamlit_folium import st_folium

# ==============================
#       API KEY
# ==============================
TOMTOM_API_KEY = st.secrets["tomtom_api_key"]  # store securely in Streamlit secrets

# ==============================
#       APP LAYOUT
# ==============================
st.title("EV Charging Stations Finder 🚗⚡")

# User input for location
lat = st.number_input("Latitude", value=51.5074)
lon = st.number_input("Longitude", value=-0.1278)
radius = st.number_input("Radius (meters)", value=5000, step=1000)

# Search button
if st.button("Find EV Stations"):
    url = f"https://api.tomtom.com/search/2/evChargingAvailability.json?key={TOMTOM_API_KEY}&lat={lat}&lon={lon}&radius={radius}"
    
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        stations = data.get("results", [])

        if stations:
            # Prepare DataFrame
            df = pd.DataFrame([{
                "Name": s.get("poi", {}).get("name"),
                "Address": s.get("address", {}).get("freeformAddress"),
                "Lat": s.get("position", {}).get("lat"),
                "Lon": s.get("position", {}).get("lon"),
                "Available Chargers": s.get("evChargerInfo", {}).get("availableConnectorTypes", [])
            } for s in stations])

            st.dataframe(df)

            # Create map
            m = folium.Map(location=[lat, lon], zoom_start=13)
            for _, row in df.iterrows():
                folium.Marker(
                    [row["Lat"], row["Lon"]],
                    popup=f"{row['Name']}<br>{row['Address']}<br>{row['Available Chargers']}"
                ).add_to(m)
            st_folium(m, width=700, height=500)

        else:
            st.warning("No EV charging stations found in this area.")
    else:
        st.error(f"API request failed: {response.status_code}")
