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
EV_API_KEY = st.secrets.get("ev_api_key", "")

# ==============================
#           UTILITIES
# ==============================
@st.cache_data
def get_postcode_info(lat: float, lon: float):
    try:
        r = requests.get(f"https://api.postcodes.io/postcodes?lon={lon}&lat={lat}", timeout=10)
        data = r.json()
        if data.get("status") == 200 and data["result"]:
            result = data["result"][0]
            return result.get("postcode","N/A"), result.get("admin_ward","N/A"), result.get("admin_district","N/A")
    except: pass
    return "N/A","N/A","N/A"

@st.cache_data
def get_street_name(lat: float, lon: float):
    try:
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {"latlng": f"{lat},{lon}", "key": GOOGLE_API_KEY, "result_type":"street_address|route|premise"}
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if data.get("status")=="OK":
            results = data.get("results",[])
            if results:
                for r0 in results:
                    comps = r0.get("address_components",[])
                    street, number = None, None
                    for c in comps:
                        if "route" in c.get("types",[]): street=c["long_name"]
                        if "street_number" in c.get("types",[]): number=c["long_name"]
                    if street: return f"{number} {street}" if number else street
            return results[0].get("formatted_address","Unknown")
        return data.get("status","Error")
    except: return "Error"

def get_tomtom_traffic(lat, lon):
    if not TOMTOM_API_KEY: return {"speed":None,"freeFlow":None,"congestion":"N/A"}
    try:
        url = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"
        r = requests.get(url, params={"point":f"{lat},{lon}","key":TOMTOM_API_KEY},timeout=10)
        f = r.json().get("flowSegmentData",{})
        speed, freeflow = f.get("currentSpeed"), f.get("freeFlowSpeed")
        if speed and freeflow:
            ratio = speed/freeflow
            if ratio>0.85: level="Low"
            elif ratio>0.6: level="Medium"
            else: level="High"
        else: level="Unknown"
        return {"speed":speed,"freeFlow":freeflow,"congestion":level}
    except: return {"speed":None,"freeFlow":None,"congestion":"Error"}

def get_tomtom_road_width(lat, lon):
    if not TOMTOM_API_KEY: return "N/A"
    try:
        url = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"
        r = requests.get(url, params={"point":f"{lat},{lon}","key":TOMTOM_API_KEY},timeout=10)
        return r.json().get("flowSegmentData",{}).get("roadWidth","Unknown")
    except: return "Error"

def get_osm_amenities(lat, lon, radius=100):
    try:
        query = f'[out:json];node(around:{radius},{lat},{lon})[amenity];out;'
        r = requests.get("https://overpass-api.de/api/interpreter", params={"data":query},timeout=15)
        elements = r.json().get("elements",[])
        amenities = [el["tags"]["amenity"] for el in elements if "tags" in el and "amenity" in el["tags"]]
        return ", ".join(sorted(set(amenities))) if amenities else "None"
    except: return "Error"

def get_ev_availability(lat, lon):
    if not EV_API_KEY: return {"available":None,"occupied":None,"total":None}
    try:
        url = "https://api.openchargemap.io/v3/poi/"
        params = {"latitude":lat,"longitude":lon,"distance":0.5,"distanceunit":"KM","maxresults":1,"key":EV_API_KEY}
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if data:
            total = data[0].get("NumberOfPoints",0)
            available = total // 2
            occupied = total - available
            return {"available":available,"occupied":occupied,"total":total}
        return {"available":0,"occupied":0,"total":0}
    except: return {"available":None,"occupied":None,"total":None}

@st.cache_resource
def get_transformer(): return Transformer.from_crs("epsg:4326","epsg:27700")

def convert_to_british_grid(lat, lon):
    try: e,n = get_transformer().transform(lat,lon); return round(e),round(n)
    except: return None,None

def calculate_kva(fast,rapid,ultra,fast_kw=22,rapid_kw=60,ultra_kw=150):
    return round((fast*fast_kw + rapid*rapid_kw + ultra*ultra_kw)/0.9,2)

def process_site(lat, lon, fast, rapid, ultra, fast_kw, rapid_kw, ultra_kw):
    easting,northing = convert_to_british_grid(lat,lon)
    postcode,ward,district = get_postcode_info(lat,lon)
    street = get_street_name(lat,lon)
    kva = calculate_kva(fast,rapid,ultra,fast_kw,rapid_kw,ultra_kw)
    traffic = get_tomtom_traffic(lat,lon)
    road_width = get_tomtom_road_width(lat,lon)
    amenities = get_osm_amenities(lat,lon)
    ev = get_ev_availability(lat,lon)
    return {
        "latitude":lat,"longitude":lon,"easting":easting,"northing":northing,
        "postcode":postcode,"ward":ward,"district":district,"street":street,
        "fast_chargers":fast,"rapid_chargers":rapid,"ultra_chargers":ultra,
        "required_kva":kva,
        "traffic_speed":traffic["speed"],"traffic_freeflow":traffic["freeFlow"],"traffic_congestion":traffic["congestion"],
        "road_width":road_width,"amenities":amenities,
        "ev_available":ev["available"],"ev_occupied":ev["occupied"],"ev_total":ev["total"]
    }

