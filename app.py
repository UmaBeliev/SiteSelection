import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
from pyproj import Transformer
import time

# --- CACHED API FUNCTIONS ---
@st.cache_data
def get_postcode_info(lat: float, lon: float):
    """Get UK postcode information"""
    try:
        response = requests.get(f"https://api.postcodes.io/postcodes?lon={lon}&lat={lat}", timeout=5)
        data = response.json()
        if data.get("status") == 200 and data["result"]:
            result = data["result"][0]
            return result.get("postcode", "N/A"), result.get("admin_ward", "N/A"), result.get("admin_district", "N/A")
    except:
        pass
    return "N/A", "N/A", "N/A"

@st.cache_data
def get_street_name(lat: float, lon: float) -> str:
    """Get street name via reverse geocoding"""
    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"format": "json", "lat": lat, "lon": lon, "zoom": 18, "addressdetails": 1},
            headers={"User-Agent": "EV-Site-App"},
            timeout=5
        )
        data = response.json()
        address = data.get("address", {})
        
        # Try multiple address components
        for key in ["road", "pedestrian", "residential", "footway", "path", "neighbourhood", "suburb"]:
            if key in address:
                return address[key]
    except:
        pass
    return "Unknown"

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

def process_site(lat, lon, fast, rapid, ultra, fast_kw, rapid_kw, ultra_kw):
    """Process a single site and return all data"""
    easting, northing = convert_to_british_grid(lat, lon)
    postcode, ward, district = get_postcode_info(lat, lon)
    street = get_street_name(lat, lon)
    kva = calculate_kva(fast, rapid, ultra, fast_kw, rapid_kw, ultra_kw)
    
    return {
        "latitude": lat, "longitude": lon, "easting": easting, "northing": northing,
        "postcode": postcode, "ward": ward, "district": district, "street": street,
        "fast_chargers": fast, "rapid_chargers": rapid, "ultra_chargers": ultra,
        "required_kva": kva
    }

# --- MAP FUNCTIONS ---
def create_single_map(site):
    m = folium.Map(location=[site["latitude"], site["longitude"]], zoom_start=15)
    popup = f"{site['street']}, {site['postcode']}<br>Power: {site['required_kva']} kVA"
    folium.Marker([site["latitude"], site["longitude"]], popup=popup, tooltip="EV Site").add_to(m)
    return m

def create_batch_map(sites):
    if not sites:
        return None
    
    center_lat = sum(s["latitude"] for s in sites) / len(sites)
    center_lon = sum(s["longitude"] for s in sites) / len(sites)
    m = folium.Map(location=[center_lat, center_lon], zoom_start=6)
    
    for i, site in enumerate(sites):
        popup = f"Site {i+1}: {site['street']}<br>Power: {site['required_kva']} kVA"
        folium.Marker([site["latitude"], site["longitude"]], popup=popup, tooltip=f"Site {i+1}").add_to(m)
    
    return m

# --- STREAMLIT APP ---
st.set_page_config(page_title="EV Charger Site Generator", page_icon="🔋", layout="wide")
st.title("🔋 EV Charger Site Generator")

# Clear any old session state with different structure
if "batch_results" in st.session_state:
    if st.session_state["batch_results"] and not all(isinstance(item, dict) for item in st.session_state["batch_results"]):
        del st.session_state["batch_results"]

# Sidebar
with st.sidebar:
    st.header("⚙️ Settings")
    fast_kw = st.number_input("Fast Charger Power (kW)", value=22)
    rapid_kw = st.number_input("Rapid Charger Power (kW)", value=60)
    ultra_kw = st.number_input("Ultra Charger Power (kW)", value=150)

