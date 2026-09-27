#!/usr/bin/env python3
"""rules — 자기개선 규칙 저장소 + 검사 엔진 (L3 의 코드화).

"지시"가 아니라 "코드"로 강제하기 위한 단일 진실 출처.
content_reviewer 와 growth_generate 가 모두 이 파일을 쓴다.

규칙 상태:
  active   — 검사에 적용됨. high 는 발행/추가 차단
  pending  — 피드백에서 자동 승격된 후보. 사람이 승인해야 active

사용법:
  python rules.py list
  python rules.py check <slug>          # 원고 1건 검사
  python rules.py approve <rule-id>     # pending → active
  python rules.py reject  <rule-id>
"""

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
STORE = ROOT / "content" / "rules.json"

CJK_RE = re.compile(r"[\u3040-\u309f\u30a0-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uff66-\uff9f]")
VISUAL_TYPES = ("visual", "diagram", "table", "chart", "compare", "flow")

BUILTIN = [
    {"id": "visual-payload", "check": "visual_payload", "severity": "high",
     "text": "visual 카드에는 렌더 가능한 페이로드(visual/data/diagram)가 있어야 한다",
     "source": "builtin"},
    {"id": "korean-only", "check": "cjk_free", "severity": "high",
     "text": "한국어만. 일본어·중국어 문자 금지", "source": "builtin"},
    {"id": "required-fields", "check": "required_fields", "severity": "high",
     "text": "topic·handle·caption 필수", "source": "builtin"},
    {"id": "card-count", "check": "card_count", "severity": "high",
     "text": "카드 5~10장", "source": "builtin"},
    {"id": "cover-3line", "check": "cover_3line", "severity": "medium",
     "text": "커버 제목은 3줄 도발·단정형", "source": "builtin"},
    {"id": "visual-ratio", "check": "visual_ratio", "severity": "medium",
     "text": "시각화 카드 비율 40% 이상", "source": "builtin"},
    {"id": "heading-length", "check": "heading_length", "severity": "low",
     "text": "heading 26자 이하", "source": "builtin"},
]


# ── 저장소 ────────────────────────────────────────────────

def load_store():
    if STORE.exists():
        try:
            d = json.loads(STORE.read_text(encoding="utf-8"))
            d.setdefault("rules", [])
            d.setdefault("pending", [])
            return d
        except json.JSONDecodeError:
            pass
    return {"rules": [], "pending": []}


def save_store(d):
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_builtins():
    d = load_store()
    have = {r["id"] for r in d["rules"]}
    added = [r for r in BUILTIN if r["id"] not in have]
    if added:
        d["rules"] = BUILTIN + d["rules"]
        save_store(d)
    return d


def active_rules():
    d = ensure_builtins()
    return [r for r in d["rules"] if r.get("status", "active") == "active"]


# ── 검사기 ────────────────────────────────────────────────

def _cards(d):
    return d.get("cards", [])


def _has_visual(c):
    return bool(c.get("visual") or c.get("data") or c.get("diagram"))


def _text(c):
    parts = [c.get("title"), c.get("heading"), c.get("body"), c.get("lead")]
    parts += list(c.get("bullets") or [])
    return " ".join(str(p) for p in parts if p)


CHECKS = {
    "visual_payload": lambda d: [
        {"card": i, "detail": f"{i}번 카드 type={c.get('type')} 인데 페이로드가 없습니다"}
        for i, c in enumerate(_cards(d), 1)
        if c.get("type") in VISUAL_TYPES and not _has_visual(c)],

    "cjk_free": lambda d: [
        {"card": i, "detail": f"{i}번 카드에 일본어/중국어: "
                             f"{' '.join(sorted({ch for ch in _text(c) if CJK_RE.match(ch)})[:8])}"}
        for i, c in enumerate(_cards(d), 1)
        if any(CJK_RE.match(ch) for ch in _text(c))],

    "required_fields": lambda d: [
        {"card": 0, "detail": f"필수 필드 누락: {f}"}
        for f in ("topic", "handle", "caption") if not d.get(f)],

    "card_count": lambda d: (
        [] if 5 <= len(_cards(d)) <= 10
        else [{"card": 0, "detail": f"카드 {len(_cards(d))}장 (5~10장 필요)"}]),

    "cover_3line": lambda d: (
        [] if _cards(d) and _cards(d)[0].get("type") == "cover"
        and "\n" in _cards(d)[0].get("title", "")
        else [{"card": 1, "detail": "커버 제목이 3줄 도발형이 아닙니다"}]),

    "visual_ratio": lambda d: (
        [] if not _cards(d) else (
            [] if sum(1 for c in _cards(d)
                      if c.get("type") in VISUAL_TYPES and _has_visual(c)) / len(_cards(d)) >= 0.4
            else [{"card": 0, "detail": "시각화 비율이 40% 미만입니다"}])),

    "heading_length": lambda d: [
        {"card": i, "detail": f"{i}번 heading {len(c.get('heading',''))}자"}
        for i, c in enumerate(_cards(d), 1)
        if len(c.get("heading", "") or "") > 26],
}


