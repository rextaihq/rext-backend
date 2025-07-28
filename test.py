import requests

res = requests.post(
    "http://127.0.0.1:2024/api/workflow/configure",
    headers={
      "Content-Type": "application/json"
    },
    json={
        "category": "categories",
        "country": "country_code",
        "language": "language_code",
    }
)

print(res)