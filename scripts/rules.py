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

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import diagrams  # noqa: E402  (렌더 실패 감지용)

CJK_RE = re.compile(r"[\u3040-\u309f\u30a0-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uff66-\uff9f]")
VISUAL_TYPES = ("visual", "diagram", "table", "chart", "compare", "flow")

BUILTIN = [
    {"id": "visual-payload", "check": "visual_payload", "severity": "high",
     "text": "visual 카드에는 렌더 가능한 페이로드(visual/data/diagram)가 있어야 한다",
     "source": "builtin"},
    {"id": "visual-renderable", "check": "visual_renderable", "severity": "high",
     "text": "visual 스펙이 실제로 렌더돼야 한다 (폴백/빈 라벨 금지)",
     "source": "builtin"},
    {"id": "korean-only", "check": "cjk_free", "severity": "high",
     "text": "한국어만. 일본어·중국어 문자 금지", "source": "builtin"},
    {"id": "required-fields", "check": "required_fields", "severity": "high",
     "text": "topic·handle·caption 필수", "source": "builtin"},
    {"id": "card-count", "check": "card_count", "severity": "high",
     "text": "카드 5~11장 (결론 카드 포함)", "source": "builtin"},
    {"id": "conclusion-before-insight", "check": "conclusion_before_insight", "severity": "high",
     "text": "마지막 '실무자 인사이트' 바로 앞에 '결론' 카드(type=conclusion)가 있어야 한다",
     "source": "builtin"},
    {"id": "cover-3line", "check": "cover_3line", "severity": "medium",
     "text": "커버 제목은 3줄 도발·단정형", "source": "builtin"},
    {"id": "body-length", "check": "body_length", "severity": "high",
     "text": "본문은 230자 이하 — 넘으면 자동축소로 글씨가 작아져 읽기 나빠진다",
     "source": "builtin"},
    {"id": "numeric-consistency", "check": "numeric_consistency", "severity": "high",
     "text": "커버 숫자와 차트 숫자가 일치해야 한다 ('격차'는 실제 계산값과 같아야 한다)",
     "source": "builtin"},
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
    """내장 룰을 저장소에 반영한다.

    과거 버그: `d["rules"] = BUILTIN + d["rules"]` 로 매 실행마다 전체를
    다시 앞에 붙여서 룰이 4중복까지 쌓였다(같은 규칙이 4번 검사·4번 보고됨).
    id 기준으로 병합하고, 사람이 정한 status 는 보존한다.
    """
    d = load_store()
    existing = {r.get("id"): r for r in d["rules"] if isinstance(r, dict) and r.get("id")}
    builtin_ids = {r["id"] for r in BUILTIN}
    CODE_OWNED = ("text", "check", "severity", "source")

    merged = []
    for r in BUILTIN:
        cur = existing.get(r["id"]) or {}
        merged.append({**cur, **{k: r[k] for k in CODE_OWNED if k in r},
                       "id": r["id"]})
    merged += [r for r in d["rules"]
               if isinstance(r, dict) and r.get("id") not in builtin_ids]

    if merged != d["rules"]:
        d["rules"] = merged
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


def _conclusion_problems(d):
    """마지막 '실무자 인사이트'(insight) 바로 앞에 '결론'(conclusion) 카드가 있어야 한다.

    사용자 요구: 발행 때마다 인사이트 전에 서머리 성격의 결론 카드를 둔다.
    """
    cards = _cards(d)
    if not cards:
        return []
    insight_idx = next((i for i, c in enumerate(cards)
                        if c.get("type") == "insight"), None)
    if insight_idx is None:
        return [{"card": 0, "detail": "insight 카드가 없어 결론 위치를 판정할 수 없습니다"}]
    if insight_idx == 0:
        return [{"card": 1, "detail": "insight 카드가 첫 장입니다 — 결론 카드를 앞에 둘 수 없습니다"}]
    prev = cards[insight_idx - 1]
    if prev.get("type") != "conclusion":
        return [{"card": insight_idx,
                 "detail": (f"인사이트({insight_idx + 1}번) 바로 앞 {insight_idx}번 카드가 "
                            f"type='{prev.get('type', 'body')}' 입니다 — "
                            "'결론'(type=conclusion) 카드를 넣어라")}]
    return []


def _render_problem(c):
    """시각화가 실제로 렌더되는지 확인. 문제 있으면 사유 문자열, 없으면 ''.

    050 발행 사고의 원인: 규칙이 'visual 키가 있는가'만 봤고
    '실제로 그려지는가'는 안 봐서, 폴백으로 깨진 카드가 통과했다.
    """
    spec = c.get("visual") or c.get("data") or c.get("diagram")
    if not isinstance(spec, dict):
        return "스펙이 dict 가 아닙니다"
    kind = spec.get("kind")
    try:
        svg = diagrams.build(spec)
    except Exception as e:                      # noqa: BLE001
        return f"렌더 중 예외 ({kind}): {e}"
    if diagrams.FALLBACK_MARKER in svg:
        return f"빌더 실패→폴백 렌더 (kind={kind}). 스펙 형태를 빌더에 맞춰라"
    if "<text" not in svg:
        return f"라벨 텍스트가 0개 (kind={kind}) — 빈 그림"
    return ""


def _text(c):
    parts = [c.get("title"), c.get("heading"), c.get("body"), c.get("lead")]
    parts += list(c.get("bullets") or [])
    return " ".join(str(p) for p in parts if p)


def _pct_numbers(text):
    """텍스트에서 퍼센트 숫자만 뽑는다. (97%, 94 등)"""
    return [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*%", str(text or ""))]


def _visual_numbers(card):
    """시각화(차트)가 담고 있는 숫자들 — 데이터의 정본으로 취급한다."""
    v = card.get("visual") or card.get("data") or card.get("diagram") or {}
    if not isinstance(v, dict):
        return []
    out = []
    for it in (v.get("items") or []):
        if isinstance(it, dict) and isinstance(it.get("value"), (int, float)):
            out.append(float(it["value"]))
    for row in (v.get("values") or []):
        if isinstance(row, list):
            out += [float(x) for x in row if isinstance(x, (int, float))]
    for sr in (v.get("series") or []):
        if isinstance(sr, dict):
            for p in (sr.get("points") or []):
                if isinstance(p, list) and len(p) > 1 and isinstance(p[1], (int, float)):
                    out.append(float(p[1]))
    return out


def _numeric_problems(d):
    """커버 숫자 ↔ 차트 숫자 불일치, 그리고 '격차' 항목의 계산 오류를 잡는다.

    051 사고: 커버는 97%/60%/37%, 차트는 94/59/37(94-59=35) 였다.
    규칙이 '키가 있는가'만 봐서 이걸 못 잡았다.
    """
    out = []
    cards = _cards(d)
    if not cards:
        return out
    vis = [n for c in cards for n in _visual_numbers(c)]
    vis_nums = sorted(set(vis))

    # 1) 커버 숫자가 차트 숫자와 '가까운데 다른' 경우 → 드리프트로 판정
    cover = cards[0]
    cover_text = f'{cover.get("title","")} {cover.get("subtitle","")} {cover.get("body","")}'
    for n in _pct_numbers(cover_text):
        if not vis_nums:
            continue
        near = [v for v in vis_nums if v and abs(n - v) / v <= 0.15]
        if near and not any(abs(n - v) < 0.01 for v in vis_nums):
            out.append({"card": 1, "detail":
                        f"커버 숫자 {n:g}% 가 차트 값 {near} 와 불일치 "
                        f"(차트를 정본으로 삼아 맞춰라)"})

    # 2) '격차/차이' 항목 값이 나머지 값들의 차와 다른 경우
    for i, c in enumerate(cards, 1):
        v = c.get("visual") or c.get("data") or c.get("diagram") or {}
        if not isinstance(v, dict):
            continue
        items = [x for x in (v.get("items") or []) if isinstance(x, dict)]
        gaps, others = [], []
        for x in items:
            val = x.get("value")
            if re.search(r"격차|차이|gap", str(x.get("label", ""))):
                gaps.append((x.get("label"), val))
            elif isinstance(val, (int, float)):
                others.append(float(val))
        if gaps and len(others) >= 2:
            want = abs(max(others) - min(others))
            for glabel, gv in gaps:
                if isinstance(gv, (int, float)) and abs(float(gv) - want) > 0.5:
                    out.append({"card": i, "detail":
                                f"{i}번 차트 '{glabel}' 값 {float(gv):g} 이 "
                                f"실제 계산값 {want:g} 과 다름 ({max(others):g}-{min(others):g})"})
    return out


CHECKS = {
    "visual_payload": lambda d: [
        {"card": i, "detail": f"{i}번 카드 type={c.get('type')} 인데 페이로드가 없습니다"}
        for i, c in enumerate(_cards(d), 1)
        if c.get("type") in VISUAL_TYPES and not _has_visual(c)],

    "visual_renderable": lambda d: [
        {"card": i, "detail": f"{i}번 카드 시각화 {why}"}
        for i, c in enumerate(_cards(d), 1)
        if c.get("type") in VISUAL_TYPES
        for why in [_render_problem(c)] if why],

    "cjk_free": lambda d: [
        {"card": i, "detail": f"{i}번 카드에 일본어/중국어: "
                             f"{' '.join(sorted({ch for ch in _text(c) if CJK_RE.match(ch)})[:8])}"}
        for i, c in enumerate(_cards(d), 1)
        if any(CJK_RE.match(ch) for ch in _text(c))],

    "required_fields": lambda d: [
        {"card": 0, "detail": f"필수 필드 누락: {f}"}
        for f in ("topic", "handle", "caption") if not d.get(f)],

    "body_length": lambda d: [
        {"card": i, "detail": f"{i}번 카드 본문 {len(c.get('body') or '')}자 "
                             f"(230자 이하 권장) — 글을 줄이고 시각화로 채워라"}
        for i, c in enumerate(_cards(d), 1)
        if len(c.get("body") or "") > 230],

    "numeric_consistency": lambda d: _numeric_problems(d),

    "card_count": lambda d: (
        [] if 5 <= len(_cards(d)) <= 11
        else [{"card": 0, "detail": f"카드 {len(_cards(d))}장 (5~11장 필요)"}]),

    "conclusion_before_insight": lambda d: _conclusion_problems(d),

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


# ── 릴스(가십) 전용 규칙 ────────────────────────────────────

REEL_KINDS = ("hook", "fact", "why", "use", "cta")
REEL_RULES = [
    {"id": "reel-scenes", "check": "reel_scenes", "severity": "high",
     "text": "릴스는 5씬 (hook·fact·why·use·cta) 정확히"},
    {"id": "reel-visual", "check": "reel_visual", "severity": "high",
     "text": "모든 씬에 시각화(visual) 필수 — 글만 있는 씬 금지"},
    {"id": "reel-sources", "check": "reel_sources", "severity": "high",
     "text": "뉴스는 출처 URL 2개 이상 (1개면 kind=rumor)"},
    {"id": "reel-use", "check": "reel_use", "severity": "high",
     "text": "'use' 씬 필수 — 얻어가는 것(적용 포인트)"},
    {"id": "reel-text-min", "check": "reel_text_min", "severity": "medium",
     "text": "화면 텍스트 최소: label 10자·takeaway 22자 이내"},
    {"id": "reel-korean", "check": "reel_korean", "severity": "high",
     "text": "한국어만 (일본어·중국어 금지)"},
]


def _reel_scenes(d):
    return d.get("scenes") or []


def _reel_text(sc):
    return " ".join(str(sc.get(k, "") or "")
                    for k in ("label", "takeaway", "narration"))


def reel_evaluate(d):
    out = []
    scenes = _reel_scenes(d)
    kinds = [s.get("kind") for s in scenes]

    if len(scenes) != 5 or set(kinds) != set(REEL_KINDS):
        out.append({"rule": "reel-scenes", "severity": "high", "card": 0,
                    "detail": f"씬 {len(scenes)}개 / kind={kinds} — 5씬(hook·fact·why·use·cta) 필요"})

    for i, s in enumerate(scenes, 1):
        if not s.get("visual"):
            out.append({"rule": "reel-visual", "severity": "high", "card": i,
                        "detail": f"{i}번 씬({s.get('kind')})에 visual 이 없습니다"})
        if any(CJK_RE.match(ch) for ch in _reel_text(s)):
            out.append({"rule": "reel-korean", "severity": "high", "card": i,
                        "detail": f"{i}번 씬에 일본어/중국어 문자가 있습니다"})
        lab, tk = str(s.get("label", "") or ""), str(s.get("takeaway", "") or "")
        if len(lab) > 10 or len(tk) > 22:
            out.append({"rule": "reel-text-min", "severity": "medium", "card": i,
                        "detail": f"{i}번 씬 텍스트 과다 (label {len(lab)}자 / takeaway {len(tk)}자)"})

    if "use" not in kinds:
        out.append({"rule": "reel-use", "severity": "high", "card": 0,
                    "detail": "'use' 씬이 없습니다 — 얻어가는 것이 빠짐"})

    src = d.get("sources") or []
    if d.get("kind") != "rumor" and len(src) < 2:
        out.append({"rule": "reel-sources", "severity": "high", "card": 0,
                    "detail": f"출처 {len(src)}개 — 뉴스는 2개 이상 필요 (아니면 kind=rumor)"})
    return out


def reel_blocking(d):
    return [v for v in reel_evaluate(d) if v["severity"] == "high"]


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
    cr = sub.add_parser("check-reel")
    cr.add_argument("path")
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

    elif args.cmd == "check-reel":
        p = pathlib.Path(args.path)
        if not p.is_absolute():
            p = (ROOT / "content" / "queue" / "reels" / args.path)
            if not p.exists() and not p.suffix:
                p = p.with_suffix(".json")
        if not p.exists():
            sys.exit(f"파일 없음: {p}")
        data = json.loads(p.read_text(encoding="utf-8"))
        v = reel_evaluate(data)
        if not v:
            print(f"✅ {p.name} — 릴스 규칙 위반 없음")
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
