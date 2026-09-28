"""렌더된 카드 이미지를 비전 모델로 검증 — 수식/빈공간/라벨 확인."""
import base64, json, os, pathlib, sys, urllib.request

KEY = None
for line in pathlib.Path("/opt/data/.env").read_text().splitlines():
    if line.startswith("OPENROUTER_API_KEY"):
        KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
MODEL = "google/gemini-2.5-flash"

PROMPT = (
    "이건 인스타 카드뉴스 한 장이다. 다음만 간결히 답해라.\n"
    "1) 수식이 있으면 제대로 렌더됐나, 아니면 $...$ 원문이 보이나?\n"
    "2) 그림/차트가 있으면 라벨(축·항목명)이 보이나? 빈 공간이 과한가?\n"
    "3) 글자가 너무 많아 보이나?\n"
    "답변은 한국어 3줄 이내."
)

slug = sys.argv[1] if len(sys.argv) > 1 else "050-activation-functions"
cards = sys.argv[2:] or ["02", "04", "08"]

for n in cards:
    p = pathlib.Path(f"/opt/data/ai_cardnews/out/{slug}/{n}.jpg")
    if not p.exists():
        print(f"[{n}] 없음"); continue
    b64 = base64.b64encode(p.read_bytes()).decode()
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}],
        "max_tokens": 400,
    }).encode()
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions", data=body,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            j = json.load(r)
        print(f"===== {n}번 카드 =====")
        print(j["choices"][0]["message"]["content"].strip())
    except Exception as e:
        print(f"[{n}] 실패: {e}")
    print()
