#!/usr/bin/env python3
"""Check latest workflow run - no sleep."""
import json, os, urllib.request

config_path = os.path.expanduser("~/.config/gh/hosts.yml")
token = None
with open(config_path) as f:
    for line in f:
        if 'oauth_token' in line:
            token = line.split(':')[1].strip()
            break

req = urllib.request.Request(
    'https://api.github.com/repos/anchackhansaram-cpf21d/ai_cardnews/actions/runs?per_page=3',
    headers={'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'}
)
resp = urllib.request.urlopen(req)
data = json.loads(resp.read())

runs = data.get('workflow_runs', [])
for r in runs:
    print(f"id={r['id']} | name={r['display_title'][:50]} | status={r['status']} | conclusion={r.get('conclusion','-')} | created={r['created_at'][:19]}")