#!/usr/bin/env python3
"""Check latest run's Instagram publish error."""
import json, os, urllib.request, zipfile, io

config_path = os.path.expanduser("~/.config/gh/hosts.yml")
token = None
with open(config_path) as f:
    for line in f:
        if 'oauth_token' in line:
            token = line.split(':')[1].strip()
            break

req = urllib.request.Request(
    'https://api.github.com/repos/anchackhansaram-cpf21d/ai_cardnews/actions/runs/35173866727/logs',
    headers={'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'}
)
resp = urllib.request.urlopen(req)
z = zipfile.ZipFile(io.BytesIO(resp.read()))

content = z.read('0_publish.txt').decode('utf-8', errors='replace')
lines = content.split('\n')
# Find error lines
for line in lines:
    if 'error' in line.lower() or '실패' in line or 'rate limit' in line.lower() or '403' in line or '400' in line:
        print(line)
print("\n--- Last 10 lines ---")
for line in lines[-10:]:
    print(line)