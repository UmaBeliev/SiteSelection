import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import json

# Page configuration
st.set_page_config(
    page_title="TomTom EV Charging Stations",
    page_icon="⚡",
    layout="wide"
)

# App title and description
st.title("⚡ TomTom EV Charging Stations Availability")
st.markdown("""
This app uses the TomTom EV Search API and EV Charging Stations Availability API to find nearby charging stations 
and check their real-time availability status.
""")

# Sidebar for API configuration
st.sidebar.header("🔧 Configuration")

# API Key input
api_key = st.sidebar.text_input(
    "TomTom API Key", 
    type="password",
    help="Get your API key from https://developer.tomtom.com/"
)

if not api_key:
    st.sidebar.warning("Please enter your TomTom API key to continue")
    st.stop()

# Location input
st.sidebar.header("📍 Location Settings")
col1, col2 = st.sidebar.columns(2)
with col1:
    latitude = st.number_input("Latitude", value=52.36, format="%.6f")
with col2:
    longitude = st.number_input("Longitude", value=4.89, format="%.6f")

radius = st.sidebar.slider("Search Radius (meters)", 100, 10000, 2000, 100)

# Filter options
st.sidebar.header("🔍 Filters")
status_filter = st.sidebar.multiselect(
    "Availability Status",
    ["Available", "Occupied", "Unknown", "OutOfService"],
    default=["Available", "Unknown"]
)

connector_types = st.sidebar.multiselect(
    "Connector Types",
    [
        "IEC62196Type2Outlet",
        "IEC62196Type2CableAttached", 
        "CHAdeMO",
        "IEC62196Type1Outlet",
        "Tesla"
    ],
    default=["IEC62196Type2Outlet", "CHAdeMO"]
)

min_power = st.sidebar.number_input("Min Power (kW)", min_value=0.0, value=22.0, step=1.0)
max_power = st.sidebar.number_input("Max Power (kW)", min_value=0.0, value=150.0, step=1.0)

limit = st.sidebar.slider("Max Results", 1, 100, 20)

# Functions for API calls
@st.cache_data(ttl=180)  # Cache for 3 minutes
def search_ev_stations(api_key, lat, lon, radius, status_filter, connector_types, min_power, max_power, limit):
    """Search for EV charging stations using TomTom EV Search API"""
    base_url = "https://api.tomtom.com/search/2/evsearch"
    
    params = {
        "key": api_key,
        "lat": lat,
        "lon": lon,
        "radius": radius,
        "limit": limit,
        "view": "Unified"
    }
    
    # Add optional filters
    if status_filter:
        params["status"] = ",".join(status_filter)
    
    if connector_types:
        params["connector"] = ",".join(connector_types)
    
    if min_power > 0:
        params["minPowerKW"] = min_power
    
    if max_power > 0:
        params["maxPowerKW"] = max_power
    
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error searching EV stations: {e}")
        return None

@st.cache_data(ttl=60)  # Cache for 1 minute for real-time data
def get_charging_availability(api_key, charging_availability_id, connector_set=None, min_power_kw=None, max_power_kw=None):
    """Get real-time availability for a specific charging station"""
    base_url = "https://api.tomtom.com/search/2/chargingAvailability.json"
    
    params = {
        "key": api_key,
        "chargingAvailability": charging_availability_id
    }
    
    if connector_set:
        params["connectorSet"] = connector_set
    if min_power_kw:
        params["minPowerKW"] = min_power_kw
    if max_power_kw:
        params["maxPowerKW"] = max_power_kw
    
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error getting availability: {e}")
        return None

