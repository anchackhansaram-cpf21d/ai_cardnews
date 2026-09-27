"""보수 리뷰어 후보(무료 모델)가 실제로 쓸만한 리뷰를 하는지 검증."""
import json, pathlib, sys, time
import requests

sys.path.insert(0, "/opt/data/ai_cardnews/scripts")
import content_reviewer as cr
import postqueue as q

key = None
for line in pathlib.Path("/opt/data/.env").read_text().splitlines():
    if line.startswith("OPENROUTER_API_KEY="):
        key = line.split("=", 1)[1].strip(); break

CANDIDATES = [
    "nvidia/nemotron-3-super-120b-a12b:free",
    "nvidia/nemotron-3.5-lightning:free",
    "qwen/qwen3.8-27b:free",
    "google/gemma-4-31b-it:free",
]

data = q.load("049-batch-inference-continuous-batching")
user_content = json.dumps({k: v for k, v in data.items() if k != "user_profile"},
                          ensure_ascii=False)[:14000]

for model in CANDIDATES:
    body = {"model": model, "messages": [
        {"role": "system", "content": cr.REVIEW_PROMPT},
        {"role": "user", "content": user_content}],
        "temperature": 0.2, "max_tokens": 2000}
    t0 = time.time()
    try:
        r = requests.post("https://openrouter.ai/api/v1/chat/completions", json=body,
                          headers={"Authorization": f"Bearer {key}"}, timeout=240)
        j = r.json()
        el = time.time() - t0
        if r.status_code != 200:
            print(f"✗ {model} HTTP {r.status_code}: {str(j)[:180]}"); continue
        msg = j["choices"][0]["message"].get("content") or ""
        u = j.get("usage") or {}
        parsed = cr._loads_lenient(msg)
        n_iss = len(parsed.get("issues", [])) if isinstance(parsed, dict) else None
        print(f"✓ {model}")
        print(f"   {el:.1f}s | out={u.get('completion_tokens')}tok | JSON={'OK' if parsed else 'FAIL'}"
              f" | issues={n_iss} | verdict={parsed.get('verdict') if isinstance(parsed,dict) else '-'}")
        if isinstance(parsed, dict):
            for i in (parsed.get("issues") or [])[:2]:
                print(f"     - {str(i.get('detail'))[:110]}")
        else:
            print("     raw:", msg[:200].replace("\n", " "))
    except Exception as e:
        print(f"✗ {model} FAIL {type(e).__name__} {str(e)[:120]}")
    time.sleep(2)
