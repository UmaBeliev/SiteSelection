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

# --- CONFIGURATION ---
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

# --- DATA MODEL ---
@dataclass
class SiteData:
    latitude: float
    longitude: float
    easting: int = None
    northing: int = None
    postcode: str = "N/A"
    ward: str = "N/A"
    district: str = "N/A"
    street: str = "Unknown"
    fast_chargers: int = 0
    rapid_chargers: int = 0
    ultra_chargers: int = 0
    required_kva: float = 0.0
    errors: str = ""

# --- SERVICES ---
class LocationService:
    def __init__(self):
        self.transformer = Transformer.from_crs("epsg:4326", "epsg:27700")
    
    def convert_coordinates(self, lat: float, lon: float) -> Tuple[int, int]:
        """Convert to British National Grid"""
        try:
            easting, northing = self.transformer.transform(lat, lon)
            return round(easting), round(northing)
        except:
            return None, None

class PowerCalculator:
    @staticmethod
    def calculate_kva(fast: int, rapid: int, ultra: int, 
                     fast_kw: float, rapid_kw: float, ultra_kw: float) -> float:
        """Calculate total kVA requirement"""
        total_kw = fast * fast_kw + rapid * rapid_kw + ultra * ultra_kw
        return round(total_kw / 0.9, 2)  # 0.9 power factor

class SiteProcessor:
    def __init__(self):
        self.location = LocationService()
        self.power = PowerCalculator()
    
    def process_site(self, lat: float, lon: float, fast: int, rapid: int, ultra: int,
                    fast_kw: float, rapid_kw: float, ultra_kw: float) -> SiteData:
        """Process a single site"""
        site = SiteData(latitude=lat, longitude=lon, fast_chargers=fast, 
                       rapid_chargers=rapid, ultra_chargers=ultra)
        
        try:
            # Get location data
            site.easting, site.northing = self.location.convert_coordinates(lat, lon)
            site.postcode, site.ward, site.district = get_postcode_info(lat, lon)
            site.street = get_street_name(lat, lon)
            
            # Calculate power
            site.required_kva = self.power.calculate_kva(
                fast, rapid, ultra, fast_kw, rapid_kw, ultra_kw
            )
            
        except Exception as e:
            site.errors = str(e)
        
        return site

# --- UI COMPONENTS ---
def create_map(site: SiteData) -> folium.Map:
    """Create a simple map for single site"""
    m = folium.Map(location=[site.latitude, site.longitude], zoom_start=15)
    
    popup_text = f"{site.street}, {site.postcode}\nPower: {site.required_kva} kVA"
    folium.Marker(
        [site.latitude, site.longitude],
        popup=popup_text,
        tooltip="EV Charging Site"
    ).add_to(m)
    
    return m

def create_batch_map(sites: List[SiteData]) -> folium.Map:
    """Create a map showing multiple sites"""
    if not sites:
        return None
    
    # Calculate center point
    valid_sites = [s for s in sites if s.latitude and s.longitude]
    if not valid_sites:
        return None
    
    center_lat = sum(s.latitude for s in valid_sites) / len(valid_sites)
    center_lon = sum(s.longitude for s in valid_sites) / len(valid_sites)
    
    m = folium.Map(location=[center_lat, center_lon], zoom_start=8)
    
    # Add markers for each site
    for i, site in enumerate(valid_sites):
        color = 'green' if not site.errors else 'red'
        
        popup_html = f"""
        <div style="font-family: Arial, sans-serif; width: 200px;">
            <h4 style="margin: 0 0 10px 0;">🔋 Site {i+1}</h4>
            <p><b>Location:</b> {site.street}</p>
            <p><b>Postcode:</b> {site.postcode}</p>
            <p><b>Chargers:</b> F:{site.fast_chargers} R:{site.rapid_chargers} U:{site.ultra_chargers}</p>
            <p><b>Power:</b> {site.required_kva} kVA</p>
            {f'<p style="color: red;"><b>Error:</b> {site.errors}</p>' if site.errors else ''}
        </div>
        """
        
        folium.Marker(
            location=[site.latitude, site.longitude],
            popup=folium.Popup(popup_html, max_width=250),
            tooltip=f"Site {i+1}: {site.required_kva} kVA",
            icon=folium.Icon(color=color)
        ).add_to(m)
        
        # Add power circle
        folium.Circle(
            location=[site.latitude, site.longitude],
            radius=max(100, min(1000, site.required_kva * 10)),
            popup=f"Site {i+1} Power: {site.required_kva} kVA",
            color=color,
            fillColor=color,
            fillOpacity=0.2
        ).add_to(m)
    
    return m