# Main tabs
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
            lat, lon = float(lat), float(lon)
            with st.spinner("Processing..."):
                site = process_site(lat, lon, fast, rapid, ultra, fast_kw, rapid_kw, ultra_kw)
                st.session_state["single_site"] = site
        except ValueError:
            st.error("❌ Enter valid coordinates")
    
    # Display results
    if "single_site" in st.session_state:
        site = st.session_state["single_site"]
        st.success("✅ Site processed successfully!")
        
        # Debug info if enabled
        if debug_mode:
            with st.expander("🔧 API Debug Info"):
                st.write("**Testing street name API directly:**")
                try:
                    test_response = requests.get(
                        "https://nominatim.openstreetmap.org/reverse",
                        params={"format": "json", "lat": site['latitude'], "lon": site['longitude'], "zoom": 18, "addressdetails": 1},
                        headers={"User-Agent": "EV-Charger-Site-Generator/1.0"},
                        timeout=10
                    )
                    st.write(f"Status Code: {test_response.status_code}")
                    if test_response.status_code == 200:
                        test_data = test_response.json()
                        st.json(test_data)
                    else:
                        st.write(f"Response: {test_response.text[:200]}")
                except Exception as e:
                    st.write(f"API Test Error: {str(e)}")
        
        # Site details
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**Location:** {site['latitude']:.6f}, {site['longitude']:.6f}")
            st.write(f"**Grid Ref:** {site['easting']:,}, {site['northing']:,}" if site['easting'] else "**Grid Ref:** N/A")
            st.write(f"**Street:** {site['street']}")
            st.write(f"**Postcode:** {site['postcode']}")
        
        with col2:
            st.write(f"**Fast:** {site['fast_chargers']}, **Rapid:** {site['rapid_chargers']}, **Ultra:** {site['ultra_chargers']}")
            st.write(f"**Total Chargers:** {site['fast_chargers'] + site['rapid_chargers'] + site['ultra_chargers']}")
            st.markdown(f"**Required kVA:** <span style='color: #1f77b4; font-weight: bold;'>{site['required_kva']}</span>", unsafe_allow_html=True)
        
        # Map
        st.subheader("🗺️ Site Location")
        site_map = create_single_map(site)
        st_folium(site_map, width=700, height=400)
        
        # Download
        df = pd.DataFrame([site])
        st.download_button("📥 Download CSV", df.to_csv(index=False), "ev_site.csv")
        
        if st.button("🔄 Clear Results"):
            del st.session_state["single_site"]
            st.rerun()

# --- BATCH PROCESSING TAB ---
with tab2:
    st.subheader("Process Multiple Sites")
    
    # Template
    template = pd.DataFrame({
        "latitude": [51.5074, 53.4808, 55.9533],
        "longitude": [-0.1278, -2.2426, -3.1883],
        "fast": [2, 3, 1], "rapid": [1, 2, 2], "ultra": [1, 0, 1]
    })
    st.download_button("📥 Download Template", template.to_csv(index=False), "template.csv")
    
    # File upload
    uploaded = st.file_uploader("Upload CSV with columns: latitude, longitude, fast, rapid, ultra", type="csv")
    
    if uploaded:
        df_in = pd.read_csv(uploaded)
        required = {"latitude", "longitude", "fast", "rapid", "ultra"}
        
        if not required.issubset(df_in.columns):
            missing = required - set(df_in.columns)
            st.error(f"❌ Missing columns: {', '.join(missing)}")
        else:
            st.success(f"✅ Loaded {len(df_in)} sites")
            st.dataframe(df_in.head())
            
            if st.button("🚀 Process All Sites"):
                progress = st.progress(0)
                results = []
                
                for i, row in df_in.iterrows():
                    progress.progress((i + 1) / len(df_in))
                    site = process_site(
                        float(row["latitude"]), float(row["longitude"]),
                        int(row.get("fast", 0)), int(row.get("rapid", 0)), int(row.get("ultra", 0)),
                        fast_kw, rapid_kw, ultra_kw
                    )
                    results.append(site)
                    time.sleep(0.2)  # Rate limiting
                
                st.session_state["batch_results"] = results
            
            # Display batch results
            if "batch_results" in st.session_state:
                results = st.session_state["batch_results"]
                df_out = pd.DataFrame(results)
                
                # Summary
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Sites", len(results))
                with col2:
                    total_chargers = sum(s['fast_chargers'] + s['rapid_chargers'] + s['ultra_chargers'] for s in results)
                    st.metric("Total Chargers", total_chargers)
                with col3:
                    total_power = sum(s['required_kva'] for s in results)
                    st.metric("Total Power", f"{total_power:,.0f} kVA")
                
                # Results table
                st.subheader("📋 Results")
                st.dataframe(df_out)
                
                # Batch map
                st.subheader("🗺️ All Sites Map")
                batch_map = create_batch_map(results)
                if batch_map:
                    st_folium(batch_map, width=700, height=500)
                
                # Download
                st.download_button("📥 Download Results", df_out.to_csv(index=False), "batch_results.csv")
                
                if st.button("🔄 Clear Batch Results"):
                    del st.session_state["batch_results"]
                    st.rerun()
