import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
from pyproj import Transformer
import time

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
    try:
        r = requests.get(f"https://api.postcodes.io/postcodes?lon={lon}&lat={lat}", timeout=10)
        data = r.json()
        if data.get("status") == 200 and data["result"]:
            res = data["result"][0]
            return res.get("postcode","N/A"), res.get("admin_ward","N/A"), res.get("admin_district","N/A")
    except:
        pass
    return "N/A","N/A","N/A"

@st.cache_data
def get_geocode_details(lat, lon):
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
    except:
        pass
    return {}

@st.cache_data
def get_nearby_amenities(lat, lon, radius=300, types=None):
    if types is None:
        types = ["charging_station","restaurant","cafe","supermarket","parking","gas_station"]
    amenities=[]
    try:
        for t in types:
            r = requests.get("https://maps.googleapis.com/maps/api/place/nearbysearch/json",
                             params={"location": f"{lat},{lon}", "radius": radius, "type": t, "key": GOOGLE_API_KEY}, timeout=10)
            results = r.json().get("results",[])
            for res in results:
                name = res.get("name")
                if name:
                    amenities.append(f"{name} ({t})")
        return ", ".join(amenities) if amenities else "None"
    except Exception as e:
        return f"Error: {e}"

@st.cache_data
def get_road_info(lat, lon):
    try:
        r = requests.get("https://roads.googleapis.com/v1/snapToRoads",
                         params={"path":f"{lat},{lon}","interpolate":"false","key":GOOGLE_API_KEY}, timeout=10)
        snapped = r.json().get("snappedPoints",[])
        if snapped:
            place_id = snapped[0].get("placeId")
            road_type = snapped[0].get("roadType","Unknown")
            r2 = requests.get("https://roads.googleapis.com/v1/speedLimits",
                              params={"placeId": place_id,"key":GOOGLE_API_KEY}, timeout=10)
            speed_info = r2.json().get("speedLimits",[])
            speed_limit = speed_info[0]["speedLimit"] if speed_info else None
            return {"road_type": road_type, "speed_limit": speed_limit}
    except:
        pass
    return {"road_type":"Unknown","speed_limit":None}

@st.cache_data
def get_distance_matrix(orig_lat, orig_lon, dest_lat, dest_lon):
    try:
        r = requests.get("https://maps.googleapis.com/maps/api/distancematrix/json",
                         params={"origins":f"{orig_lat},{orig_lon}",
                                 "destinations":f"{dest_lat},{dest_lon}",
                                 "key":GOOGLE_API_KEY,
                                 "departure_time":"now"}, timeout=10)
        data = r.json()
        if data.get("rows"):
            dur = data["rows"][0]["elements"][0].get("duration_in_traffic")
            if dur: return dur.get("value")/60
    except:
        pass
    return None

@st.cache_resource
def get_transformer():
    return Transformer.from_crs("epsg:4326","epsg:27700")

def convert_to_british_grid(lat, lon):
    transformer = get_transformer()
    try:
        e,n = transformer.transform(lat, lon)
        return round(e), round(n)
    except:
        return None,None

def calculate_kva(fast, rapid, ultra, fast_kw=22, rapid_kw=60, ultra_kw=150):
    return round((fast*fast_kw + rapid*rapid_kw + ultra*ultra_kw)/0.9,2)

def get_tomtom_traffic(lat, lon):
    try:
        url="https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"
        params={"point":f"{lat},{lon}","key":TOMTOM_API_KEY}
        r = requests.get(url, params=params, timeout=10)
        flow = r.json().get("flowSegmentData",{})
        speed, freeflow = flow.get("currentSpeed"), flow.get("freeFlowSpeed")
        if speed and freeflow:
            ratio = speed/freeflow
            if ratio>0.85: level="Low"
            elif ratio>0.6: level="Medium"
            else: level="High"
            return {"speed":speed,"freeFlow":freeflow,"congestion":level}
    except:
        pass
    return {"speed":None,"freeFlow":None,"congestion":"N/A"}