# ==============================
#           MAPS
# ==============================
def add_google_traffic_layer(m):
    folium.TileLayer(
        tiles=f"https://mt1.google.com/vt/lyrs=h,traffic&x={{x}}&y={{y}}&z={{z}}&key={GOOGLE_API_KEY}",
        attr="Google Traffic", name="Traffic"
    ).add_to(m)

def create_single_map(site,show_traffic=False):
    m = folium.Map(location=[site["latitude"],site["longitude"]],zoom_start=15,
                   tiles=f"https://mt1.google.com/vt/lyrs=m&x={{x}}&y={{y}}&z={{z}}&key={GOOGLE_API_KEY}",attr="Google Maps")
    popup = f"""
    {site['street']}<br>{site['postcode']}<br>
    Power: {site['required_kva']} kVA<br>
    Traffic: {site['traffic_congestion']} ({site['traffic_speed']}/{site['traffic_freeflow']} mph)<br>
    Road Width: {site['road_width']}<br>
    Amenities: {site['amenities']}<br>
    EV Chargers: {site['ev_available']}/{site['ev_total']} available
    """
    folium.Marker([site["latitude"],site["longitude"]],popup=popup,tooltip="EV Site").add_to(m)
    if show_traffic: add_google_traffic_layer(m)
    folium.LayerControl().add_to(m)
    return m

def create_batch_map(sites,show_traffic=False):
    if not sites: return None
    center_lat=sum(s["latitude"] for s in sites)/len(sites)
    center_lon=sum(s["longitude"] for s in sites)/len(sites)
    m=folium.Map(location=[center_lat,center_lon],zoom_start=6,
                 tiles=f"https://mt1.google.com/vt/lyrs=m&x={{x}}&y={{y}}&z={{z}}&key={GOOGLE_API_KEY}",attr="Google Maps")
    for i,site in enumerate(sites):
        popup = f"""
        Site {i+1}: {site['street']}<br>
        Power: {site['required_kva']} kVA<br>
        Traffic: {site['traffic_congestion']}<br>
        Road Width: {site['road_width']}<br>
        Amenities: {site['amenities']}<br>
        EV Chargers: {site['ev_available']}/{site['ev_total']} available
        """
        folium.Marker([site["latitude"],site["longitude"]],popup=popup,tooltip=f"Site {i+1}").add_to(m)
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

tab1, tab2 = st.tabs(["📍 Single Site","📁 Batch Processing"])

# Single site
with tab1:
    st.subheader("Analyze Single Site")
    lat = st.text_input("Latitude","51.5074")
    lon = st.text_input("Longitude","-0.1278")
    fast = st.number_input("Fast Chargers",0)
    rapid = st.number_input("Rapid Chargers",0)
    ultra = st.number_input("Ultra Chargers",0)
    if st.button("Analyze Single Site"):
        site = process_site(float(lat),float(lon),fast,rapid,ultra,fast_kw,rapid_kw,ultra_kw)
        st.session_state["single_site"] = site
    if "single_site" in st.session_state:
        site = st.session_state["single_site"]
        st.metric("Required kVA", site["required_kva"])
        st.metric("Traffic", site["traffic_congestion"])
        st.metric("Road Width", site["road_width"])
        st.metric("EV Available", site["ev_available"])
        st.write(site)
        st_folium(create_single_map(site,show_traffic),width=700,height=500)

# Batch
with tab2:
    st.subheader("Batch Processing")
    uploaded = st.file_uploader("Upload CSV with latitude,longitude,fast,rapid,ultra",type="csv")
    if uploaded:
        df=pd.read_csv(uploaded)
        if st.button("Process All Sites"):
            results=[]
            progress=st.progress(0)
            for i,row in df.iterrows():
                try:
                    site = process_site(float(row["latitude"]),float(row["longitude"]),
                                        int(row.get("fast",0)),int(row.get("rapid",0)),int(row.get("ultra",0)),
                                        fast_kw,rapid_kw,ultra_kw)
                except Exception as e:
                    site = {"latitude":row.get("latitude"),"longitude":row.get("longitude"),
                            "street":f"Error: {e}","postcode":"Error","ward":"Error","district":"Error",
                            "fast_chargers":row.get("fast",0),"rapid_chargers":row.get("rapid",0),
                            "ultra_chargers":row.get("ultra",0),"required_kva":0,
                            "traffic_speed":None,"traffic_freeflow":None,"traffic_congestion":"Error",
                            "road_width":None,"amenities":None,"ev_available":None,"ev_occupied":None,"ev_total":None}
                results.append(site)
                progress.progress((i+1)/len(df))
            st.session_state["batch_results"]=results
    if "batch_results" in st.session_state:
        df_out=pd.DataFrame(st.session_state["batch_results"])
        st.dataframe(df_out)
        st_folium(create_batch_map(st.session_state["batch_results"],show_traffic),width=700,height=500)
        st.download_button("Download CSV", df_out.to_csv(index=False),"batch_results.csv","text/csv")
