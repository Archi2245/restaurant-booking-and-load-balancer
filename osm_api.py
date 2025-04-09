import requests

def search_restaurants(city):
    query = f"""
    [out:json];
    area["name"="{city}"]->.searchArea;
    (
      node["amenity"="restaurant"](area.searchArea);
      way["amenity"="restaurant"](area.searchArea);
      relation["amenity"="restaurant"](area.searchArea);
    );
    out center 20;
    """
    url = "https://overpass-api.de/api/interpreter"
    results = []
    
    try:
        response = requests.get(url, params={'data': query}, timeout=10)
        response.raise_for_status()  # Raise an exception for bad responses
        data = response.json()
        
        for element in data.get('elements', []):
            name = element.get('tags', {}).get('name', 'Unnamed Restaurant')
            lat = element.get('lat') or element.get('center', {}).get('lat')
            lon = element.get('lon') or element.get('center', {}).get('lon')
            
            if name and lat and lon:
                results.append({
                    'name': name,
                    'lat': lat,
                    'lon': lon
                })
    except (requests.RequestException, ValueError) as e:
        print(f"Error fetching restaurants from OSM: {e}")
        # Return empty list on error
    
    return results