import requests
import json

URL = "http://localhost:8006/chat"
PAYLOAD = {
    "message": "Tell me about rice fertilizer",
    "language": "en"
}

try:
    response = requests.post(URL, json=PAYLOAD)
    print(f"Status Code: {response.status_code}")
    print("Response JSON:")
    print(json.dumps(response.json(), indent=2))
except Exception as e:
    print(f"Error: {e}")
