import httpx
import json
import config

url = "https://jsearch.p.rapidapi.com/search"
headers = {
    "X-RapidAPI-Key": config.RAPIDAPI_KEY,
    "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
}
params = {
    "query": "Engineering Manager Google",
    "page": "1",
    "num_pages": "1",
}

resp = httpx.get(url, headers=headers, params=params, timeout=15)
print(f"Status: {resp.status_code}")
data = resp.json()
print(f"Jobs found: {len(data.get('data', []))}")
if data.get('data'):
    job = data['data'][0]
    print(f"First result: {job.get('job_title')} @ {job.get('employer_name')}")
else:
    print(f"Response: {json.dumps(data, indent=2)[:500]}")