def display_site_details(site: SiteData):
    """Display site information"""
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📍 Location")
        st.write(f"**Coordinates:** {site.latitude:.6f}, {site.longitude:.6f}")
        if site.easting and site.northing:
            st.write(f"**Grid Ref:** {site.easting:,}, {site.northing:,}")
        st.write(f"**Street:** {site.street}")
        st.write(f"**Postcode:** {site.postcode}")
        st.write(f"**Ward:** {site.ward}")
        st.write(f"**District:** {site.district}")
    
    with col2:
        st.subheader("⚡ Power Requirements")
        st.write(f"**Fast Chargers:** {site.fast_chargers}")
        st.write(f"**Rapid Chargers:** {site.rapid_chargers}")
        st.write(f"**Ultra Chargers:** {site.ultra_chargers}")
        st.write(f"**Total Chargers:** {site.fast_chargers + site.rapid_chargers + site.ultra_chargers}")
        st.markdown(f"**Required kVA:** <span style='color: #1f77b4; font-size: 1.2em; font-weight: bold;'>{site.required_kva}</span>", 
                   unsafe_allow_html=True)
    
    if site.errors:
        st.warning(f"⚠️ Issues: {site.errors}")

def show_summary_stats(sites: List[SiteData]):
    """Show summary statistics"""
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Sites", len(sites))
    with col2:
        total_chargers = sum(s.fast_chargers + s.rapid_chargers + s.ultra_chargers for s in sites)
        st.metric("Total Chargers", total_chargers)
    with col3:
        total_power = sum(s.required_kva for s in sites)
        st.metric("Total Power", f"{total_power:,.0f} kVA")
    with col4:
        errors = len([s for s in sites if s.errors])
        st.metric("Processing Errors", errors)

