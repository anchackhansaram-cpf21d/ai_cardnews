#!/usr/bin/env python3
"""Check latest workflow run status via GitHub API."""
import json
import os
import urllib.request
import time

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

# Wait 2 minutes
print("Waiting 120 seconds for workflow to start...")
time.sleep(120)

# List runs for the workflow
req = urllib.request.Request(
    'https://api.github.com/repos/anchackhansaram-cpf21d/ai_cardnews/actions/runs?per_page=5',
    headers={'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'}
)
resp = urllib.request.urlopen(req)
data = json.loads(resp.read())

runs = data.get('workflow_runs', [])
if not runs:
    print("No runs found")
    exit(1)

print(f"Latest {len(runs)} runs:")
for r in runs:
    print(f"  id={r['id']}, name={r['display_title'][:40]}, status={r['status']}, conclusion={r.get('conclusion','N/A')}, branch={r['head_branch']}")

latest = runs[0]
status = latest['status']
conclusion = latest.get('conclusion')

print(f"\nLatest run: id={latest['id']}, status={status}, conclusion={conclusion}")

if status == 'completed':
    if conclusion == 'success':
        print("RESULT: SUCCESS")
    elif conclusion == 'failure':
        print("RESULT: FAILURE")
        # Get logs URL
        print(f"Logs URL: {latest.get('logs_url', 'N/A')}")
    else:
        print(f"RESULT: {conclusion}")
else:
    print(f"Still running (status={status}), will need to check again later")

# Save run details
with open('/opt/data/ai_cardnews/last_run_status.json', 'w') as f:
    json.dump(runs[0] if runs else {}, f, indent=2)

print("Status saved to last_run_status.json")