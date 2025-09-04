import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
from pyproj import Transformer
import time

# --- GOOGLE API KEY ---
GOOGLE_API_KEY = st.secrets["google_api_key"]

# --- CACHED API FUNCTIONS ---
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
        st.warning(f"Postcode API error: {str(e)}")
    return "N/A", "N/A", "N/A"

@st.cache_data
def get_street_name(lat: float, lon: float) -> str:
    """Get street name using Google Maps Reverse Geocoding"""
    try:
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {
            "latlng": f"{lat},{lon}",
            "key": GOOGLE_API_KEY,
            "result_type": "street_address|route|premise"
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        # Check if request was successful
        if response.status_code != 200:
            st.warning(f"Google API returned status code: {response.status_code}")
            return "Unknown"
            
        data = response.json()
        
        # Debug: Show API response status
        st.write(f"Google API Status: {data.get('status')}")
        
        if data.get("status") == "OK":
            results = data.get("results", [])
            if results:
                # Try to get street name from address components
                for result in results:
                    address_components = result.get("address_components", [])
                    street_name = None
                    street_number = None
                    
                    for component in address_components:
                        types = component.get("types", [])
                        if "route" in types:
                            street_name = component["long_name"]
                        elif "street_number" in types:
                            street_number = component["long_name"]
                    
                    # If we found a street name, return it (with number if available)
                    if street_name:
                        if street_number:
                            return f"{street_number} {street_name}"
                        return street_name
                
                # Fallback: try to extract street from formatted address
                formatted_address = results[0].get("formatted_address", "")
                if formatted_address and formatted_address != "Unknown":
                    # Take the first part before the first comma
                    street_part = formatted_address.split(',')[0].strip()
                    if street_part:
                        return street_part
                
                return formatted_address[:50] + "..." if len(formatted_address) > 50 else formatted_address
        
        elif data.get("status") == "ZERO_RESULTS":
            return "No address found"
        elif data.get("status") == "OVER_QUERY_LIMIT":
            st.error("Google API quota exceeded")
            return "Quota exceeded"
        elif data.get("status") == "REQUEST_DENIED":
            st.error("Google API request denied - check your API key and billing")
            return "API denied"
        else:
            st.warning(f"Google API error: {data.get('status')} - {data.get('error_message', '')}")
            return f"API Error: {data.get('status')}"
            
    except requests.exceptions.Timeout:
        st.warning("Google API request timed out")
        return "Timeout"
    except Exception as e:
        st.warning(f"Street name lookup error: {str(e)}")
        return f"Error: {str(e)}"
    
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
    popup = f"{site['street']}<br>{site['postcode']}<br>Power: {site['required_kva']} kVA"
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

# API Key Check
if not GOOGLE_API_KEY or GOOGLE_API_KEY == "your_api_key_here":
    st.error("⚠️ Google API key not configured. Please set it in Streamlit secrets.")
    st.info("Go to Streamlit Cloud Settings → Secrets and add: google_api_key = 'YOUR_API_KEY'")

# Clear old session state
if "batch_results" in st.session_state:
    if st.session_state["batch_results"] and not all(isinstance(item, dict) for item in st.session_state["batch_results"]):
        del st.session_state["batch_results"]

# Sidebar
with st.sidebar:
    st.header("⚙️ Settings")
    fast_kw = st.number_input("Fast Charger Power (kW)", value=22)
    rapid_kw = st.number_input("Rapid Charger Power (kW)", value=60)
    ultra_kw = st.number_input("Ultra Charger Power (kW)", value=150)
    
    # Debug section
    with st.expander("🔧 Debug Info"):
        if st.button("Test Google API"):
            test_lat, test_lon = 51.5074, -0.1278  # London
            st.write(f"Testing with coordinates: {test_lat}, {test_lon}")
            test_result = get_street_name(test_lat, test_lon)
            st.write(f"Result: {test_result}")

# Main tabs
tab1, tab2 = st.tabs(["📍 Single Site", "📁 Batch Processing"])

# --- SINGLE SITE TAB ---
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
            with st.spinner("Processing site data..."):
                site = process_site(lat, lon, fast, rapid, ultra, fast_kw, rapid_kw, ultra_kw)
                st.session_state["single_site"] = site
        except ValueError:
            st.error("❌ Please enter valid latitude and longitude coordinates")
    
    if "single_site" in st.session_state:
        site = st.session_state["single_site"]
        st.success("✅ Site processed successfully!")
        
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**Location:** {site['latitude']:.6f}, {site['longitude']:.6f}")
            st.write(f"**Grid Ref:** {site['easting']:,}, {site['northing']:,}" if site['easting'] else "**Grid Ref:** N/A")
            st.write(f"**Street:** {site['street']}")
            st.write(f"**Postcode:** {site['postcode']}")
            st.write(f"**Ward:** {site['ward']}")
        
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
        st.download_button("📥 Download CSV", df.to_csv(index=False), "ev_site.csv", "text/csv")
        
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
    st.download_button("📥 Download Template", template.to_csv(index=False), "template.csv", "text/csv")
    
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
                status = st.empty()
                results = []
                errors = []
                
                # Add delay selector for batch processing
                st.info("💡 Processing with 1-second delays between requests to avoid API limits")
                
                for i, row in df_in.iterrows():
                    status.text(f"Processing site {i+1} of {len(df_in)} - {row.get('latitude', 'N/A')}, {row.get('longitude', 'N/A')}")
                    progress.progress((i + 1) / len(df_in))
                    
                    try:
                        site = process_site(
                            float(row["latitude"]), float(row["longitude"]),
                            int(row.get("fast", 0)), int(row.get("rapid", 0)), int(row.get("ultra", 0)),
                            fast_kw, rapid_kw, ultra_kw, show_debug=False
                        )
                        results.append(site)
                        
                        # Show progress for street name lookup
                        if site['street'] in ['Quota exceeded', 'API denied', 'Timeout']:
                            errors.append(f"Site {i+1}: {site['street']}")
                            
                    except Exception as e:
                        error_msg = str(e)
                        errors.append(f"Site {i+1}: {error_msg}")
                        st.warning(f"Error processing site {i+1}: {error_msg}")
                        # Add placeholder data for failed sites
                        results.append({
                            "latitude": row["latitude"], "longitude": row["longitude"], 
                            "easting": None, "northing": None,
                            "postcode": "Error", "ward": "Error", "district": "Error", 
                            "street": f"Error: {error_msg[:30]}", "fast_chargers": row.get("fast", 0), 
                            "rapid_chargers": row.get("rapid", 0), "ultra_chargers": row.get("ultra", 0),
                            "required_kva": 0
                        })
                    
                    # Longer delay for batch processing to avoid rate limits
                    time.sleep(1.0)
                
                status.text("Processing complete!")
                
                # Show error summary
                if errors:
                    st.warning(f"⚠️ {len(errors)} sites had issues:")
                    for error in errors[:5]:  # Show first 5 errors
                        st.text(f"• {error}")
                    if len(errors) > 5:
                        st.text(f"... and {len(errors) - 5} more errors")
                
                st.session_state["batch_results"] = results
            
            # Display batch results
            if "batch_results" in st.session_state:
                results = st.session_state["batch_results"]
                df_out = pd.DataFrame(results)
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Sites", len(results))
                with col2:
                    total_chargers = sum(s['fast_chargers'] + s['rapid_chargers'] + s['ultra_chargers'] for s in results if isinstance(s.get('fast_chargers'), int))
                    st.metric("Total Chargers", total_chargers)
                with col3:
                    total_power = sum(s['required_kva'] for s in results if isinstance(s.get('required_kva'), (int, float)))
                    st.metric("Total Power", f"{total_power:,.0f} kVA")
                
                st.subheader("📋 Results")
                st.dataframe(df_out)
                
                st.subheader("🗺️ All Sites Map")
                batch_map = create_batch_map(results)
                if batch_map:
                    st_folium(batch_map, width=700, height=500)
                
                st.download_button("📥 Download Results", df_out.to_csv(index=False), "batch_results.csv", "text/csv")
                
                if st.button("🔄 Clear Batch Results"):
                    del st.session_state["batch_results"]
                    st.rerun()
