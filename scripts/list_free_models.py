import json
d = json.load(open('/tmp/or_models.json'))['data']
free = []
for m in d:
    p = m.get('pricing') or {}
    try:
        pin = float(p.get('prompt', '1')); pout = float(p.get('completion', '1'))
    except (TypeError, ValueError):
        continue
    if pin == 0 and pout == 0:
        free.append(m)

print(f"무료 모델 {len(free)}개\n")
# NVIDIA / 주요 계열 우선
def score(m):
    i = m['id'].lower()
    return (0 if 'nvidia' in i or 'nemotron' in i else 1, len(i))
for m in sorted(free, key=score)[:40]:
    ctx = m.get('context_length')
    i = m['id']
    print(f"{i:60s} ctx={ctx}")
