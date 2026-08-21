import json
from collections import Counter

with open("directed_roads.geojson", 'r') as f:
    geojson = json.load(f)

# Count how many of each feature_type exist
types = Counter(f['properties'].get('feature_type') for f in geojson['features'])
print("Feature types found:", dict(types))

# If there's a type we missed, print its properties
for f in geojson['features']:
    if f['properties'].get('feature_type') not in ['node', 'edge']:
        print("Unknown feature:", f['properties'])