def process_site(lat, lon, fast, rapid, ultra, fast_kw, rapid_kw, ultra_kw):
    easting,northing = convert_to_british_grid(lat, lon)
    postcode, ward, district = get_postcode_info(lat, lon)
    geo = get_geocode_details(lat, lon)
    kva = calculate_kva(fast, rapid, ultra, fast_kw, rapid_kw, ultra_kw)
    traffic = get_tomtom_traffic(lat, lon) if TOMTOM_API_KEY else {"speed":None,"freeFlow":None,"congestion":"N/A"}
    amenities = get_nearby_amenities(lat, lon)
    road_info = get_road_info(lat, lon)
    travel_time_to_center = get_distance_matrix(lat, lon, 51.5074, -0.1278)  # London center
    return {
        "latitude": lat, "longitude": lon, "easting": easting, "northing": northing,
        "postcode": postcode, "ward": ward, "district": district,
        "street": geo.get("street"), "street_number": geo.get("street_number"),
        "neighborhood": geo.get("neighborhood"), "city": geo.get("city"),
        "county": geo.get("county"), "region": geo.get("region"), "country": geo.get("country"),
        "formatted_address": geo.get("formatted_address"),
        "fast_chargers": fast, "rapid_chargers": rapid, "ultra_chargers": ultra,
        "required_kva": kva,
        "traffic_speed": traffic["speed"], "traffic_freeflow": traffic["freeFlow"], "traffic_congestion": traffic["congestion"],
        "amenities": amenities,
        "road_type": road_info["road_type"],
        "speed_limit": road_info["speed_limit"],
        "travel_time_to_center_min": travel_time_to_center
    }

# ==============================
# MAP FUNCTIONS
# ==============================

def add_google_traffic_layer(m):
    folium.TileLayer(
        tiles=f"https://mt1.google.com/vt/lyrs=h,traffic&x={{x}}&y={{y}}&z={{z}}&key={GOOGLE_API_KEY}",
        attr="Google Traffic", name="Traffic"
    ).add_to(m)

def create_single_map(site, show_traffic=False):
    m = folium.Map(location=[site["latitude"], site["longitude"]], zoom_start=15,
                   tiles=f"https://mt1.google.com/vt/lyrs=m&x={{x}}&y={{y}}&z={{z}}&key={GOOGLE_API_KEY}", attr="Google Maps")
    popup = f"""
    {site.get('formatted_address', 'Unknown Address')}<br>
    Power: {site.get('required_kva','N/A')} kVA<br>
    Traffic: {site.get('traffic_congestion','N/A')} ({site.get('traffic_speed','N/A')}/{site.get('traffic_freeflow','N/A')} mph)<br>
    Road Type: {site.get('road_type','N/A')}<br>
    Speed Limit: {site.get('speed_limit','N/A')}<br>
    Travel time to London center: {site.get('travel_time_to_center_min','N/A')} min<br>
    Nearby Amenities: {site.get('amenities','N/A')}
    """
    folium.Marker([site["latitude"], site["longitude"]], popup=popup, tooltip="EV Site", icon=folium.Icon(color="pink")).add_to(m)
    if show_traffic: add_google_traffic_layer(m)
    folium.LayerControl().add_to(m)
    return m

def create_batch_map(sites, show_traffic=False):
    if not sites: return None
    center_lat = sum(s["latitude"] for s in sites)/len(sites)
    center_lon = sum(s["longitude"] for s in sites)/len(sites)
    m = folium.Map(location=[center_lat, center_lon], zoom_start=6,
                   tiles=f"https://mt1.google.com/vt/lyrs=m&x={{x}}&y={{y}}&z={{z}}&key={GOOGLE_API_KEY}", attr="Google Maps")
    for i, site in enumerate(sites):
        popup = f"""
        Site {i+1}: {site.get('formatted_address','Unknown Address')}<br>
        Power: {site.get('required_kva','N/A')} kVA<br>
        Traffic: {site.get('traffic_congestion','N/A')}<br>
        Road Type: {site.get('road_type','N/A')}<br>
        Speed Limit: {site.get('speed_limit','N/A')}<br>
        Travel time to London center: {site.get('travel_time_to_center_min','N/A')} min<br>
        Nearby Amenities: {site.get('amenities','N/A')}
        """
        folium.Marker([site["latitude"], site["longitude"]], popup=popup, tooltip="EV Site", icon=folium.Icon(color="pink")).add_to(m)
    if show_traffic: add_google_traffic_layer(m)
    folium.LayerControl().add_to(m)
    return m

