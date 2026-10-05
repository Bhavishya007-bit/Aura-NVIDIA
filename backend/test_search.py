import requests

embedding = [0.01] * 1024

response = requests.post(
    "http://127.0.0.1:8000/search",
    json={
        "embedding": embedding,
        "top_k": 5
    }
)

print("Status:", response.status_code)
print("Response:", response.json())