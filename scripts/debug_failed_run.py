#!/usr/bin/env python3
"""Get workflow run logs for a failed run."""
import json, os, urllib.request

config_path = os.path.expanduser("~/.config/gh/hosts.yml")
token = None
with open(config_path) as f:
    for line in f:
        if 'oauth_token' in line:
            token = line.split(':')[1].strip()
            break

# Get the failed run details
req = urllib.request.Request(
    'https://api.github.com/repos/anchackhansaram-cpf21d/ai_cardnews/actions/runs/35047532203',
    headers={'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'}
)
resp = urllib.request.urlopen(req)
run = json.loads(resp.read())

print(f"Status: {run['status']}, Conclusion: {run.get('conclusion')}")
print(f"Head branch: {run['head_branch']}")
print(f"Event: {run['event']}")
print(f"Jobs URL: {run['jobs_url']}")

# Get jobs
req2 = urllib.request.Request(run['jobs_url'],
    headers={'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'})
resp2 = urllib.request.urlopen(req2)
jobs = json.loads(resp2.read())

for job in jobs.get('jobs', []):
    print(f"\nJob: {job['name']} | status={job['status']} | conclusion={job.get('conclusion')}")
    for step in job.get('steps', []):
        status_icon = '✅' if step.get('conclusion') == 'success' else ('❌' if step.get('conclusion') == 'failure' else '⏳')
        print(f"  {status_icon} {step['name']} ({step['status']} / {step.get('conclusion','-')})")
        if step.get('conclusion') == 'failure':
            # Get logs for this step
            if 'logs_url' in step:
                logs_url = step['logs_url']
                print(f"    Logs: {logs_url}")