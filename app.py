import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
from pyproj import Transformer
import time
import logging

# ==============================
# API KEYS
# ==============================
GOOGLE_API_KEY = st.secrets["google_api_key"]
TOMTOM_API_KEY = st.secrets.get("tomtom_api_key", "")

# ==============================
# UTILITY FUNCTIONS
# ==============================

@st.cache_data
def get_postcode_info(lat, lon):
    """Get postcode information using postcodes.io API"""
    try:
        r = requests.get(f"https://api.postcodes.io/postcodes?lon={lon}&lat={lat}", timeout=10)
        data = r.json()
        if data.get("status") == 200 and data["result"]:
            res = data["result"][0]
            return res.get("postcode","N/A"), res.get("admin_ward","N/A"), res.get("admin_district","N/A")
    except Exception as e:
        st.warning(f"Postcode API error: {e}")
    return "N/A","N/A","N/A"

@st.cache_data
def get_geocode_details(lat, lon):
    """Get detailed geocoding information from Google Maps"""
    try:
        r = requests.get("https://maps.googleapis.com/maps/api/geocode/json", 
                         params={"latlng": f"{lat},{lon}", "key": GOOGLE_API_KEY}, timeout=10)
        data = r.json()
        if data.get("status")=="OK" and data.get("results"):
            comps = data["results"][0]["address_components"]
            details = {}
            for c in comps:
                types = c.get("types",[])
                if "route" in types: details["street"]=c["long_name"]
                if "street_number" in types: details["street_number"]=c["long_name"]
                if "neighborhood" in types: details["neighborhood"]=c["long_name"]
                if "locality" in types: details["city"]=c["long_name"]
                if "administrative_area_level_2" in types: details["county"]=c["long_name"]
                if "administrative_area_level_1" in types: details["region"]=c["long_name"]
                if "postal_code" in types: details["postcode"]=c["long_name"]
                if "country" in types: details["country"]=c["long_name"]
            details["formatted_address"]=data["results"][0].get("formatted_address")
            return details
    except Exception as e:
        st.warning(f"Geocoding API error: {e}")
    return {}

