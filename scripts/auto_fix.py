#!/usr/bin/env python3
"""리뷰 → 수정 → 발행.

기존 파이프라인은 '검수에서 걸리면 차단'이었다. 그래서 리뷰어가 진짜 결함
(예: 051의 커버 97%/60% vs 차트 94/59)을 찾아도 발행이 그냥 막히거나,
LLM 차단이 OFF라 그대로 나갔다.

이 스크립트는 그 사이를 닫는다:
  1) 리뷰(진보/보수) + 룰 검사
  2) 지적을 **반영해 원고를 수정**한다
     - 결정론적 수정: '격차' 재계산, 커버 숫자를 차트 정본에 정렬, 커버 3줄
     - LLM 수정: 카드 단위로 지적을 반영 (적용 후 결정론 재검증, 실패하면 되돌림)
  3) 재검증 → high 위반이 없으면 **발행 가능(0)**, 남으면 보류(1)

거짓 지적(오판)은 수정 대상에서 제외한다 — 예: "2026년은 미래" 같은
학습 컷오프 기반 오판. 오판을 '고치면' 멀쩡한 내용이 망가진다.

사용:
  python auto_fix.py --slug 051-overfitting-generalization
  python auto_fix.py --slug X --rounds 3        # 더 시도
  python auto_fix.py --slug X --no-llm          # 결정론 수정만
종료 코드: 0 = 발행 가능, 1 = 보류(사람 확인 필요)
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import rules as R                     # noqa: E402
import postqueue as q                 # noqa: E402

TODAY = dt.date.today().isoformat()

# ── 거짓 지적(오판) 필터 ─────────────────────────────────────
# LLM 리뷰어는 학습 컷오프 때문에 "미래 날짜"라고 오판한다.
# 그런 지적을 '수정'하면 멀쩡한 날짜를 망가뜨린다.
FALSE_POSITIVE_PATTERNS = [
    r"미래", r"future", r"검증\s*불가", r"아직\s*일어나지",
]


def is_false_positive(issue: dict) -> bool:
    detail = str(issue.get("detail", ""))
    if not re.search("|".join(FALSE_POSITIVE_PATTERNS), detail):
        return False
    # 지적 안에 오늘 이전 날짜가 있으면 '미래' 주장은 거짓
    for y, m in re.findall(r"(20\d{2})\s*년\s*(\d{1,2})\s*월", detail):
        try:
            d = dt.date(int(y), int(m), 1)
        except ValueError:
            continue
        if d <= dt.date.today():
            return True
    # 연도만 언급된 경우
    for y in re.findall(r"(20\d{2})", detail):
        if int(y) <= dt.date.today().year:
            return True
    return False


# ── 결정론적 수정기 ──────────────────────────────────────────

def fix_gap_values(data) -> list:
    """'격차/차이' 항목 값을 실제 계산값으로 고친다."""
    applied = []
    for i, c in enumerate(data.get("cards", []), 1):
        v = c.get("visual")
        if not isinstance(v, dict):
            continue
        items = [x for x in (v.get("items") or []) if isinstance(x, dict)]
        gaps, others = [], []
        for x in items:
            val = x.get("value")
            if re.search(r"격차|차이|gap", str(x.get("label", ""))):
                gaps.append(x)
            elif isinstance(val, (int, float)):
                others.append(float(val))
        if gaps and len(others) >= 2:
            want = abs(max(others) - min(others))
            for g in gaps:
                if isinstance(g.get("value"), (int, float)) and abs(float(g["value"]) - want) > 0.5:
                    old = g["value"]
                    g["value"] = int(want) if float(want).is_integer() else round(want, 2)
                    applied.append(f"{i}번 차트 '{g.get('label')}' {old:g} → {g['value']:g} "
                                   f"(계산값 {max(others):g}-{min(others):g})")
    return applied


def visual_numbers(data) -> list:
    out = []
    for c in data.get("cards", []):
        out += R._visual_numbers(c)
    return sorted({n for n in out if n})


def fix_cover_numbers(data) -> list:
    """커버의 숫자를 차트(정본) 값에 정렬한다.

    예: 커버 97%/60%/37% → 차트 94/59/35 로 치환.
    차트 값과 15% 이상 떨어져 있으면 다른 지표로 보고 건드리지 않는다.
    """
    cards = data.get("cards", [])
    if not cards or cards[0].get("type") != "cover":
        return []
    canon = visual_numbers(data)
    if not canon:
        return []
    applied = []

    def remap(text):
        if not text:
            return text, []
        changed = []

        def sub(m):
            raw = m.group(1)
            n = float(raw)
            if any(abs(n - v) < 0.01 for v in canon):
                return m.group(0)                       # 이미 일치
            near = [v for v in canon if abs(n - v) / v <= 0.15]
            if not near:
                return m.group(0)                       # 다른 지표 — 보존
            tgt = min(near, key=lambda v: abs(n - v))
            new = f"{tgt:g}"
            if new != raw:
                changed.append(f"{raw} → {new}")
            return f"{new}%"
        out = re.sub(r"(\d+(?:\.\d+)?)\s*%", sub, str(text))
        return out, changed

    for field in ("title", "subtitle", "body", "lead"):
        if cards[0].get(field):
            new, ch = remap(cards[0][field])
            if ch:
                cards[0][field] = new
                applied.append(f"커버 {field}: " + ", ".join(ch))
    return applied


DETERMINISTIC_FIXERS = [fix_gap_values, fix_cover_numbers]


def deterministic_pass(data) -> list:
    applied = []
    for fn in DETERMINISTIC_FIXERS:
        try:
            applied += fn(data) or []
        except Exception as e:                                  # noqa: BLE001
            applied.append(f"[{fn.__name__} 실패: {type(e).__name__}: {e}]")
    return applied


# ── LLM 수정 (적용 후 재검증, 실패 시 되돌림) ────────────────

FIX_PROMPT = """너는 카드뉴스 원고를 고치는 편집자다. 아래 '지적'만 반영해서
해당 카드의 JSON 필드를 고쳐라. 지적과 무관한 내용은 절대 바꾸지 마라.

