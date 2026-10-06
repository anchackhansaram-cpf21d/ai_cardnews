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
    """리뷰어가 지적한 카드를 LLM으로 고친다.

    적용 후 '그 카드의 위반이 실제로 줄었는지'를 결정론적으로 확인한다.
    줄지 않았으면 되돌린다 — 안 고쳐진 카드를 그대로 두면 발행까지 흘러간다.
    """
    applied, notes = [], []

    def card_high(no):
        return {x.get("detail") for x in R.evaluate(data)
                if x.get("severity") == "high" and x.get("card") == no}

    def all_high():
        return {x.get("detail") for x in R.evaluate(data) if x.get("severity") == "high"}

    by_card: dict[int, list] = {}
    for i in issues:
        c = i.get("card")
        if isinstance(c, int) and 1 <= c <= len(data.get("cards", [])):
            by_card.setdefault(c, []).append(i)

    for card_no, card_issues in list(by_card.items())[:max_cards]:
        idx = card_no - 1
        original = copy.deepcopy(data["cards"][idx])
        before_card, before_all = card_high(card_no), all_high()

        new_card, err = llm_fix_card(original, card_issues)
        if err or not isinstance(new_card, dict):
            notes.append(f"{card_no}번 LLM 수정 실패: {err}")
            continue

        new_card.setdefault("type", original.get("type"))
        data["cards"][idx] = new_card
        after_card, after_all = card_high(card_no), all_high()

        new_violation = bool(after_all - before_all)
        unresolved = bool(before_card and after_card and len(after_card) >= len(before_card))
        if new_violation or unresolved:
            data["cards"][idx] = original
            why = "새 위반을 만들어" if new_violation else "결함을 못 고쳐"
            notes.append(f"{card_no}번 LLM 수정이 {why} 되돌림")
        else:
            applied.append(f"{card_no}번 카드 LLM 수정 적용 "
                           f"(위반 {len(before_card)}→{len(after_card)})")
    return applied, notes


# ── 리뷰어(진보/보수)의 리뷰를 수정에 반영 ───────────────────

def run_reviewer(slug: str):
    """content_reviewer 를 돌려 진보/보수 리뷰 결과를 가져온다.

    반환: (llm_issues, patches, summaries)
      llm_issues — 리뷰어가 지적한 것 (source=progressive|conservative)
      patches    — 진보 리뷰어가 제안한 카드 패치
    """
    try:
        import content_reviewer as CR
    except Exception as e:                                      # noqa: BLE001
        return [], [], {"error": f"리뷰어 로드 실패: {e}"}
    try:
        res = CR.review(slug, fix=False, roles=["progressive", "conservative"])
    except Exception as e:                                      # noqa: BLE001
        return [], [], {"error": f"리뷰 실행 실패: {type(e).__name__}: {e}"}
    llm_issues = [i for i in (res.get("issues") or []) if i.get("source")]
    patches = res.get("patches") or []
    return llm_issues, patches, res.get("summaries") or {}


def apply_reviewer_patches(data, patches) -> tuple[list, list]:
    """진보 리뷰어가 제안한 패치를 원고에 적용한다.

    가드: 적용 후 **새로운** high 위반이 생기면 되돌린다.
    (리뷰 패치는 개선 제안이라 기존 위반을 고치지 않을 수도 있다 —
     '위반이 줄었는가'로 판정하면 정당한 개선까지 되돌리게 된다)
    """
    applied, notes = [], []
    for p in patches or []:
        card_no = p.get("card")
        setter = p.get("set") or {}
        if not isinstance(card_no, int) or not isinstance(setter, dict) or not setter:
            continue
        if card_no < 1:
            notes.append(f"리뷰 패치 카드번호 무효({card_no}) — 1-based 여야 함, 건너뜀")
            continue
        idx = card_no - 1
        if not (0 <= idx < len(data.get("cards", []))):
            notes.append(f"리뷰 패치 카드번호 범위 초과({card_no}) — 건너뜀")
            continue
        def _high():
            return {f"{x.get('rule')}|{x.get('detail')}"
                    for x in R.evaluate(data) if x.get("severity") == "high"}

        before = _high()
        original_cards = copy.deepcopy(data["cards"])
        for k, v in setter.items():
            data["cards"][idx][k] = v
        new_violations = _high() - before

        # 새 위반이 '숫자 불일치'뿐이면 패치를 버리지 말고 결정론 fixer 로 교정한다.
        # (진보 리뷰어가 좋은 후킹을 냈는데 차트에 없는 숫자 하나 때문에 통째로
        #  버려지는 낭비를 막는다 — 예: 커버 90% → 차트 정본 93% 로 치환)
        if new_violations and all(v.startswith("numeric-consistency|") for v in new_violations):
            fixed = fix_cover_numbers(data) + fix_gap_values(data)
            if fixed and not (_high() - before):
                new_violations = set()
                notes.append(f"{card_no}번 리뷰 패치 — 숫자를 차트 정본으로 교정: {', '.join(fixed)}")

        if new_violations:
            data["cards"] = original_cards
            notes.append(f"{card_no}번 리뷰 패치가 새 위반을 만들어 되돌림")
        else:
            applied.append(f"{card_no}번 리뷰 패치 적용 ({', '.join(setter.keys())})")
    return applied, notes


