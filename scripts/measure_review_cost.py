"""리뷰어 LLM 호출의 실제 토큰 사용량을 측정한다 (비용 산정용)."""
import json, os, pathlib, sys
import requests

sys.path.insert(0, "/opt/data/ai_cardnews/scripts")
import content_reviewer as cr
import postqueue as q

key = None
for line in pathlib.Path("/opt/data/.env").read_text().splitlines():
    if line.startswith("OPENROUTER_API_KEY="):
        key = line.split("=", 1)[1].strip(); break

slug = "049-batch-inference-continuous-batching"
data = q.load(slug)
user_content = json.dumps({k: v for k, v in data.items() if k != "user_profile"},
                          ensure_ascii=False)[:14000]
print(f"manuscript: {slug} | chars={len(user_content)}")

for model in ("google/gemini-2.5-flash", "deepseek/deepseek-chat",
              "openai/gpt-4o-mini", "qwen/qwen3-32b"):
    body = {"model": model, "messages": [
        {"role": "system", "content": cr.REVIEW_PROMPT},
        {"role": "user", "content": user_content}],
        "temperature": 0.2, "max_tokens": 2000,
        "response_format": {"type": "json_object"}}
    try:
        r = requests.post("https://openrouter.ai/api/v1/chat/completions", json=body,
                          headers={"Authorization": f"Bearer {key}"}, timeout=180)
        j = r.json()
        u = j.get("usage") or {}
        if not u:
            print(f"{model}: HTTP {r.status_code} | {str(j)[:200]}")
            continue
        print(f"{model}: HTTP {r.status_code} | prompt={u.get('prompt_tokens')} "
              f"completion={u.get('completion_tokens')}")
    except Exception as e:
        print(f"{model}: FAIL {type(e).__name__} {str(e)[:120]}")