@st.cache_data
def get_nearby_amenities(lat, lon, radius=500):
    """Get nearby amenities using Google Places API (Nearby Search)"""
    amenities = []
    
    # Define place types according to Google Places API documentation
    place_types = [
        "gas_station",      # Petrol stations
        "restaurant",       # Restaurants
        "cafe",            # Cafes
        "shopping_mall",   # Shopping centers
        "supermarket",     # Supermarkets
        "hospital",        # Hospitals
        "pharmacy",        # Pharmacies
        "bank",           # Banks
        "atm",            # ATMs
        "lodging"         # Hotels
    ]
    
    try:
        url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        
        for place_type in place_types:
            params = {
                "location": f"{lat},{lon}",
                "radius": radius,
                "type": place_type,
                "key": GOOGLE_API_KEY
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("status") == "OK":
                    results = data.get("results", [])
                    
                    for place in results[:3]:  # Limit to top 3 per category
                        name = place.get("name", "Unknown")
                        rating = place.get("rating", "N/A")
                        
                        # Format place type for display
                        display_type = place_type.replace("_", " ").title()
                        
                        amenity_info = f"{name} ({display_type})"
                        if rating != "N/A":
                            amenity_info += f" ⭐{rating}"
                            
                        amenities.append(amenity_info)
                
                elif data.get("status") == "ZERO_RESULTS":
                    continue  # No results for this type
                else:
                    st.warning(f"Places API error for {place_type}: {data.get('status')}")
            
            else:
                st.warning(f"HTTP error {response.status_code} for {place_type}")
            
            # Small delay to avoid rate limiting
            time.sleep(0.1)
        
        # EV Charging stations - separate search with keyword
        ev_params = {
            "location": f"{lat},{lon}",
            "radius": radius,
            "keyword": "electric vehicle charging station",
            "key": GOOGLE_API_KEY
        }
        
        ev_response = requests.get(url, params=ev_params, timeout=10)
        if ev_response.status_code == 200:
            ev_data = ev_response.json()
            if ev_data.get("status") == "OK":
                ev_results = ev_data.get("results", [])
                for ev_place in ev_results[:3]:
                    name = ev_place.get("name", "Unknown")
                    rating = ev_place.get("rating", "N/A")
                    amenity_info = f"{name} (EV Charging)"
                    if rating != "N/A":
                        amenity_info += f" ⭐{rating}"
                    amenities.append(amenity_info)
        
        return "; ".join(amenities[:15]) if amenities else "None nearby"
        
    except Exception as e:
        st.warning(f"Places API error: {e}")
        return f"Error retrieving amenities: {str(e)}"

@st.cache_data
def get_road_info_google_roads(lat, lon):
    """
    Get road information using Google Roads API according to official documentation
    https://developers.google.com/maps/documentation/roads/overview
    """
    road_info = {
        "road_name": "Unknown",
        "road_type": "Unknown", 
        "speed_limit": None,
        "place_id": None
    }
    
    try:
        # Step 1: Snap to Roads API
        snap_url = "https://roads.googleapis.com/v1/snapToRoads"
        snap_params = {
            "path": f"{lat},{lon}",
            "interpolate": "true",
            "key": GOOGLE_API_KEY
        }
        
        snap_response = requests.get(snap_url, params=snap_params, timeout=10)
        
        if snap_response.status_code == 200:
            snap_data = snap_response.json()
            
            if "snappedPoints" in snap_data and snap_data["snappedPoints"]:
                snapped_point = snap_data["snappedPoints"][0]
                place_id = snapped_point.get("placeId")
                
                if place_id:
                    road_info["place_id"] = place_id
                    
                    # Step 2: Get Speed Limits
                    speed_url = "https://roads.googleapis.com/v1/speedLimits"
                    speed_params = {
                        "placeId": place_id,
                        "key": GOOGLE_API_KEY
                    }
                    
                    speed_response = requests.get(speed_url, params=speed_params, timeout=10)
                    
                    if speed_response.status_code == 200:
                        speed_data = speed_response.json()
                        
                        if "speedLimits" in speed_data and speed_data["speedLimits"]:
                            speed_limit_data = speed_data["speedLimits"][0]
                            road_info["speed_limit"] = speed_limit_data.get("speedLimit")
                    
                    # Step 3: Get place details for road name and classification
                    place_url = "https://maps.googleapis.com/maps/api/place/details/json"
                    place_params = {
                        "place_id": place_id,
                        "fields": "name,types,geometry,formatted_address",
                        "key": GOOGLE_API_KEY
                    }
                    
                    place_response = requests.get(place_url, params=place_params, timeout=10)
                    
                    if place_response.status_code == 200:
                        place_data = place_response.json()
                        
                        if place_data.get("status") == "OK":
                            result = place_data.get("result", {})
                            road_info["road_name"] = result.get("name", "Unknown Road")
                            
                            # Classify road type based on Google Places types
                            place_types = result.get("types", [])
                            road_info["road_type"] = classify_road_type(place_types, road_info["road_name"])
        
        else:
            st.warning(f"Roads API HTTP error: {snap_response.status_code}")
            
    except Exception as e:
        st.warning(f"Google Roads API error: {e}")
    
    # Fallback: Use reverse geocoding if Roads API fails
    if road_info["road_name"] == "Unknown":
        try:
            geocode_url = "https://maps.googleapis.com/maps/api/geocode/json"
            geocode_params = {
                "latlng": f"{lat},{lon}",
                "key": GOOGLE_API_KEY
            }
            
            geocode_response = requests.get(geocode_url, params=geocode_params, timeout=10)
            
            if geocode_response.status_code == 200:
                geocode_data = geocode_response.json()
                
                if geocode_data.get("status") == "OK" and geocode_data.get("results"):
                    # Extract road name from address components
                    components = geocode_data["results"][0].get("address_components", [])
                    
                    for component in components:
                        types = component.get("types", [])
                        if "route" in types:
                            road_info["road_name"] = component.get("long_name", "Unknown Road")
                            road_info["road_type"] = classify_road_type_from_name(road_info["road_name"])
                            break
            
        except Exception as e:
            st.warning(f"Geocoding fallback error: {e}")
    
    return road_info

def classify_road_type(place_types, road_name=""):
    """Classify road type based on Google Places API types and road name"""
    
    # Primary classification from Google Places types
    if "highway" in place_types:
        return "Highway"
    elif "primary" in place_types:
        return "Primary Road"
    elif "secondary" in place_types:
        return "Secondary Road"
    elif "tertiary" in place_types:
        return "Tertiary Road"
    elif "residential" in place_types:
        return "Residential Street"
    elif "service" in place_types:
        return "Service Road"
    elif "trunk" in place_types:
        return "Trunk Road"
    elif "route" in place_types:
        return "Route"
    else:
        # Fallback to name-based classification
        return classify_road_type_from_name(road_name)

def classify_road_type_from_name(road_name):
    """Classify road type based on road name patterns (UK-focused)"""
    if not road_name or road_name == "Unknown Road":
        return "Local Road"
    
    road_name_lower = road_name.lower()
    
    # UK road classifications
    if any(keyword in road_name_lower for keyword in ["motorway", "m1", "m25", "m2", "m3", "m4", "m5", "m6"]):
        return "Motorway"
    elif road_name_lower.startswith("a") and len(road_name) > 1 and road_name[1:].split()[0].isdigit():
        return "A Road"
    elif road_name_lower.startswith("b") and len(road_name) > 1 and road_name[1:].split()[0].isdigit():
        return "B Road"
    elif any(keyword in road_name_lower for keyword in ["dual carriageway", "bypass"]):
        return "Dual Carriageway"
    elif any(keyword in road_name_lower for keyword in ["street", "road", "avenue", "lane", "drive", "close", "way"]):
        return "Local Road"
    elif any(keyword in road_name_lower for keyword in ["roundabout", "circus"]):
        return "Roundabout"
    else:
        return "Local Road"

@st.cache_resource
def get_transformer():
    """Get coordinate transformer for British National Grid"""
    return Transformer.from_crs("epsg:4326","epsg:27700")

def convert_to_british_grid(lat, lon):
    """Convert WGS84 coordinates to British National Grid"""
    transformer = get_transformer()
    try:
        e, n = transformer.transform(lat, lon)
        return round(e), round(n)
    except Exception as e:
        st.warning(f"Coordinate transformation error: {e}")
        return None, None

def calculate_kva(fast, rapid, ultra, fast_kw=22, rapid_kw=60, ultra_kw=150):
    """Calculate required kVA capacity"""
    total_kw = fast * fast_kw + rapid * rapid_kw + ultra * ultra_kw
    # Assuming power factor of 0.9 and 10% overhead
    return round(total_kw / 0.9 * 1.1, 2)

def get_tomtom_traffic(lat, lon):
    """Get traffic information from TomTom API"""
    if not TOMTOM_API_KEY:
        return {"speed": None, "freeFlow": None, "congestion": "N/A"}
        
    try:
        url = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"
        params = {"point": f"{lat},{lon}", "key": TOMTOM_API_KEY}
        r = requests.get(url, params=params, timeout=10)
        
        if r.status_code == 200:
            flow = r.json().get("flowSegmentData", {})
            speed, freeflow = flow.get("currentSpeed"), flow.get("freeFlowSpeed")
            if speed and freeflow and freeflow > 0:
                ratio = speed / freeflow
                if ratio > 0.85:
                    level = "Low"
                elif ratio > 0.6:
                    level = "Medium"
                else:
                    level = "High"
                return {"speed": speed, "freeFlow": freeflow, "congestion": level}
    except Exception as e:
        st.warning(f"TomTom API error: {e}")
    
    return {"speed": None, "freeFlow": None, "congestion": "N/A"}

def process_site(lat, lon, fast, rapid, ultra, fast_kw, rapid_kw, ultra_kw):
    """Process a single site and gather all information"""
    with st.spinner(f"Processing site at {lat}, {lon}..."):
        # Basic coordinates
        easting, northing = convert_to_british_grid(lat, lon)
        
        # Postcode information
        postcode, ward, district = get_postcode_info(lat, lon)
        
        # Detailed geocoding
        geo = get_geocode_details(lat, lon)
        
        # Power calculation
        kva = calculate_kva(fast, rapid, ultra, fast_kw, rapid_kw, ultra_kw)
        
        # Traffic information
        traffic = get_tomtom_traffic(lat, lon)
        
        # Amenities
        amenities = get_nearby_amenities(lat, lon)
        
        # Road information using proper Google Roads API
        road_info = get_road_info_google_roads(lat, lon)
        
        return {
            "latitude": lat,
            "longitude": lon,
            "easting": easting,
            "northing": northing,
            "postcode": postcode,
            "ward": ward,
            "district": district,
            "street": geo.get("street", "N/A"),
            "street_number": geo.get("street_number", "N/A"),
            "neighborhood": geo.get("neighborhood", "N/A"),
            "city": geo.get("city", "N/A"),
            "county": geo.get("county", "N/A"),
            "region": geo.get("region", "N/A"),
            "country": geo.get("country", "N/A"),
            "formatted_address": geo.get("formatted_address", "N/A"),
            "fast_chargers": fast,
            "rapid_chargers": rapid,
            "ultra_chargers": ultra,
            "required_kva": kva,
            "traffic_speed": traffic["speed"],
            "traffic_freeflow": traffic["freeFlow"],
            "traffic_congestion": traffic["congestion"],
            "amenities": amenities,
            "road_type": road_info["road_type"],
            "road_name": road_info["road_name"],
            "speed_limit": road_info["speed_limit"],
            "place_id": road_info.get("place_id")
        }

# ==============================
# MAP FUNCTIONS
# ==============================

def add_google_traffic_layer(m):
    """Add Google Traffic layer to folium map"""
    folium.TileLayer(
        tiles=f"https://mt1.google.com/vt/lyrs=h,traffic&x={{x}}&y={{y}}&z={{z}}&key={GOOGLE_API_KEY}",
        attr="Google Traffic",
        name="Traffic",
        overlay=True,
        control=True
    ).add_to(m)

def create_single_map(site, show_traffic=False):
    """Create a map for a single site"""
    m = folium.Map(
        location=[site["latitude"], site["longitude"]], 
        zoom_start=15,
        tiles=f"https://mt1.google.com/vt/lyrs=m&x={{x}}&y={{y}}&z={{z}}&key={GOOGLE_API_KEY}", 
        attr="Google Maps"
    )
    
    popup_content = f"""
    <b>📍 {site.get('formatted_address', 'Unknown Address')}</b><br>
    <b>🔌 Power:</b> {site.get('required_kva','N/A')} kVA<br>
    <b>🛣️ Road:</b> {site.get('road_name','N/A')} ({site.get('road_type','N/A')})<br>
    <b>🚗 Speed Limit:</b> {site.get('speed_limit','N/A')} mph<br>
    <b>🚦 Traffic:</b> {site.get('traffic_congestion','N/A')} ({site.get('traffic_speed','N/A')}/{site.get('traffic_freeflow','N/A')} mph)<br>
    <b>🏪 Nearby:</b> {site.get('amenities','N/A')[:150]}{'...' if len(str(site.get('amenities',''))) > 150 else ''}
    """
    
    folium.Marker(
        [site["latitude"], site["longitude"]], 
        popup=folium.Popup(popup_content, max_width=300),
        tooltip="🔋 EV Charging Site",
        icon=folium.Icon(color="green", icon="bolt", prefix="fa")
    ).add_to(m)
    
    if show_traffic:
        add_google_traffic_layer(m)
    
    folium.LayerControl().add_to(m)
    return m

def create_batch_map(sites, show_traffic=False):
    """Create a map for multiple sites"""
    if not sites:
        return None
        
    # Calculate center point
    valid_sites = [s for s in sites if s.get("latitude") and s.get("longitude")]
    if not valid_sites:
        return None
        
    center_lat = sum(s["latitude"] for s in valid_sites) / len(valid_sites)
    center_lon = sum(s["longitude"] for s in valid_sites) / len(valid_sites)
    
    m = folium.Map(
        location=[center_lat, center_lon], 
        zoom_start=8,
        tiles=f"https://mt1.google.com/vt/lyrs=m&x={{x}}&y={{y}}&z={{z}}&key={GOOGLE_API_KEY}", 
        attr="Google Maps"
    )
    
    colors = ["red", "blue", "green", "purple", "orange", "darkred", "lightred", 
              "beige", "darkblue", "darkgreen", "cadetblue", "darkpurple", "white", 
              "pink", "lightblue", "lightgreen", "gray", "black", "lightgray"]
    
    for i, site in enumerate(valid_sites):
        color = colors[i % len(colors)]
        
        popup_content = f"""
        <b>📍 Site {i+1}:</b> {site.get('formatted_address','Unknown Address')}<br>
        <b>🔌 Power:</b> {site.get('required_kva','N/A')} kVA<br>
        <b>🛣️ Road:</b> {site.get('road_name','N/A')} ({site.get('road_type','N/A')})<br>
        <b>🚗 Speed Limit:</b> {site.get('speed_limit','N/A')} mph<br>
        <b>🚦 Traffic:</b> {site.get('traffic_congestion','N/A')}<br>
        <b>🏪 Nearby:</b> {site.get('amenities','N/A')[:100]}{'...' if len(str(site.get('amenities',''))) > 100 else ''}
        """
        
        folium.Marker(
            [site["latitude"], site["longitude"]], 
            popup=folium.Popup(popup_content, max_width=300),
            tooltip=f"🔋 EV Site {i+1}",
            icon=folium.Icon(color=color, icon="bolt", prefix="fa")
        ).add_to(m)
    
    if show_traffic:
        add_google_traffic_layer(m)
    
    folium.LayerControl().add_to(m)
    return m

# ==============================
# STREAMLIT APP
# ==============================

st.set_page_config(page_title="EV Charger Site Generator", page_icon="🔋", layout="wide")

# Header
st.title("🔋 EV Charger Site Generator (CPO Edition)")
st.markdown("*Comprehensive site analysis for EV charging infrastructure planning*")

# Sidebar
with st.sidebar:
    st.header("⚙️ Settings")
    
    st.subheader("Charger Power Settings")
    fast_kw = st.number_input("Fast Charger Power (kW)", value=22, min_value=1, max_value=100)
    rapid_kw = st.number_input("Rapid Charger Power (kW)", value=60, min_value=1, max_value=200)
    ultra_kw = st.number_input("Ultra Charger Power (kW)", value=150, min_value=1, max_value=400)
    
    st.subheader("Map Settings")
    show_traffic = st.checkbox("Show Google Traffic Layer", value=False)
    
    st.subheader("API Status")
    st.success("✅ Google Maps API") if GOOGLE_API_KEY else st.error("❌ Google Maps API")
    st.success("✅ TomTom API") if TOMTOM_API_KEY else st.warning("⚠️ TomTom API (Optional)")

# Main tabs
tab1, tab2 = st.tabs(["📍 Single Site Analysis", "📁 Batch Processing"])

# --- SINGLE SITE ---
with tab1:
    st.subheader("🔍 Analyze Single Site")
    
    col1, col2 = st.columns(2)
    
    with col1:
        lat = st.text_input("Latitude", value="51.5074", help="Enter latitude in decimal degrees")
        lon = st.text_input("Longitude", value="-0.1278", help="Enter longitude in decimal degrees")
    
    with col2:
        fast = st.number_input("Fast Chargers", min_value=0, value=2, help=f"Number of {fast_kw}kW chargers")
        rapid = st.number_input("Rapid Chargers", min_value=0, value=2, help=f"Number of {rapid_kw}kW chargers")
        ultra = st.number_input("Ultra Chargers", min_value=0, value=1, help=f"Number of {ultra_kw}kW chargers")

    if st.button("🔍 Analyze Site", type="primary"):
        try:
            lat_float, lon_float = float(lat), float(lon)
            if not (-90 <= lat_float <= 90) or not (-180 <= lon_float <= 180):
                st.error("Invalid coordinates. Latitude must be between -90 and 90, longitude between -180 and 180.")
            else:
                site = process_site(lat_float, lon_float, fast, rapid, ultra, fast_kw, rapid_kw, ultra_kw)
                st.session_state["single_site"] = site
                st.success("✅ Site analysis completed!")
        except ValueError:
            st.error("Invalid coordinate format. Please enter numeric values.")
        except Exception as e:
            st.error(f"Error analyzing site: {e}")

    if "single_site" in st.session_state:
        site = st.session_state["single_site"]
        
        # Key metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Required kVA", site["required_kva"])
        with col2:
            st.metric("Road Type", site["road_type"])
        with col3:
            st.metric("Traffic Level", site["traffic_congestion"])
        with col4:
            speed_limit = site["speed_limit"]
            st.metric("Speed Limit", f"{speed_limit} mph" if speed_limit else "N/A")
        
        # Detailed information
        st.subheader("📋 Detailed Site Information")
        
        detail_tabs = st.tabs(["🏠 Location", "🔌 Power", "🛣️ Road Info", "🚦 Traffic", "🏪 Amenities"])
        
        with detail_tabs[0]:
            st.write(f"**Address:** {site['formatted_address']}")
            st.write(f"**Postcode:** {site['postcode']}")
            st.write(f"**Ward:** {site['ward']}")
            st.write(f"**District:** {site['district']}")
            st.write(f"**British Grid:** {site['easting']}, {site['northing']}")
        
        with detail_tabs[1]:
            st.write(f"**Fast Chargers:** {site['fast_chargers']} × {fast_kw}kW")
            st.write(f"**Rapid Chargers:** {site['rapid_chargers']} × {rapid_kw}kW")
            st.write(f"**Ultra Chargers:** {site['ultra_chargers']} × {ultra_kw}kW")
            st.write(f"**Total Required kVA:** {site['required_kva']}")
        
        with detail_tabs[2]:
            st.write(f"**Road Name:** {site['road_name']}")
            st.write(f"**Road Type:** {site['road_type']}")
            st.write(f"**Speed Limit:** {site['speed_limit']} mph" if site['speed_limit'] else "Speed Limit: N/A")
            if site.get('place_id'):
                st.write(f"**Google Place ID:** {site['place_id']}")
        
        with detail_tabs[3]:
            st.write(f"**Congestion Level:** {site['traffic_congestion']}")
            if site['traffic_speed']:
                st.write(f"**Current Speed:** {site['traffic_speed']} mph")
                st.write(f"**Free Flow Speed:** {site['traffic_freeflow']} mph")
        
        with detail_tabs[4]:
            st.write(f"**Nearby Amenities:** {site['amenities']}")
        
        # Map
        st.subheader("🗺️ Site Map")
        map_obj = create_single_map(site, show_traffic)
        st_folium(map_obj, width=700, height=500, returned_objects=["last_object_clicked"])

# --- BATCH PROCESSING ---
with tab2:
    st.subheader("📁 Batch Processing")
    st.markdown("Upload a CSV file with the required columns to analyze multiple sites at once.")
    
    # File upload
    uploaded = st.file_uploader(
        "Upload CSV file", 
        type="csv",
        help="Required columns: latitude, longitude, fast, rapid, ultra"
    )
    
    if uploaded:
        try:
            df = pd.read_csv(uploaded)
            
            st.subheader("📊 Data Preview")
            st.dataframe(df.head())
            
            # Check required columns
            required_cols = {"latitude", "longitude", "fast", "rapid", "ultra"}
            missing_cols = required_cols - set(df.columns)
            
            if missing_cols:
                st.error(f"❌ Missing required columns: {', '.join(missing_cols)}")
                st.info("Required columns: latitude, longitude, fast, rapid, ultra")
            else:
                st.success(f"✅ CSV file loaded successfully! Found {len(df)} sites to process.")
                
                if st.button("🚀 Process All Sites", type="primary"):
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    results = []
                    
                    for i, row in df.iterrows():
                        try:
                            status_text.text(f"Processing site {i+1}/{len(df)}: ({row['latitude']}, {row['longitude']})")
                            site = process_site(
                                float(row["latitude"]), 
                                float(row["longitude"]),
                                int(row.get("fast", 0)), 
                                int(row.get("rapid", 0)), 
                                int(row.get("ultra", 0)),
                                fast_kw, rapid_kw, ultra_kw
                            )
                            results.append(site)
                        except Exception as e:
                            st.warning(f"Error processing row {i+1}: {e}")
                            # Add empty result to maintain alignment
                            results.append({
                                "latitude": row.get("latitude"),
                                "longitude": row.get("longitude"),
                                "error": str(e)
                            })
                        
                        progress_bar.progress((i + 1) / len(df))
                    
                    status_text.text("✅ Batch processing completed!")
                    st.session_state["batch_results"] = results

        except Exception as e:
            st.error(f"Error reading CSV file: {e}")

    # Display batch results
    if "batch_results" in st.session_state:
        results = st.session_state["batch_results"]
        
        st.subheader("📊 Batch Results")
        
        # Create results dataframe
        df_out = pd.DataFrame(results)
        
        # Summary statistics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            total_sites = len(results)
            st.metric("Total Sites", total_sites)
        
        with col2:
            successful = sum(1 for r in results if "error" not in r)
            st.metric("Successful", successful)
        
        with col3:
            if "required_kva" in df_out.columns:
                avg_kva = df_out["required_kva"].mean()
                st.metric("Avg kVA", f"{avg_kva:.1f}" if not pd.isna(avg_kva) else "N/A")
        
        with col4:
            failed = total_sites - successful
            st.metric("Failed", failed)
        
        # Results table
        st.dataframe(df_out, use_container_width=True)
        
        # Map
        st.subheader("🗺️ Sites Map")
        batch_map = create_batch_map(results, show_traffic=show_traffic)
        if batch_map:
            st_folium(batch_map, width=700, height=500)
        else:
            st.error("Unable to create map - no valid sites found.")
        
        # Download results
        csv_data = df_out.to_csv(index=False)
        st.download_button(
            label="📥 Download Results CSV",
            data=csv_data,
            file_name=f"ev_site_analysis_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )

# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: #666;'>
        <p>🔋 EV Charger Site Generator v2.0 | Built with Streamlit</p>
        <p>Powered by Google Maps API, TomTom Traffic API, and Postcodes.io</p>
    </div>
    """, 
    unsafe_allow_html=True
)