# ── 결론 카드 삽입 (인사이트 바로 앞) ────────────────────────
#
# 왜 필요한가: 사용자 요구로 발행 때마다 '실무자 인사이트' 앞에 서머리 성격의
# '결론' 카드가 들어간다. 그런데 llm_pass / apply_reviewer_patches 는 **기존 카드의
# 필드만** 고칠 수 있어서 '없는 카드를 넣는' 일은 못 한다. 그래서 삽입 전용 경로를 둔다.

CONCLUSION_HEADING = "이것만 가져가시면 됩니다"   # 매회 고정 — 시리즈 인식용

CONCLUSION_PROMPT = """당신은 한국어 AI 교육 카드뉴스의 편집자입니다.
아래 원고 전체를 읽고, **마지막 '실무자 인사이트' 카드 바로 앞에 들어갈 '결론' 카드 하나**를 쓰세요.

역할: 독자가 **가져갈 것만 딱 추려주는** 카드. 이 카드만 봐도 핵심을 다 얻어야 합니다.
'글 전체 요약'이 아니라 **'이것만 가져가라'** 는 태도로 쓰세요.

규칙:
- 한국어만. 일본어/중국어 금지.
- heading 은 **반드시 "이것만 가져가시면 됩니다"** 로 고정한다. 매회 동일하게 쓴다.
- body 는 90자 이하 한 문장 — 글 전체를 관통하는 결론 한 줄.
- bullets 는 3~4개. 각 55자 이하. 각 항목은 서로 다른 축(원리/수치/적용)을 담아라.
  bullets 는 "독자가 들고 갈 것" 목록이므로 명사형/단정형으로 끊어 써라.
- **원고에 없는 숫자를 새로 만들지 마라.** 원고에 나온 수치만 인용한다.
- 원고에 있는 수치·개념을 쓰되, 본문을 그대로 복사하지는 마라. 요약이다.

출력은 JSON 객체 하나만. 설명·마크다운·코드펜스 금지:
{"type":"conclusion","label":"결론","heading":"이것만 가져가시면 됩니다","body":"<90자 이하 한 문장>","bullets":["<55자 이하>","<55자 이하>","<55자 이하>"]}
"""


def llm_write_conclusion(data, timeout=150):
    """원고를 읽고 결론 카드 하나를 LLM으로 작성한다. 실패 시 (None, 사유)."""
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        return None, "OPENROUTER_API_KEY 없음"
    model = os.environ.get("REVIEW_MODEL_PROGRESSIVE") or "anthropic/claude-sonnet-4.5"
    slim = {
        "topic": data.get("topic"),
        "cards": [{"i": i, "type": c.get("type", "body"),
                   "heading": c.get("heading"), "title": c.get("title"),
                   "body": c.get("body"), "lead": c.get("lead"),
                   "subtitle": c.get("subtitle")}
                  for i, c in enumerate(data.get("cards", []), 1)],
    }
    try:
        import requests
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json={"model": model, "temperature": 0.2, "max_tokens": 1200,
                  "messages": [{"role": "user", "content":
                                CONCLUSION_PROMPT + "\n\n원고:\n"
                                + json.dumps(slim, ensure_ascii=False, indent=1)[:9000]}]},
            timeout=timeout,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}: {r.text[:140]}"
        txt = r.json()["choices"][0]["message"].get("content") or ""
        txt = re.sub(r"^```(?:json)?|```$", "", txt.strip(), flags=re.M).strip()
        i, j = txt.find("{"), txt.rfind("}")
        if i < 0 or j <= i:
            return None, "JSON 없음"
        card = json.loads(txt[i:j + 1])
        card["type"] = "conclusion"
        card.setdefault("label", "결론")
        card["heading"] = CONCLUSION_HEADING      # 매회 고정 (LLM 이 다르게 써도 덮어씀)
        if not (card.get("heading") or card.get("body") or card.get("bullets")):
            return None, "빈 결론 카드"
        return card, None
    except Exception as e:                                      # noqa: BLE001
        return None, f"{type(e).__name__}: {str(e)[:140]}"


