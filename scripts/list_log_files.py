#!/usr/bin/env python3
"""List all log files and get the actual Instagram publish error."""
import json, os, urllib.request, zipfile, io

config_path = os.path.expanduser("~/.config/gh/hosts.yml")
token = None
with open(config_path) as f:
    for line in f:
        if 'oauth_token' in line:
            token = line.split(':')[1].strip()
            break

req = urllib.request.Request(
    'https://api.github.com/repos/anchackhansaram-cpf21d/ai_cardnews/actions/runs/35047532203/logs',
    headers={'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'}
)
resp = urllib.request.urlopen(req)
z = zipfile.ZipFile(io.BytesIO(resp.read()))

# List ALL files
print("=== All log files ===")
for name in z.namelist():
    print(name)

# Find files related to the failed step
print("\n=== Files with 'insta' or '발행' or 'publish' in name ===")
for name in z.namelist():
    if any(k in name.lower() for k in ['insta', '발행', 'publish', 'instagram']):
        content = z.read(name).decode('utf-8', errors='replace')
        print(f"\n--- {name} ---")
        # Show the last part where error would be
        lines = content.split('\n')
        for line in lines[-50:]:
            print(line)