def create_map(stations_data, lat, lon):
    """Create an interactive map with charging stations"""
    if not stations_data or "results" not in stations_data:
        return None
    
    # Prepare data for map
    map_data = []
    for result in stations_data["results"]:
        poi = result.get("poi", {})
        position = result.get("position", {})
        
        # Get EV details
        ev_details = result.get("chargingPark", {}).get("chargingStations", [])
        total_points = sum(len(station.get("chargingPoints", [])) for station in ev_details)
        
        # Get available connectors
        connectors = []
        for station in ev_details:
            for point in station.get("chargingPoints", []):
                for connector in point.get("connectors", []):
                    connectors.append(connector.get("connectorType", "Unknown"))
        
        map_data.append({
            "name": poi.get("name", "Unknown Station"),
            "lat": position.get("lat", 0),
            "lon": position.get("lon", 0),
            "address": result.get("address", {}).get("freeformAddress", ""),
            "total_points": total_points,
            "connectors": ", ".join(set(connectors)),
            "id": result.get("id", "")
        })
    
    if not map_data:
        return None
    
    df = pd.DataFrame(map_data)
    
    # Create map
    fig = px.scatter_mapbox(
        df,
        lat="lat",
        lon="lon",
        hover_name="name",
        hover_data=["address", "total_points", "connectors"],
        zoom=12,
        height=500,
        size_max=15,
        size="total_points"
    )
    
    # Add center point
    fig.add_trace(
        go.Scattermapbox(
            lat=[lat],
            lon=[lon],
            mode="markers",
            marker=go.scattermapbox.Marker(size=14, color="red"),
            name="Search Center",
            text="Your Location"
        )
    )
    
    fig.update_layout(
        mapbox_style="open-street-map",
        mapbox=dict(center=go.layout.mapbox.Center(lat=lat, lon=lon)),
        showlegend=True,
        margin={"r": 0, "t": 0, "l": 0, "b": 0}
    )
    
    return fig

def create_availability_chart(availability_data):
    """Create a chart showing availability statistics"""
    if not availability_data or "connectors" not in availability_data:
        return None
    
    chart_data = []
    for connector in availability_data["connectors"]:
        connector_type = connector.get("type", "Unknown")
        current = connector.get("availability", {}).get("current", {})
        
        chart_data.append({
            "Connector Type": connector_type,
            "Available": current.get("available", 0),
            "Occupied": current.get("occupied", 0),
            "Reserved": current.get("reserved", 0),
            "Unknown": current.get("unknown", 0),
            "Out of Service": current.get("outOfService", 0)
        })
    
    if not chart_data:
        return None
    
    df = pd.DataFrame(chart_data)
    
    # Create stacked bar chart
    fig = px.bar(
        df.melt(id_vars=["Connector Type"], var_name="Status", value_name="Count"),
        x="Connector Type",
        y="Count",
        color="Status",
        title="Charging Point Availability by Connector Type",
        color_discrete_map={
            "Available": "#28a745",
            "Occupied": "#dc3545", 
            "Reserved": "#ffc107",
            "Unknown": "#6c757d",
            "Out of Service": "#343a40"
        }
    )
    
    fig.update_layout(height=400)
    return fig

