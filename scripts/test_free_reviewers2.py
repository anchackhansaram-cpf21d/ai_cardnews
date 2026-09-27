"""보수 리뷰어 후보 2차 — json_object 모드 + 재시도."""
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
    "poolside/laguna-s-2.1:free",
    "thinkingmachines/inkling:free",
    "cohere/north-mini-code:free",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    "openrouter/free",
]

SYS = cr.REVIEW_PROMPT + "\n\n반드시 JSON 객체 하나만 출력하라. 사고 과정·설명·마크다운 금지."
data = q.load("049-batch-inference-continuous-batching")
user_content = json.dumps({k: v for k, v in data.items() if k != "user_profile"},
                          ensure_ascii=False)[:14000]

for model in CANDIDATES:
    for attempt in (1, 2):
        body = {"model": model, "messages": [
            {"role": "system", "content": SYS},
            {"role": "user", "content": user_content}],
            "temperature": 0.2, "max_tokens": 3000,
            "response_format": {"type": "json_object"}}
        t0 = time.time()
        try:
            r = requests.post("https://openrouter.ai/api/v1/chat/completions", json=body,
                              headers={"Authorization": f"Bearer {key}"}, timeout=240)
            j = r.json()
            el = time.time() - t0
            if r.status_code != 200:
                err = str(j.get('error', {}).get('message', j))[:90]
                print(f"✗ {model} [{attempt}] HTTP {r.status_code}: {err}")
                time.sleep(6); continue
            msg = (j["choices"][0]["message"].get("content") or "")
            u = j.get("usage") or {}
            parsed = cr._loads_lenient(msg)
            ok = isinstance(parsed, dict) and "verdict" in parsed
            print(f"{'✓' if ok else '△'} {model} [{attempt}] {el:.0f}s out={u.get('completion_tokens')}tok "
                  f"JSON={'OK' if ok else 'FAIL'} issues={len(parsed.get('issues', [])) if ok else '-'}")
            if ok:
                for i in (parsed.get("issues") or [])[:2]:
                    print(f"     - {str(i.get('detail'))[:100]}")
            else:
                print("     raw:", msg[:150].replace("\n", " "))
            break
        except Exception as e:
            print(f"✗ {model} [{attempt}] {type(e).__name__} {str(e)[:100]}")
            time.sleep(6)
    time.sleep(2)
