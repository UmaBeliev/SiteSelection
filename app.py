import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
from pyproj import Transformer
from dataclasses import dataclass
from typing import Tuple, List
import time
import json

# --- CACHED API FUNCTIONS ---
@st.cache_data
def get_postcode_info(lat: float, lon: float) -> Tuple[str, str, str]:
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
    """Get street name via reverse geocoding"""
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
        return data.get("address", {}).get("road", "Unknown")
    except:
        return "Unknown"

# --- COORDINATE CONVERTER ---
@st.cache_resource
def get_transformer():
    return Transformer.from_crs("epsg:4326", "epsg:27700")

def convert_to_british_grid(lat: float, lon: float) -> Tuple[int, int]:
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
    """Create map for single site"""
    m = folium.Map(location=[site_data["latitude"], site_data["longitude"]], zoom_start=15)
    
    popup_text = f"{site_data['street']}, {site_data['postcode']}\nPower: {site_data['required_kva']} kVA"
    folium.Marker(
        [site_data["latitude"], site_data["longitude"]],
        popup=popup_text,
        tooltip="EV Charging Site"
    ).add_to(m)
    
    return m

def create_batch_map(sites):
    """Create map for multiple sites"""
    if not sites:
        return None
    
    # Calculate center
    center_lat = sum(s["latitude"] for s in sites) / len(sites)
    center_lon = sum(s["longitude"] for s in sites) / len(sites)
    
    m = folium.Map(location=[center_lat, center_lon], zoom_start=8)
    
    for i, site in enumerate(sites):
        color = 'green' if site.get('postcode', 'N/A') != 'N/A' else 'red'
        
        popup_html = f"""
        <div style="font-family: Arial; width: 200px;">
            <h4>🔋 Site {i+1}</h4>
            <p><b>Location:</b> {site['street']}</p>
            <p><b>Postcode:</b> {site['postcode']}</p>
            <p><b>Chargers:</b> F:{site['fast_chargers']} R:{site['rapid_chargers']} U:{site['ultra_chargers']}</p>
            <p><b>Power:</b> {site['required_kva']} kVA</p>
        </div>
        """
        
        folium.Marker(
            location=[site["latitude"], site["longitude"]],
            popup=folium.Popup(popup_html, max_width=250),
            tooltip=f"Site {i+1}: {site['required_kva']} kVA",
            icon=folium.Icon(color=color)
        ).add_to(m)
    
    return m

# --- STREAMLIT APP ---
st.set_page_config(page_title="EV Charger Site Generator", page_icon="🔋", layout="wide")
st.title("🔋 EV Charger Site Generator")

# --- SIDEBAR CONFIG ---
with st.sidebar:
    st.header("⚙️ Charger Power Settings")
    fast_kw = st.number_input("Fast Charger Power (kW)", value=22)
    rapid_kw = st.number_input("Rapid Charger Power (kW)", value=60)
    ultra_kw = st.number_input("Ultra Charger Power (kW)", value=150)

# --- TABS ---
tab1, tab2 = st.tabs(["📍 Single Site", "📁 Batch Processing"])

