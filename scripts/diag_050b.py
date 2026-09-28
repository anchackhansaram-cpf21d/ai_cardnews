import json, pathlib, re, sys
sys.path.insert(0, "/opt/data/ai_cardnews/scripts")
import diagrams

d = json.loads(pathlib.Path("/opt/data/ai_cardnews/content/queue/050-activation-functions.json")
               .read_text(encoding="utf-8"))

for i in (4, 6, 8, 9):
    c = d["cards"][i - 1]
    v = c.get("visual")
    svg = diagrams.build(v)
    print("=" * 20, i, "번", v.get("kind"))
    print("spec:", json.dumps(v, ensure_ascii=False)[:400])
    print("svg len:", len(svg))
    # 텍스트 노드 뽑기
    texts = re.findall(r">([^<>]{1,40})</text>", svg)
    print("svg 안 텍스트:", texts[:12])
    if "없음" in svg or "fallback" in svg.lower():
        print("⚠️ 폴백 렌더됨")
    print()

print("=== 원문 LaTeX 확인 (2/5/7번) ===")
for i in (2, 5, 7):
    b = d["cards"][i - 1].get("body", "")
    for m in re.findall(r"\$[^$]{1,60}\$", b)[:4]:
        print(f"  {i}번: {m}")
