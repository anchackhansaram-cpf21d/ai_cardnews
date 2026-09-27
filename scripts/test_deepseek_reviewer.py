"""보수 리뷰어: deepseek 후보 검증 (JSON 준수 + 리뷰 품질)."""
import json, pathlib, sys, time
import requests

sys.path.insert(0, "/opt/data/ai_cardnews/scripts")
import content_reviewer as cr
import postqueue as q

key = None
for line in pathlib.Path("/opt/data/.env").read_text().splitlines():
    if line.startswith("OPENROUTER_API_KEY="):
        key = line.split("=", 1)[1].strip(); break

CONSERVATIVE_PROMPT = """당신은 한국어 AI 교육 카드뉴스의 **보수적 게이트키퍼 리뷰어**입니다.
역할: 관대하게 넘기지 말고, 발행을 막아야 할 결함을 찾아내는 것이 임무입니다.

검수 기준(엄격):
1. 사실 정확성 — 논문/연도/버전/모델명 등 출처 표기가 틀렸거나 검증 불가면 지적
2. 과장·단정 — 근거 없는 최상급 표현("무조건", "100%", "역대 최고") 지적
3. 설명 충분성 — 그림만 있고 설명이 부족한 카드
4. 커버 후킹 — 3줄 도발·단정형인지
5. 언어 — 한국어만 (일본어/중국어 금지)
6. 시각화 카드에 data/visual 페이로드가 있는지

출력: JSON 객체 하나만. 사고 과정·설명·마크다운 금지.
{"verdict":"pass|fix|block","summary":"한 줄","issues":[{"card":<번호>,"type":"<종류>","severity":"high|medium|low","detail":"<근거 포함 설명>"}]}
문제 없으면 issues를 빈 배열로."""

CANDIDATES = ["deepseek/deepseek-v4-flash", "deepseek/deepseek-chat", "deepseek/deepseek-v4-pro"]
data = q.load("049-batch-inference-continuous-batching")
user_content = json.dumps({k: v for k, v in data.items() if k != "user_profile"},
                          ensure_ascii=False)[:14000]

for model in CANDIDATES:
    body = {"model": model, "messages": [
        {"role": "system", "content": CONSERVATIVE_PROMPT},
        {"role": "user", "content": user_content}],
        "temperature": 0.1, "max_tokens": 3000,
        "response_format": {"type": "json_object"}}
    t0 = time.time()
    try:
        r = requests.post("https://openrouter.ai/api/v1/chat/completions", json=body,
                          headers={"Authorization": f"Bearer {key}"}, timeout=240)
        j = r.json(); el = time.time() - t0
        if r.status_code != 200:
            print(f"✗ {model} HTTP {r.status_code}: {str(j.get('error', j))[:120]}"); continue
        msg = j["choices"][0]["message"].get("content") or ""
        u = j.get("usage") or {}
        parsed = cr._loads_lenient(msg)
        ok = isinstance(parsed, dict) and "verdict" in parsed
        print(f"{'✓' if ok else '△'} {model} {el:.0f}s out={u.get('completion_tokens')}tok JSON={'OK' if ok else 'FAIL'}")
        if ok:
            print(f"   verdict={parsed.get('verdict')} | summary={str(parsed.get('summary'))[:90]}")
            for i in (parsed.get("issues") or [])[:3]:
                print(f"   - [{i.get('severity')}] {i.get('card')}번 {str(i.get('detail'))[:110]}")
        else:
            print("   raw:", msg[:180].replace("\n", " "))
    except Exception as e:
        print(f"✗ {model} {type(e).__name__} {str(e)[:110]}")
    time.sleep(2)
