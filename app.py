import requests

# Replace with your actual Google API key
GOOGLE_API_KEY = "YOUR_API_KEY_HERE"

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
        print("Google API error:", e)
        return "Unknown"

# Example coordinates (London)
latitude = 51.5074
longitude = -0.1278

street_name = get_street_name_google(latitude, longitude, GOOGLE_API_KEY)
print("Street Name:", street_name)