# ==============================
# STREAMLIT APP
# ==============================

st.set_page_config(page_title="EV Charger Site Generator", page_icon="🔋", layout="wide")
st.title("🔋 EV Charger Site Generator (CPO Edition)")

# Sidebar
with st.sidebar:
    st.header("⚙️ Settings")
    fast_kw = st.number_input("Fast Charger Power (kW)", value=22)
    rapid_kw = st.number_input("Rapid Charger Power (kW)", value=60)
    ultra_kw = st.number_input("Ultra Charger Power (kW)", value=150)
    show_traffic = st.checkbox("Show Google Traffic Layer", value=False)

# Tabs
tab1, tab2 = st.tabs(["📍 Single Site", "📁 Batch Processing"])

# --- SINGLE SITE ---
with tab1:
    st.subheader("Analyze Single Site")
    lat = st.text_input("Latitude", "51.5074")
    lon = st.text_input("Longitude", "-0.1278")
    fast = st.number_input("Fast Chargers", min_value=0, value=0)
    rapid = st.number_input("Rapid Chargers", min_value=0, value=0)
    ultra = st.number_input("Ultra Chargers", min_value=0, value=0)

    if st.button("🔍 Analyze Site"):
        try:
            site = process_site(float(lat), float(lon), fast, rapid, ultra, fast_kw, rapid_kw, ultra_kw)
            st.session_state["single_site"] = site
        except Exception as e:
            st.error(f"Error: {e}")

    if "single_site" in st.session_state:
        site = st.session_state["single_site"]
        st.metric("Required kVA", site["required_kva"])
        st.metric("Traffic Congestion", site["traffic_congestion"])
        st.metric("Road Type", site["road_type"])
        st.metric("Travel time to London center (min)", site["travel_time_to_center_min"])
        st.subheader("📋 Details")
        st.write(site)
        st.subheader("🗺️ Map")
        st_folium(create_single_map(site, show_traffic), width=700, height=500)

# --- BATCH PROCESSING ---
with tab2:
    st.subheader("Batch Processing")
    uploaded = st.file_uploader("Upload CSV with columns: latitude, longitude, fast, rapid, ultra", type="csv")
    if uploaded:
        df = pd.read_csv(uploaded)
        required_cols = {"latitude", "longitude", "fast", "rapid", "ultra"}
        if not required_cols.issubset(df.columns):
            st.error(f"Missing columns: {', '.join(required_cols - set(df.columns))}")
        else:
            if st.button("🚀 Process All Sites"):
                progress = st.progress(0)
                results=[]
                for i,row in df.iterrows():
                    try:
                        site = process_site(float(row["latitude"]), float(row["longitude"]),
                                            int(row.get("fast",0)), int(row.get("rapid",0)), int(row.get("ultra",0)),
                                            fast_kw, rapid_kw, ultra_kw)
                        results.append(site)
                    except:
                        results.append({})
                    progress.progress((i+1)/len(df))
                st.session_state["batch_results"] = results

    if "batch_results" in st.session_state:
        results = st.session_state["batch_results"]
        df_out = pd.DataFrame(results)
        st.subheader("📋 Batch Results")
        st.dataframe(df_out)
        st.subheader("🗺️ Map")
        st_folium(create_batch_map(results, show_traffic=show_traffic), width=700, height=500)
        st.download_button("📥 Download CSV", df_out.to_csv(index=False), "batch_results.csv", "text/csv")
