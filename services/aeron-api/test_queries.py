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

urls = [
    f'https://live3.aeronsystems.com/api/stations/{station_id}/readings?mode=latest',
    f'https://live3.aeronsystems.com/api/stations/{station_id}/readings?limit=1',
    f'https://live3.aeronsystems.com/api/stations/{station_id}/readings?mode=realtime',
    f'https://live3.aeronsystems.com/api/stations/{station_id}/data?limit=1'
]

for url in urls:
    print(f'Fetching {url}')
    req = urllib.request.Request(url, headers={'Cookie': cookie})
    try:
        with urllib.request.urlopen(req, timeout=5.0) as res:
            data = json.loads(res.read().decode())
            if isinstance(data, list):
                if len(data) > 0:
                    print('List latest:', data[0].get('recordedAt'))
                else:
                    print('Empty list')
            else:
                print('Dict:', data.get('recordedAt', 'No recordedAt'))
    except urllib.error.HTTPError as e:
        print('HTTPError:', e.code)
    except Exception as e:
        print('Error:', e)