# Main app logic
if st.button("🔍 Search EV Charging Stations", type="primary"):
    with st.spinner("Searching for EV charging stations..."):
        # Search for stations
        stations_data = search_ev_stations(
            api_key, latitude, longitude, radius, 
            status_filter, connector_types, min_power, max_power, limit
        )
        
        if stations_data and "results" in stations_data:
            st.success(f"Found {len(stations_data['results'])} charging stations")
            
            # Create tabs for different views
            tab1, tab2, tab3 = st.tabs(["🗺️ Map View", "📊 Station Details", "📈 Real-time Availability"])
            
            with tab1:
                # Show map
                map_fig = create_map(stations_data, latitude, longitude)
                if map_fig:
                    st.plotly_chart(map_fig, use_container_width=True)
                else:
                    st.warning("No stations found to display on map")
            
            with tab2:
                # Show detailed results
                st.subheader("Charging Stations Found")
                
                for i, result in enumerate(stations_data["results"]):
                    with st.expander(f"🔌 {result.get('poi', {}).get('name', f'Station {i+1}')}"):
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.write("**Address:**", result.get("address", {}).get("freeformAddress", "N/A"))
                            st.write("**Distance:**", f"{result.get('dist', 0):.0f} meters")
                            
                            # Position info
                            pos = result.get("position", {})
                            st.write("**Coordinates:**", f"{pos.get('lat', 0):.6f}, {pos.get('lon', 0):.6f}")
                        
                        with col2:
                            # EV specific details
                            charging_park = result.get("chargingPark", {})
                            stations = charging_park.get("chargingStations", [])
                            
                            total_points = 0
                            all_connectors = set()
                            
                            for station in stations:
                                points = station.get("chargingPoints", [])
                                total_points += len(points)
                                
                                for point in points:
                                    for connector in point.get("connectors", []):
                                        all_connectors.add(connector.get("connectorType", "Unknown"))
                            
                            st.write("**Total Charging Points:**", total_points)
                            st.write("**Connector Types:**", ", ".join(all_connectors))
                            
                            # Check if availability data is available
                            availability_id = charging_park.get("connectors", [{}])[0].get("chargingAvailability")
                            if availability_id:
                                st.write("**Availability ID:**", availability_id)
                                
                                if st.button(f"Check Real-time Availability", key=f"check_{i}"):
                                    availability_data = get_charging_availability(api_key, availability_id)
                                    if availability_data:
                                        st.json(availability_data)
            
            with tab3:
                # Real-time availability for all stations
                st.subheader("Real-time Availability Check")
                
                # Get availability for stations that have availability IDs
                availability_stats = {"total_available": 0, "total_occupied": 0, "total_unknown": 0}
                
                for result in stations_data["results"]:
                    charging_park = result.get("chargingPark", {})
                    connectors = charging_park.get("connectors", [])
                    
                    for connector in connectors:
                        availability_id = connector.get("chargingAvailability")
                        if availability_id:
                            availability_data = get_charging_availability(api_key, availability_id)
                            if availability_data:
                                for conn in availability_data.get("connectors", []):
                                    current = conn.get("availability", {}).get("current", {})
                                    availability_stats["total_available"] += current.get("available", 0)
                                    availability_stats["total_occupied"] += current.get("occupied", 0)
                                    availability_stats["total_unknown"] += current.get("unknown", 0)
                
                # Show summary statistics
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Available Charging Points", availability_stats["total_available"])
                with col2:
                    st.metric("Occupied Charging Points", availability_stats["total_occupied"])
                with col3:
                    st.metric("Unknown Status", availability_stats["total_unknown"])
                
                # Detailed availability for individual stations
                st.subheader("Individual Station Availability")
                
                station_selector = st.selectbox(
                    "Select a station to check availability:",
                    options=range(len(stations_data["results"])),
                    format_func=lambda x: stations_data["results"][x].get("poi", {}).get("name", f"Station {x+1}")
                )
                
                selected_station = stations_data["results"][station_selector]
                charging_park = selected_station.get("chargingPark", {})
                connectors = charging_park.get("connectors", [])
                
                for connector in connectors:
                    availability_id = connector.get("chargingAvailability")
                    if availability_id:
                        availability_data = get_charging_availability(api_key, availability_id)
                        if availability_data:
                            chart = create_availability_chart(availability_data)
                            if chart:
                                st.plotly_chart(chart, use_container_width=True)
                            
                            # Show detailed breakdown
                            st.subheader("Detailed Availability Data")
                            st.json(availability_data)
                        break
        
        else:
            st.warning("No charging stations found. Try adjusting your search parameters.")

# Footer with information
st.markdown("---")
st.markdown("""
**About this app:**
- Uses TomTom EV Search API to find nearby charging stations
- Uses TomTom EV Charging Stations Availability API for real-time status
- Data is refreshed every 3 minutes for availability information
- Get your API key at: https://developer.tomtom.com/

**Supported Connector Types:**
- IEC62196Type2Outlet (Type 2)
- IEC62196Type2CableAttached (Type 2 with cable)
- CHAdeMO
- IEC62196Type1Outlet (Type 1)
- Tesla (Supercharger)
""")