# --- MAIN APP ---
def main():
    st.set_page_config(
        page_title="EV Charger Site Generator",
        page_icon="🔋",
        layout="wide"
    )
    
    st.title("🔋 EV Charger Site Generator")
    st.markdown("*Generate site sheets for EV charging stations with automated location data*")
    
    # Sidebar configuration
    with st.sidebar:
        st.header("⚙️ Settings")
        fast_kw = st.number_input("Fast Charger Power (kW)", value=22.0, min_value=1.0)
        rapid_kw = st.number_input("Rapid Charger Power (kW)", value=60.0, min_value=1.0)
        ultra_kw = st.number_input("Ultra-Rapid Power (kW)", value=150.0, min_value=1.0)
    
    processor = SiteProcessor()
    
    # Main tabs
    tab1, tab2 = st.tabs(["📍 Single Site", "📁 Batch Processing"])
    
    # --- SINGLE SITE TAB ---
    with tab1:
        st.subheader("Analyze Single Site")
        
        # Use form to prevent premature submission
        with st.form("single_site_form"):
            col1, col2 = st.columns([2, 1])
            
            with col1:
                lat = st.number_input("Latitude", format="%.6f", help="WGS84 decimal degrees")
                lon = st.number_input("Longitude", format="%.6f", help="WGS84 decimal degrees")
            
            with col2:
                fast = st.number_input("Fast Chargers", min_value=0, max_value=20, value=0)
                rapid = st.number_input("Rapid Chargers", min_value=0, max_value=20, value=0)
                ultra = st.number_input("Ultra Chargers", min_value=0, max_value=20, value=0)
            
            # Form submit button
            submitted = st.form_submit_button("🔍 Analyze Site", type="primary")
        
        # Process when form is submitted
        if submitted:
            if lat != 0.0 and lon != 0.0:
                with st.spinner("Processing site..."):
                    site = processor.process_site(lat, lon, fast, rapid, ultra, 
                                                fast_kw, rapid_kw, ultra_kw)
                
                st.success("✅ Site processed successfully!")
                
                # Display results
                display_site_details(site)
                
                # Map
                st.subheader("📍 Site Location")
                try:
                    site_map = create_map(site)
                    st_folium(site_map, width=700, height=400)
                except Exception as e:
                    google_url = f"https://www.google.com/maps?q={lat},{lon}"
                    st.markdown(f"🗺️ [View on Google Maps]({google_url})")
                    st.warning(f"Map issue: {str(e)}")
                
                # Export
                st.subheader("📥 Export Data")
                site_dict = {
                    "latitude": site.latitude, "longitude": site.longitude,
                    "easting": site.easting, "northing": site.northing,
                    "postcode": site.postcode, "ward": site.ward, "district": site.district,
                    "street": site.street, "fast_chargers": site.fast_chargers,
                    "rapid_chargers": site.rapid_chargers, "ultra_chargers": site.ultra_chargers,
                    "required_kva": site.required_kva, "errors": site.errors
                }
                
                col1, col2 = st.columns(2)
                with col1:
                    df = pd.DataFrame([site_dict])
                    st.download_button("📄 Download CSV", df.to_csv(index=False), 
                                     file_name="ev_site.csv", mime="text/csv")
                with col2:
                    st.download_button("📋 Download JSON", json.dumps(site_dict, indent=2),
                                     file_name="ev_site.json", mime="application/json")
            else:
                st.error("❌ Please enter valid coordinates")
    
    # --- BATCH PROCESSING TAB ---
    with tab2:
        st.subheader("Process Multiple Sites")
        
        # Template download
        template_data = {
            "latitude": [51.5074, 53.4808, 55.9533],
            "longitude": [-0.1278, -2.2426, -3.1883],
            "fast": [4, 2, 6],
            "rapid": [2, 4, 2],
            "ultra": [1, 2, 0]
        }
        template_df = pd.DataFrame(template_data)
        
        col1, col2 = st.columns(2)
        with col1:
            st.download_button("📥 Download Template", template_df.to_csv(index=False),
                             file_name="template.csv", mime="text/csv")
        with col2:
            st.write("**Required columns:** latitude, longitude, fast, rapid, ultra")
        
        # File upload
        uploaded_file = st.file_uploader("Upload CSV", type=["csv"])
        
        if uploaded_file:
            try:
                df_input = pd.read_csv(uploaded_file)
                required_cols = {"latitude", "longitude", "fast", "rapid", "ultra"}
                
                if not required_cols.issubset(df_input.columns):
                    missing = required_cols - set(df_input.columns)
                    st.error(f"❌ Missing columns: {', '.join(missing)}")
                else:
                    st.success(f"✅ Loaded {len(df_input)} sites")
                    st.dataframe(df_input.head())
                    
                    # Use form for batch processing
                    with st.form("batch_process_form"):
                        process_batch = st.form_submit_button("🚀 Process All Sites", type="primary")
                    
                    if process_batch:
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        results = []
                        
                        for i, row in df_input.iterrows():
                            status_text.text(f"Processing site {i+1}/{len(df_input)}")
                            progress_bar.progress((i + 1) / len(df_input))
                            
                            site = processor.process_site(
                                row["latitude"], row["longitude"],
                                int(row.get("fast", 0)), int(row.get("rapid", 0)), int(row.get("ultra", 0)),
                                fast_kw, rapid_kw, ultra_kw
                            )
                            
                            results.append({
                                "latitude": site.latitude, "longitude": site.longitude,
                                "easting": site.easting, "northing": site.northing,
                                "postcode": site.postcode, "ward": site.ward, "district": site.district,
                                "street": site.street, "fast_chargers": site.fast_chargers,
                                "rapid_chargers": site.rapid_chargers, "ultra_chargers": site.ultra_chargers,
                                "required_kva": site.required_kva, "errors": site.errors
                            })
                            
                            time.sleep(0.1)  # Rate limiting
                        
                        status_text.text("✅ Processing complete!")
                        
                        # Show results
                        df_results = pd.DataFrame(results)
                        sites_list = [SiteData(**row) for row in results]
                        
                        st.subheader("📊 Results Summary")
                        show_summary_stats(sites_list)
                        
                        st.subheader("📋 Detailed Results")
                        st.dataframe(df_results)
                        
                        # Batch map
                        st.subheader("🗺️ All Sites Map")
                        try:
                            batch_map = create_batch_map(sites_list)
                            if batch_map:
                                st_folium(batch_map, width=700, height=500)
                            else:
                                st.warning("No valid coordinates found for mapping")
                        except Exception as e:
                            st.error(f"Map display error: {str(e)}")
                        
                        # Download results
                        st.download_button("📥 Download Results", df_results.to_csv(index=False),
                                         file_name="batch_results.csv", mime="text/csv")
                        
            except Exception as e:
                st.error(f"❌ Error processing file: {str(e)}")

if __name__ == "__main__":
    main()