def insert_conclusion(data, verbose=True) -> tuple[list, list]:
    """인사이트 바로 앞에 결론 카드를 삽입한다. 이미 있으면 아무것도 안 한다.

    가드: 삽입 후 **새로운** high 위반이 생기면 되돌린다.
    """
    applied, notes = [], []
    cards = data.get("cards", [])
    ins_idx = next((i for i, c in enumerate(cards)
                    if c.get("type") == "insight"), None)
    if ins_idx is None or ins_idx == 0:
        return applied, notes
    if cards[ins_idx - 1].get("type") == "conclusion":
        return applied, notes                       # 이미 있음

    card, err = llm_write_conclusion(data)
    if err or not card:
        notes.append(f"결론 카드 생성 실패: {err}")
        return applied, notes

    before = {f"{x.get('rule')}|{x.get('detail')}"
              for x in R.evaluate(data) if x.get("severity") == "high"}
    original = copy.deepcopy(cards)
    cards.insert(ins_idx, card)
    new_high = {f"{x.get('rule')}|{x.get('detail')}"
                for x in R.evaluate(data) if x.get("severity") == "high"} - before
    if new_high:
        data["cards"] = original
        notes.append(f"결론 카드가 새 위반을 만들어 되돌림: {list(new_high)[0][:80]}")
    else:
        applied.append(f"{ins_idx}번 자리에 결론 카드 삽입 "
                       f"(heading='{card.get('heading','')}')")
        if verbose:
            print(f"    ➕ 결론 카드 삽입: {card.get('heading','')}")
    return applied, notes


# ── 메인 루프 ────────────────────────────────────────────────

def run(slug: str, rounds=2, use_llm=True, verbose=True):
    path = ROOT / "content" / "queue" / f"{slug}.json"
    if not path.exists():
        sys.exit(f"원고가 없습니다: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))

    history = []
    llm_issues, reviewer_patches, summaries = [], [], {}

    # ── 0) 결론 카드 삽입 — 인사이트 바로 앞 (반드시 리뷰보다 먼저) ──
    # 리뷰 뒤에 넣으면 카드 인덱스가 밀려서 리뷰 패치가 엉뚱한 카드에 붙는다.
    # 리뷰어는 디스크에서 원고를 다시 읽으므로, 삽입했으면 파일에 먼저 쓴다.
    if use_llm:
        if verbose:
            print("── 0) 결론 카드 확인 (인사이트 바로 앞) ──")
        ap0, nt0 = insert_conclusion(data, verbose=verbose)
        for n in nt0:
            print(f"    ⚠️  {n}")
        if ap0:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                            encoding="utf-8")
            history.append({"round": "conclusion", "applied": ap0})
        elif verbose:
            print("    ✓ 결론 카드 있음 (또는 삽입 불필요)")

    # ── 1) 리뷰 — 진보/보수 리뷰어 ──────────────────────────
    if use_llm:
        if verbose:
            print("── 1) 리뷰 (진보/보수 2리뷰어) ──")
        llm_issues, reviewer_patches, summaries = run_reviewer(slug)
        for k, v in summaries.items():
            if v:
                print(f"    [{k}] {v}")
        if verbose:
            print(f"    → 지적 {len(llm_issues)}건 · 카드 패치 {len(reviewer_patches)}건")

    # ── 2) 리뷰 반영 — 진보 리뷰어의 카드 패치 적용 ─────────
    if reviewer_patches:
        if verbose:
            print("── 2) 리뷰 반영 (제안 패치 적용) ──")
        ap, nt = apply_reviewer_patches(data, reviewer_patches)
        for a in ap:
            print(f"    ✏️  {a}")
        for n in nt:
            print(f"    ⚠️  {n}")
        history.append({"round": 0, "reviewer_patches": ap, "notes": nt})

    # ── 3) 결정론 수정 + 룰 위반 해소 ───────────────────────
    for rnd in range(1, rounds + 1):
        high = [i for i in R.evaluate(data) if i.get("severity") == "high"]
        if verbose:
            print(f"── 3) 라운드 {rnd}: high 위반 {len(high)}건 ──")
        if not high:
            break

        applied = deterministic_pass(data)
        for a in applied:
            print(f"    ✏️  {a}")

        remaining = [i for i in R.evaluate(data) if i.get("severity") == "high"]
        llm_applied, notes = [], []
        if remaining and use_llm:
            real = [i for i in remaining if not is_false_positive(i)]
            for s in [i for i in remaining if is_false_positive(i)]:
                if verbose:
                    print(f"    🚫 오판 제외: {s.get('detail','')[:70]}")
            if real:
                llm_applied, notes = llm_pass(data, real)
                for a in llm_applied:
                    print(f"    🤖 {a}")
                for n in notes:
                    print(f"    ⚠️  {n}")

        history.append({"round": rnd, "deterministic": applied,
                        "llm": llm_applied, "notes": notes})
        if not applied and not llm_applied:
            if verbose:
                print("    (더 고칠 것이 없음)")
            break

    # ── 4) 리뷰어 지적 카드 수정 (룰 위반이 없어도 반영) ────
    if use_llm and llm_issues:
        real = [i for i in llm_issues if not is_false_positive(i)]
        if verbose:
            print(f"── 4) 리뷰 지적 반영 ({len(real)}건) ──")
        ap, nt = llm_pass(data, real)
        for a in ap:
            print(f"    🤖 {a}")
        for n in nt:
            print(f"    ⚠️  {n}")
        for s in [i for i in llm_issues if is_false_positive(i)]:
            if verbose:
                print(f"    🚫 오판 제외: {s.get('detail','')[:70]}")
        history.append({"round": "review-fix", "llm": ap, "notes": nt})

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