오늘 날짜: {today}
규칙: 한국어만 사용. 본문 230자 이하. 수식은 $...$ 로 표기.

[지적]
{issues}

[카드 원문 JSON]
{card}

출력은 수정된 카드 JSON 하나만. 설명 없이 JSON만."""


def llm_fix_card(card: dict, issues: list, timeout=120):
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        return None, "OPENROUTER_API_KEY 없음"
    model = os.environ.get("REVIEW_MODEL_PROGRESSIVE") or "anthropic/claude-sonnet-4.5"
    body = {
        "model": model,
        "messages": [{"role": "user", "content": FIX_PROMPT.format(
            today=TODAY,
            issues=json.dumps(issues, ensure_ascii=False, indent=1),
            card=json.dumps(card, ensure_ascii=False, indent=1))}],
        "temperature": 0,
    }
    try:
        import requests
        r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                          json=body, timeout=timeout,
                          headers={"Authorization": f"Bearer {key}",
                                   "Content-Type": "application/json"})
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}: {r.text[:160]}"
        txt = r.json()["choices"][0]["message"]["content"]
        txt = re.sub(r"^```(?:json)?|```$", "", txt.strip(), flags=re.M).strip()
        return json.loads(txt), None
    except Exception as e:                                      # noqa: BLE001
        return None, f"{type(e).__name__}: {str(e)[:140]}"


def llm_pass(data, issues, max_cards=3) -> tuple[list, list]:
    """지적이 있는 카드만 LLM으로 고친다.

    적용 후 '그 카드의 위반이 실제로 줄었는지'를 결정론적으로 확인한다.
    줄지 않았으면 되돌린다 — 안 고쳐진 카드를 그대로 두면 발행까지 흘러간다.
    """
    applied, notes = [], []

    def card_high(no):
        return {x.get("detail") for x in R.evaluate(data)
                if x.get("severity") == "high" and x.get("card") == no}

    by_card: dict[int, list] = {}
    for i in issues:
        c = i.get("card")
        if isinstance(c, int) and 1 <= c <= len(data.get("cards", [])):
            by_card.setdefault(c, []).append(i)

    for card_no, card_issues in list(by_card.items())[:max_cards]:
        idx = card_no - 1
        original = copy.deepcopy(data["cards"][idx])
        before = card_high(card_no)

        new_card, err = llm_fix_card(original, card_issues)
        if err or not isinstance(new_card, dict):
            notes.append(f"{card_no}번 LLM 수정 실패: {err}")
            continue

        new_card.setdefault("type", original.get("type"))
        data["cards"][idx] = new_card
        after = card_high(card_no)

        if after and len(after) >= len(before):
            data["cards"][idx] = original
            notes.append(f"{card_no}번 LLM 수정이 결함을 못 고쳐 되돌림")
        else:
            applied.append(f"{card_no}번 카드 LLM 수정 적용 "
                           f"(위반 {len(before)}→{len(after)})")
    return applied, notes


# ── 메인 루프 ────────────────────────────────────────────────

def run(slug: str, rounds=2, use_llm=True, verbose=True):
    path = ROOT / "content" / "queue" / f"{slug}.json"
    if not path.exists():
        sys.exit(f"원고가 없습니다: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))

    history = []
    for rnd in range(1, rounds + 1):
        issues = R.evaluate(data)
        high = [i for i in issues if i.get("severity") == "high"]
        if verbose:
            print(f"— 라운드 {rnd}: high 위반 {len(high)}건")
        if not high:
            break

        applied = deterministic_pass(data)
        if applied and verbose:
            for a in applied:
                print(f"    ✏️  {a}")

        remaining = [i for i in R.evaluate(data) if i.get("severity") == "high"]
        llm_applied, notes = [], []
        if remaining and use_llm:
            # 오판은 수정 대상에서 제외
            real = [i for i in remaining if not is_false_positive(i)]
            skipped = [i for i in remaining if is_false_positive(i)]
            for s in skipped:
                if verbose:
                    print(f"    🚫 오판 제외: {s.get('detail','')[:70]}")
            if real:
                llm_applied, notes = llm_pass(data, real)
                if verbose:
                    for a in llm_applied:
                        print(f"    🤖 {a}")
                    for n in notes:
                        print(f"    ⚠️  {n}")

        history.append({"round": rnd, "deterministic": applied,
                        "llm": llm_applied, "notes": notes})
        if not applied and not llm_applied:
            if verbose:
                print("    (더 고칠 것이 없음 — 루프 종료)")
            break

    final = R.evaluate(data)
    high_left = [i for i in final if i.get("severity") == "high"]
    real_left = [i for i in high_left if not is_false_positive(i)]

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    if verbose:
        print()
        if not real_left:
            print(f"✅ {slug} — 수정 완료, 발행 가능")
            if high_left:
                print(f"   (오판으로 제외된 지적 {len(high_left)}건은 발행을 막지 않음)")
        else:
            print(f"❌ {slug} — 자동 수정으로 해결 못 한 high 위반 {len(real_left)}건")
            for i in real_left[:5]:
                print(f"   - {i.get('rule')}: {i.get('detail','')[:100]}")

    return {"slug": slug, "history": history, "remaining": real_left,
            "ready": not real_left}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    res = run(a.slug, rounds=a.rounds, use_llm=not a.no_llm, verbose=not a.quiet)
    sys.exit(0 if res["ready"] else 1)


if __name__ == "__main__":
    main()
