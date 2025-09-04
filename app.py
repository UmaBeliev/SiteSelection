import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
from pyproj import Transformer
import time

# ==============================
#           API KEYS
# ==============================
GOOGLE_API_KEY = st.secrets["google_api_key"]
TOMTOM_API_KEY = st.secrets.get("tomtom_api_key", "")

# ==============================
#           UTILITIES
# ==============================

@st.cache_data
def get_postcode_info(lat: float, lon: float):
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
def get_street_name(lat: float, lon: float, debug=False) -> str:
    try:
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {"latlng": f"{lat},{lon}", "key": GOOGLE_API_KEY, "result_type": "street_address|route|premise"}
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        if debug:
            st.write(f"Google API Response: {data}")

        if data.get("status") == "OK":
            results = data.get("results", [])
            if results:
                for result in results:
                    comps = result.get("address_components", [])
                    street, number = None, None
                    for c in comps:
                        if "route" in c.get("types", []):
                            street = c["long_name"]
                        elif "street_number" in c.get("types", []):
                            number = c["long_name"]
                    if street:
                        return f"{number} {street}" if number else street
            return results[0].get("formatted_address", "Unknown")
        elif data.get("status") == "OVER_QUERY_LIMIT":
            return "Quota exceeded"
        elif data.get("status") == "REQUEST_DENIED":
            return "API denied"
        elif data.get("status") == "ZERO_RESULTS":
            return "No address found"
        else:
            return f"API Error: {data.get('status')}"
    except Exception as e:
        return f"Error: {e}"

def get_tomtom_traffic(lat, lon, api_key):
    try:
        url = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"
        params = {"point": f"{lat},{lon}", "key": api_key}
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            flow = r.json().get("flowSegmentData", {})
            speed, freeflow = flow.get("currentSpeed"), flow.get("freeFlowSpeed")
            if speed and freeflow:
                ratio = speed / freeflow
                if ratio > 0.85: level = "Low"
                elif ratio > 0.6: level = "Medium"
                else: level = "High"
                return {"speed": speed, "freeFlow": freeflow, "congestion": level}
        return {"speed": None, "freeFlow": None, "congestion": "Unknown"}
    except Exception as e:
        return {"speed": None, "freeFlow": None, "congestion": f"Error: {e}"}

def get_osm_road_width(lat, lon, radius=50):
    try:
        query = f"""
        [out:json];
        way(around:{radius},{lat},{lon})[highway];
        out tags;
        """
        url = "https://overpass-api.de/api/interpreter"
        r = requests.get(url, params={"data": query}, timeout=15)
        if r.status_code == 200:
            for el in r.json().get("elements", []):
                tags = el.get("tags", {})
                if "width" in tags:
                    return tags["width"]
                elif "lanes" in tags:
                    # approximate width if lanes are known
                    try:
                        lanes = int(tags["lanes"])
                        return str(lanes * 3.5)  # assume 3.5 m per lane
                    except:
                        pass
                elif "sidewalk:width" in tags:
                    return tags["sidewalk:width"]
        return "Unknown"
    except Exception as e:
        return f"Error: {e}"



def get_osm_amenities(lat, lon, radius=100):
    try:
        query = f"""
        [out:json];
        node(around:{radius},{lat},{lon})[amenity];
        out;
        """
        url = "https://overpass-api.de/api/interpreter"
        r = requests.get(url, params={"data": query}, timeout=15)
        if r.status_code == 200:
            amenities = [el["tags"]["amenity"] for el in r.json().get("elements", []) if "tags" in el and "amenity" in el["tags"]]
            return ", ".join(sorted(set(amenities))) if amenities else "None"
        return "Unknown"
    except Exception as e:
        return f"Error: {e}"

@st.cache_resource
def get_transformer():
    return Transformer.from_crs("epsg:4326", "epsg:27700")

def convert_to_british_grid(lat, lon):
    try:
        transformer = get_transformer()
        easting, northing = transformer.transform(lat, lon)
        return round(easting), round(northing)
    except:
        return None, None

def calculate_kva(fast, rapid, ultra, fast_kw=22, rapid_kw=60, ultra_kw=150):
    return round((fast * fast_kw + rapid * rapid_kw + ultra * ultra_kw) / 0.9, 2)

