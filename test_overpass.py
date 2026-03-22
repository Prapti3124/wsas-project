import requests
def print_hospitals():
    try:
        url = "http://overpass-api.de/api/interpreter"
        query = """
        [out:json][timeout:10];
        nwr["amenity"="hospital"](around:5000,19.23,73.13);
        out center 4;
        """
        response = requests.post(url, data=query, timeout=10)
        data = response.json()
        print(f"Elements found: {len(data.get('elements', []))}")
        for el in data.get("elements", []):
            tags = el.get("tags", {})
            name = tags.get("name")
            print(name)
    except Exception as e:
        print(f"Error: {e}")

print_hospitals()
