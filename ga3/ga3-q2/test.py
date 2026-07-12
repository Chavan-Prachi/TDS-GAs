import requests

# REPLACE THIS with your actual Render URL (e.g., https://my-app.onrender.com)
url = "https://ga3-q2-lnne.onrender.com/answer-image"

# A tiny 1x1 pixel image in base64 just to test the connection
dummy_image_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="

payload = {
    "image_base64": dummy_image_base64,
    "question": "What is in this image?"
}

print("Sending request (this might take 30-50 seconds if the app is sleeping)...")
response = requests.post(url, json=payload)

print(f"Status Code: {response.status_code}")
print(f"Response JSON: {response.json()}")
