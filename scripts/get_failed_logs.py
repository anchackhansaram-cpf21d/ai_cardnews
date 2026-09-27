#!/usr/bin/env python3
"""Get Instagram publish step logs."""
import json, os, urllib.request, zipfile, io

config_path = os.path.expanduser("~/.config/gh/hosts.yml")
token = None
with open(config_path) as f:
    for line in f:
        if 'oauth_token' in line:
            token = line.split(':')[1].strip()
            break

# Get logs for the failed run
req = urllib.request.Request(
    'https://api.github.com/repos/anchackhansaram-cpf21d/ai_cardnews/actions/runs/35047532203/logs',
    headers={'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'}
)
resp = urllib.request.urlopen(req)
zip_data = resp.read()

# Extract and find the publish step log
z = zipfile.ZipFile(io.BytesIO(zip_data))
for name in z.namelist():
    if '인스타그램' in name or 'insta' in name.lower() or 'publish' in name.lower():
        content = z.read(name).decode('utf-8', errors='replace')
        print(f"=== {name} ===")
        print(content[-2000:])  # Last 2000 chars of the log
        print("===================")