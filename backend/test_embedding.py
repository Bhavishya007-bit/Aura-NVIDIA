import requests

embedding = [0.01] * 1024

response = requests.put(
    "http://127.0.0.1:8000/chunks/1/embedding",
    json={
        "embedding": embedding
    }
)

print("Status:", response.status_code)
print("Response:", response.json())