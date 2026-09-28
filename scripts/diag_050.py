"""050 원고 진단 — 카드별 문제(빈 렌더/텍스트 과다/LaTeX) 탐지."""
import json, pathlib, re, sys
sys.path.insert(0, "/opt/data/ai_cardnews/scripts")
import diagrams

d = json.loads(pathlib.Path("/opt/data/ai_cardnews/content/queue/050-activation-functions.json")
               .read_text(encoding="utf-8"))

print(f"총 {len(d['cards'])}장\n")
for i, c in enumerate(d["cards"], 1):
    t = c.get("type")
    head = c.get("heading", "") or c.get("title", "")
    body = c.get("body", "") or ""
    v = c.get("visual")
    line = f"[{i:2d}] {t:8s} heading={len(head):2d}자 body={len(body):3d}자"
    problems = []
    if not head.strip() and t not in ("insight",):
        problems.append("제목없음")
    if t == "visual":
        if not v:
            problems.append("visual키없음")
        else:
            svg = diagrams.build(v)
            if "시각자료 없음" in svg:
                problems.append(f"렌더실패(kind={v.get('kind')})")
            kind = v.get("kind")
            # bars 인데 라벨이 짧으면 왼쪽 공백 발생
            if kind == "bars":
                labs = [str(x.get("label", "")) for x in (v.get("items") or [])]
                mx = max((len(x) for x in labs), default=0)
                if mx < 6:
                    problems.append(f"bars라벨짧음(최대{mx}자)→좌측공백")
    if re.search(r"\$[^$]{2,}\$", body) or re.search(r"\$[^$]{2,}\$", head):
        problems.append("LaTeX원문노출")
    print(line + ("  ⚠️ " + ", ".join(problems) if problems else "  OK"))
    if t == "visual" and v:
        print(f"      visual kind={v.get('kind')} keys={list(v.keys())}")

print("\n=== 캡션 길이 ===", len(d.get("caption", "")))
print("=== 해시태그", len(d.get("hashtags", [])), "개 ===")
