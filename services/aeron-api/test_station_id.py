import urllib.request
import json
import os

env = {}
with open('.env', 'r') as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith('#'): continue
        if '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip().strip('"\'')

cookie = env.get('AERON_SESSION_COOKIE', '')
station_id = env.get('AERON_STATION_ID', '')

url = f'https://live3.aeronsystems.com/api/stations/{station_id}'
print(f'Fetching {url}')
req = urllib.request.Request(url, headers={'Cookie': cookie})
try:
    with urllib.request.urlopen(req, timeout=10.0) as res:
        data = json.loads(res.read().decode())
        print(json.dumps(data, indent=2))
except Exception as e:
    print('Error:', e)