def evaluate(data, rules=None):
    """active 규칙을 돌려 위반 목록 반환."""
    rules = rules if rules is not None else active_rules()
    out = []
    for r in rules:
        fn = CHECKS.get(r.get("check"))
        if not fn:
            continue
        try:
            for v in fn(data):
                out.append({"rule": r["id"], "text": r["text"],
                            "severity": r.get("severity", "medium"), **v})
        except Exception as e:                              # noqa: BLE001
            out.append({"rule": r["id"], "text": r["text"], "severity": "low",
                        "card": 0, "detail": f"검사기 오류: {type(e).__name__}"})
    return out


def blocking(data, rules=None):
    return [v for v in evaluate(data, rules) if v["severity"] == "high"]


# ── 승격 (feedback → pending → active) ─────────────────────

def promote(text, check=None, severity="medium", source="feedback"):
    """규칙 후보를 pending 에 추가. 같은 문구면 hits 증가."""
    d = ensure_builtins()
    key = text.strip()
    for r in d["rules"] + d["pending"]:
        if r.get("text", "").strip() == key:
            r["hits"] = r.get("hits", 1) + 1
            save_store(d)
            return r
    rec = {"id": f"fb-{len(d['pending']) + 1:02d}", "text": key,
           "check": check, "severity": severity, "status": "pending",
           "source": source, "hits": 1,
           "note": "사람 승인 필요: python rules.py approve <id>" if not check
                   else "승인 시 자동 검사 적용"}
    d["pending"].append(rec)
    save_store(d)
    return rec


def approve(rule_id):
    d = ensure_builtins()
    for i, r in enumerate(d["pending"]):
        if r["id"] == rule_id:
            r["status"] = "active"
            d["rules"].append(d["pending"].pop(i))
            save_store(d)
            return r
    return None


def reject(rule_id):
    d = ensure_builtins()
    for i, r in enumerate(d["pending"]):
        if r["id"] == rule_id:
            d["pending"].pop(i)
            save_store(d)
            return True
    return False


def briefing():
    """원고 생성 전에 주입할 텍스트 (L3 → L1)."""
    d = ensure_builtins()
    lines = []
    if d["pending"]:
        lines.append("## 승인 대기 규칙 (참고)")
        lines += [f"- {r['text']} (위반 {r.get('hits',1)}회)" for r in d["pending"]]
    checks = [r for r in d["rules"] if r.get("status", "active") == "active"]
    if checks:
        lines.append("\n## 활성 규칙 (위반 시 발행 차단)")
        lines += [f"- [{r.get('severity')}] {r['text']}" for r in checks]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    sub.add_parser("briefing")
    c = sub.add_parser("check")
    c.add_argument("slug")
    a = sub.add_parser("approve"); a.add_argument("rule_id")
    r = sub.add_parser("reject"); r.add_argument("rule_id")
    p = sub.add_parser("promote")
    p.add_argument("text"); p.add_argument("--check"); p.add_argument("--severity", default="medium")
    args = ap.parse_args()

    if args.cmd == "list":
        d = ensure_builtins()
        print(f"활성 규칙 {len([r for r in d['rules'] if r.get('status','active')=='active'])}개")
        for x in d["rules"]:
            if x.get("status", "active") == "active":
                print(f"  [{x.get('severity')}] {x['id']:16s} {x['text']}")
        if d["pending"]:
            print(f"\n승인 대기 {len(d['pending'])}개")
            for x in d["pending"]:
                print(f"  {x['id']:16s} {x['text']} (위반 {x.get('hits',1)}회)")

    elif args.cmd == "briefing":
        print(briefing())

    elif args.cmd == "check":
        import postqueue as q
        data = q.load(args.slug)
        v = evaluate(data)
        if not v:
            print(f"✅ {args.slug} — 규칙 위반 없음")
            return
        for x in v:
            print(f"[{x['severity']}] {x['rule']}: {x['detail']}")
        sys.exit(1 if any(x["severity"] == "high" for x in v) else 0)

    elif args.cmd == "promote":
        rec = promote(args.text, args.check, args.severity)
        print(f"후보 등록: {rec['id']} (위반 {rec.get('hits')}회) — {rec['text']}")

    elif args.cmd == "approve":
        rec = approve(args.rule_id)
        print(f"승인됨: {rec['id']} → active" if rec else "해당 id 없음")

    elif args.cmd == "reject":
        print("삭제됨" if reject(args.rule_id) else "해당 id 없음")


if __name__ == "__main__":
    main()
