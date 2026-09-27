#!/usr/bin/env python3
"""Trigger the Instagram publish workflow via GitHub API."""
import json
import os
import urllib.request

# Read token from gh config
config_path = os.path.expanduser("~/.config/gh/hosts.yml")
token = None
with open(config_path) as f:
    for line in f:
        if 'oauth_token' in line:
            token = line.split(':')[1].strip()
            break

if not token:
    print("ERROR: No token found")
    exit(1)

# First, list workflows to find the correct workflow ID
req = urllib.request.Request(
    'https://api.github.com/repos/anchackhansaram-cpf21d/ai_cardnews/actions/workflows',
    headers={'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'}
)
resp = urllib.request.urlopen(req)
data = json.loads(resp.read())

wf = None
for w in data.get('workflows', []):
    wname = w['name']
    print(f"  id={w['id']}, name={wname}, path={w['path']}")
    if '인스타' in wname or '카드' in wname or '카드뉴스' in wname or '인스타그램' in wname:
        wf = w
        print(f"  -> MATCHED: id={w['id']}")
        break

if not wf:
    print("ERROR: No matching workflow found")
    exit(1)

# Trigger dispatch
wf_id = wf['id']
req2 = urllib.request.Request(
    f'https://api.github.com/repos/anchackhansaram-cpf21d/ai_cardnews/actions/workflows/{wf_id}/dispatches',
    data=json.dumps({'ref': 'main'}).encode(),
    headers={'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'},
    method='POST'
)
resp2 = urllib.request.urlopen(req2)
print(f'Dispatch status: {resp2.status}')
print(f'Dispatch response: {resp2.read().decode()}')
print('SUCCESS: Workflow triggered')