# --- SINGLE SITE TAB ---
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
            
            with st.spinner("Processing site data..."):
                site_data = process_single_site(lat, lon, fast, rapid, ultra, fast_kw, rapid_kw, ultra_kw)
                st.session_state["single_site"] = site_data
                
        except ValueError:
            st.error("❌ Enter valid numbers for latitude and longitude")

    if "single_site" in st.session_state:
        site = st.session_state["single_site"]
        st.success("✅ Site processed successfully!")
        
        # Display site details
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📍 Location Details")
            st.write(f"**Coordinates:** {site['latitude']:.6f}, {site['longitude']:.6f}")
            if site['easting'] and site['northing']:
                st.write(f"**Grid Reference:** {site['easting']:,}, {site['northing']:,}")
            st.write(f"**Street:** {site['street']}")
            st.write(f"**Postcode:** {site['postcode']}")
            st.write(f"**Ward:** {site['ward']}")
            st.write(f"**District:** {site['district']}")
        
        with col2:
            st.subheader("⚡ Power Requirements")
            st.write(f"**Fast Chargers:** {site['fast_chargers']}")
            st.write(f"**Rapid Chargers:** {site['rapid_chargers']}")
            st.write(f"**Ultra Chargers:** {site['ultra_chargers']}")
            st.write(f"**Total Chargers:** {site['fast_chargers'] + site['rapid_chargers'] + site['ultra_chargers']}")
            st.markdown(f"**Required kVA:** <span style='color: #1f77b4; font-size: 1.2em; font-weight: bold;'>{site['required_kva']}</span>", 
                       unsafe_allow_html=True)

        # Map
        st.subheader("🗺️ Site Location")
        try:
            site_map = create_single_map(site)
            st_folium(site_map, width=700, height=400)
        except Exception as e:
            google_url = f"https://www.google.com/maps?q={site['latitude']},{site['longitude']}"
            st.markdown(f"🗺️ [View on Google Maps]({google_url})")

        # Download
        df = pd.DataFrame([site])
        st.download_button("📥 Download Site Data (CSV)", df.to_csv(index=False), "ev_site.csv")
        
        # Clear button
        if st.button("🔄 Clear Results"):
            del st.session_state["single_site"]
            st.rerun()

# --- BATCH TAB ---
with tab2:
    st.subheader("Process Multiple Sites")

    # Template
    template = pd.DataFrame({
        "latitude": [51.5074, 53.4808, 55.9533],
        "longitude": [-0.1278, -2.2426, -3.1883],
        "fast": [2, 3, 1],
        "rapid": [1, 2, 2],
        "ultra": [1, 0, 1]
    })
    st.download_button("📥 Download Template", template.to_csv(index=False), "template.csv")

    uploaded = st.file_uploader("Upload CSV with columns: latitude, longitude, fast, rapid, ultra", type="csv")

    if uploaded:
        df_in = pd.read_csv(uploaded)
        required_cols = {"latitude", "longitude", "fast", "rapid", "ultra"}
        
        if not required_cols.issubset(df_in.columns):
            missing = required_cols - set(df_in.columns)
            st.error(f"❌ Missing required columns: {', '.join(missing)}")
        else:
            st.success(f"✅ Loaded {len(df_in)} sites")
            st.dataframe(df_in.head())
            
            if st.button("🚀 Process All Sites"):
                progress_bar = st.progress(0)
                results = []
                
                for i, row in df_in.iterrows():
                    progress_bar.progress((i + 1) / len(df_in))
                    
                    site_data = process_single_site(
                        row["latitude"], row["longitude"],
                        int(row.get("fast", 0)), int(row.get("rapid", 0)), int(row.get("ultra", 0)),
                        fast_kw, rapid_kw, ultra_kw
                    )
                    results.append(site_data)
                    time.sleep(0.1)  # Rate limiting
                
                st.session_state["batch_results"] = results

            if "batch_results" in st.session_state:
                results = st.session_state["batch_results"]
                df_out = pd.DataFrame(results)
                
                # Summary stats
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total Sites", len(results))
                with col2:
                    total_chargers = sum(s['fast_chargers'] + s['rapid_chargers'] + s['ultra_chargers'] for s in results)
                    st.metric("Total Chargers", total_chargers)
                with col3:
                    total_power = sum(s['required_kva'] for s in results)
                    st.metric("Total Power", f"{total_power:,.0f} kVA")
                with col4:
                    successful = len([s for s in results if s['postcode'] != 'N/A'])
                    st.metric("Successful Lookups", f"{successful}/{len(results)}")

                st.subheader("📋 Detailed Results")
                st.dataframe(df_out)

                # Batch map
                st.subheader("🗺️ All Sites Map")
                try:
                    batch_map = create_batch_map(results)
                    if batch_map:
                        st_folium(batch_map, width=700, height=500)
                    else:
                        st.warning("No valid coordinates for mapping")
                except Exception as e:
                    st.error(f"Map error: {str(e)}")

                st.download_button("📥 Download Batch Results (CSV)", df_out.to_csv(index=False), "batch_results.csv")
                
                # Clear button
                if st.button("🔄 Clear Batch Results"):
                    del st.session_state["batch_results"]
                    st.rerun()
