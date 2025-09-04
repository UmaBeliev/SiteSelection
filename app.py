import streamlit as st
import requests
import pandas as pd

# --- CONFIG ---
# Store your API key in Streamlit Secrets: st.secrets["GOOGLE_API_KEY"]
GOOGLE_API_KEY = st.secrets.get("AIzaSyAashMjJzxbRAj0wKBbxHi6WunL0kv48n4")

def get_street_name_google(lat, lon, api_key):
    """Get street name from Google Geocoding API"""
    try:
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {"latlng": f"{lat},{lon}", "key": api_key}
        response = requests.get(url, params=params, timeout=5)
        data = response.json()

        if data.get("status") == "OK" and data.get("results"):
            components = data["results"][0]["address_components"]
            for comp in components:
                if "route" in comp["types"]:
                    return comp["long_name"]
        return "Unknown"
    except Exception as e:
        return f"Error: {e}"

# --- STREAMLIT APP ---
st.set_page_config(page_title="Street Lookup with Google", layout="wide")
st.title("📍 Google Street Name Lookup")

st.markdown("""
Enter latitude and longitude to get the street name using **Google Geocoding API**.
""")

with st.form("lookup_form"):
    lat = st.text_input("Latitude (e.g., 51.5074)")
    lon = st.text_input("Longitude (e.g., -0.1278)")
    submitted = st.form_submit_button("🔍 Lookup Street")

if submitted:
    try:
        lat_f = float(lat)
        lon_f = float(lon)
        if not GOOGLE_API_KEY:
            st.error("❌ Google API key not found. Add it in Streamlit secrets.")
        else:
            with st.spinner("Fetching street name..."):
                street = get_street_name_google(lat_f, lon_f, GOOGLE_API_KEY)
            st.success("✅ Done!")
            st.write(f"**Street Name:** {street}")

            # Download as CSV
            df = pd.DataFrame([{"latitude": lat_f, "longitude": lon_f, "street": street}])
            st.download_button("📥 Download CSV", df.to_csv(index=False), "street_lookup.csv")

    except ValueError:
        st.error("❌ Enter valid numbers for latitude and longitude")