def process_site(lat, lon, fast, rapid, ultra, fast_kw, rapid_kw, ultra_kw, debug=False):
    easting, northing = convert_to_british_grid(lat, lon)
    postcode, ward, district = get_postcode_info(lat, lon)
    street = get_street_name(lat, lon, debug)
    kva = calculate_kva(fast, rapid, ultra, fast_kw, rapid_kw, ultra_kw)
    traffic = get_tomtom_traffic(lat, lon, TOMTOM_API_KEY) if TOMTOM_API_KEY else {"speed": None, "freeFlow": None, "congestion": "N/A"}
    road_width = get_osm_road_width(lat, lon)
    amenities = get_osm_amenities(lat, lon)
    return {
        "latitude": lat, "longitude": lon,
        "easting": easting, "northing": northing,
        "postcode": postcode, "ward": ward, "district": district, "street": street,
        "fast_chargers": fast, "rapid_chargers": rapid, "ultra_chargers": ultra,
        "required_kva": kva,
        "traffic_speed": traffic["speed"], "traffic_freeflow": traffic["freeFlow"], "traffic_congestion": traffic["congestion"],
        "road_width": road_width, "amenities": amenities
    }

# ==============================
#           MAPS
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
    {site['street']}<br>{site['postcode']}<br>
    Power: {site['required_kva']} kVA<br>
    Traffic: {site['traffic_congestion']} ({site['traffic_speed']}/{site['traffic_freeflow']} mph)<br>
    Road Width: {site['road_width']}<br>
    Amenities: {site['amenities']}
    """
    
    folium.Marker(
        [site["latitude"], site["longitude"]],
        popup=popup,
        tooltip="EV Site",
        icon=folium.Icon(color="pink")  # <-- pink marker
    ).add_to(m)
    if show_traffic: add_google_traffic_layer(m)
    folium.LayerControl().add_to(m)
    return m

def create_batch_map(sites, show_traffic=False):
    if not sites: return None
    center_lat = sum(s["latitude"] for s in sites) / len(sites)
    center_lon = sum(s["longitude"] for s in sites) / len(sites)
    m = folium.Map(location=[center_lat, center_lon], zoom_start=6,
                   tiles=f"https://mt1.google.com/vt/lyrs=m&x={{x}}&y={{y}}&z={{z}}&key={GOOGLE_API_KEY}", attr="Google Maps")
    for i, site in enumerate(sites):
        popup = f"""
        Site {i+1}: {site['street']}<br>
        Power: {site['required_kva']} kVA<br>
        Traffic: {site['traffic_congestion']}<br>
        Road Width: {site['road_width']}<br>
        Amenities: {site['amenities']}
        """
        
        folium.Marker(
        [site["latitude"], site["longitude"]],
        popup=popup,
        tooltip="EV Site",
        icon=folium.Icon(color="pink")  # <-- pink marker
    ).add_to(m)
    if show_traffic: add_google_traffic_layer(m)
    folium.LayerControl().add_to(m)
    return m

# ==============================
#           STREAMLIT APP
# ==============================
st.set_page_config(page_title="EV Charger Site Generator", page_icon="🔋", layout="wide")
st.title("🔋 EV Charger Site Generator")

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
        st.metric("Road Width", site["road_width"])
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
            missing = required_cols - set(df.columns)
            st.error(f"Missing columns: {', '.join(missing)}")
        else:
            if st.button("🚀 Process All Sites"):
                progress = st.progress(0)
                results, errors = [], []
                
                for i, row in df.iterrows():
                    try:
                        site = process_site(
                            float(row["latitude"]), float(row["longitude"]),
                            int(row.get("fast",0)), int(row.get("rapid",0)), int(row.get("ultra",0)),
                            fast_kw, rapid_kw, ultra_kw
                        )
                        results.append(site)
                    except Exception as e:
                        errors.append(f"Row {i+1}: {e}")
                        results.append({
                            "latitude": row.get("latitude"), "longitude": row.get("longitude"),
                            "easting": None, "northing": None,
                            "postcode": "Error", "ward": "Error", "district": "Error",
                            "street": f"Error: {str(e)[:30]}",
                            "fast_chargers": row.get("fast", 0),
                            "rapid_chargers": row.get("rapid", 0),
                            "ultra_chargers": row.get("ultra", 0),
                            "required_kva": 0,
                            "traffic_speed": None, "traffic_freeflow": None, "traffic_congestion": "Error",
                            "road_width": None, "amenities": None
                        })
                    
                    # Adaptive sleep
                    if site.get("street") in ["Quota exceeded", "API denied"]:
                        time.sleep(1.0)
                    else:
                        time.sleep(0.1)
                    
                    progress.progress((i+1)/len(df))
                
                st.session_state["batch_results"] = results
                
                if errors:
                    st.warning(f"{len(errors)} errors occurred:")
                    st.dataframe(pd.DataFrame(errors, columns=["Error"]))
                
                st.success("Batch processing complete!")
    
    if "batch_results" in st.session_state:
        results = st.session_state["batch_results"]
        df_out = pd.DataFrame(results)
        st.subheader("📋 Batch Results")
        st.dataframe(df_out)
        st.subheader("🗺️ Map")
        st_folium(create_batch_map(results, show_traffic=show_traffic), width=700, height=500)
        st.download_button("📥 Download CSV", df_out.to_csv(index=False), "batch_results.csv", "text/csv")
