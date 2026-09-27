#!/usr/bin/env python3
"""contentreviewer — 원고 LLM 검수 에이전트.

파이프라인 (영상의 AI Native Company OS 구조):
    contentorchestrator
      ├─ contentwriter   (growth_generate.py / 원고 생성)
      ├─ contentreviewer  ← 이 파일 (draft 검수 + 자동 수정)
      └─ render → publish

2단계로 검수한다.
  1) 룰 검사 (결정적): 빈 카드, 언어 오염(일본어/중국어), 시각화 비율, 필수 필드
  2) LLM 검수: 내용 정확성·후킹·설명 충분성 → verdict + 카드 패치 제안

사용법:
  python content_reviewer.py --slug 049-batch-inference-continuous-batching
  python content_reviewer.py --all
  python content_reviewer.py --slug X --fix        # LLM 패치를 원고에 적용
  python content_reviewer.py --slug X --rules-only # LLM 없이 룰 검사만

종료 코드: 0=통과, 1=차단(block), 2=수정 필요(fix)
"""

import argparse
import json
import os
import pathlib
import re
import sys

import requests

import postqueue as q

ROOT = pathlib.Path(__file__).resolve().parent.parent
MODEL = os.environ.get("REVIEW_MODEL") or "google/gemini-2.5-flash"
MIN_VISUAL_RATIO = 0.4          # 시각화 카드 최소 비율
VISUAL_TYPES = ("visual", "diagram", "table", "chart", "compare", "flow")

# 일본어 가나 / 한자 (한글과 코드 범위가 겹치지 않음)
CJK_RE = re.compile(r"[\u3040-\u309f\u30a0-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uff66-\uff9f]")
ALLOWED_CJK = set()             # 필요 시 허용 문자 추가


# ── 1단계: 룰 검사 ──────────────────────────────────────────

def has_visual(card):
    """시각화 카드에 실제 렌더할 페이로드가 있는지."""
    return bool(card.get("visual") or card.get("data") or card.get("diagram"))


def card_text(card):
    parts = [card.get("title"), card.get("heading"), card.get("body"), card.get("lead")]
    parts += list(card.get("bullets") or [])
    return " ".join(str(p) for p in parts if p)


def rule_check(data):
    issues = []
    cards = data.get("cards", [])

    for i, c in enumerate(cards, 1):
        text = card_text(c).strip()
        # 빈 카드
        if not text and not has_visual(c):
            issues.append({"card": i, "type": "empty_card", "severity": "high",
                           "detail": "제목·본문·데이터가 모두 비어 있습니다."})
        # 언어 오염
        bad = sorted({ch for ch in text if CJK_RE.match(ch)} - ALLOWED_CJK)
        if bad:
            issues.append({"card": i, "type": "language", "severity": "high",
                           "detail": f"일본어/중국어 문자 발견: {' '.join(bad[:10])}"})
        # visual 타입인데 실제 데이터 없음
        if c.get("type") in VISUAL_TYPES and not has_visual(c):
            issues.append({"card": i, "type": "visual_no_data", "severity": "high",
                           "detail": f"type={c.get('type')} 인데 data/diagram 이 없어 빈 카드로 렌더됩니다."})
        # heading 길이
        if c.get("type") not in ("cover", "insight", "cta", "outro") and not c.get("heading"):
            issues.append({"card": i, "type": "no_heading", "severity": "low",
                           "detail": "heading 이 없습니다."})

    # 커버 후킹 (3줄 도발형)
    if cards and cards[0].get("type") == "cover":
        title = cards[0].get("title", "")
        if "\n" not in title:
            issues.append({"card": 1, "type": "hook_weak", "severity": "medium",
                           "detail": "커버 제목이 한 줄입니다. 3줄 도발형(\\n 2개) 권장."})

    # 시각화 비율
    if cards:
        n_visual = sum(1 for c in cards
                       if c.get("type") in VISUAL_TYPES and has_visual(c))
        ratio = n_visual / len(cards)
        if ratio < MIN_VISUAL_RATIO:
            issues.append({"card": 0, "type": "visual_ratio", "severity": "medium",
                           "detail": f"시각화 {n_visual}/{len(cards)}장 ({ratio:.0%}) — 최소 {MIN_VISUAL_RATIO:.0%} 권장"})

    for f in ("topic", "handle", "caption"):
        if not data.get(f):
            issues.append({"card": 0, "type": "missing_field", "severity": "high",
                           "detail": f"필수 필드 누락: {f}"})
    return issues


# ── 2단계: LLM 검수 ────────────────────────────────────────

REVIEW_PROMPT = """당신은 한국어 AI 교육 카드뉴스의 수석 리뷰어입니다.
아래 원고(JSON)를 검수하고, 발견한 문제를 JSON으로만 답하세요.

검수 기준:
1. 사실 정확성 — AI/ML 개념 설명이 틀렸거나 과장됐는지
2. 설명 충분성 — 그림만 있고 설명이 빈약하지 않은지
3. 후킹 — 커버 제목이 3줄 도발·단정형인지
4. 언어 — 한국어만 사용(일본어/중국어 금지)
5. 카드 완결성 — type=visual 인데 data/diagram 이 비어 있지 않은지
6. 캡션 — 첫 문장이 후킹인지

출력 형식(JSON만, 다른 텍스트 금지):
{
  "verdict": "pass" | "fix" | "block",
  "summary": "한 줄 총평",
  "issues": [{"card": <번호>, "type": "<종류>", "severity": "high|medium|low", "detail": "<설명>"}],
  "patches": [{"card": <번호>, "set": {"<필드>": "<새 값>"}}]
}
- 문제가 없으면 issues/patches 를 빈 배열로.
- patches 는 실제로 고칠 수 있는 것만 (문구 교정, 빈 heading 채우기 등).
- 개념 자체가 틀렸으면 verdict=block, patches 없이 이유만.
"""


def _loads_lenient(txt):
    """LLM이 뱉은 JSON을 최대한 살려서 파싱한다."""
    txt = re.sub(r"^```(?:json)?|```$", "", (txt or "").strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(txt)
    except Exception:                                       # noqa: BLE001
        pass
    i, j = txt.find("{"), txt.rfind("}")
    if i == -1 or j <= i:
        return None
    cand = txt[i:j + 1]
    attempts = [
        cand,
        re.sub(r",\s*([}\]])", r"\1", cand),                            # 꼬리 쉼표
        re.sub(r"(?<!\\)\n", " ", re.sub(r",\s*([}\]])", r"\1", cand)),  # + 원시 줄바꿈
        re.sub(r'(\w)"(\s*[:,\]}])', r"\1'", cand),                      # 잘못된 따옴표
    ]
    for a in attempts:
        try:
            return json.loads(a)
        except Exception:                                   # noqa: BLE001
            continue
    return None


def llm_review(data, timeout=120):
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return None, "OPENROUTER_API_KEY 없음 (룰 검사만 수행)"

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": REVIEW_PROMPT},
            {"role": "user", "content": json.dumps(
                {k: v for k, v in data.items() if k != "user_profile"},
                ensure_ascii=False)[:14000]},
        ],
        "temperature": 0.2,
        "max_tokens": 2000,
        "response_format": {"type": "json_object"},
    }
    try:
        r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                          json=payload, timeout=timeout,
                          headers={"Authorization": f"Bearer {key}",
                                   "Content-Type": "application/json"})
        if r.status_code != 200:
            return None, f"LLM HTTP {r.status_code}: {r.text[:200]}"
        txt = r.json()["choices"][0]["message"]["content"]
        parsed = _loads_lenient(txt)
        if parsed is None:
            dbg = ROOT / "out" / "_review_raw.txt"
            dbg.parent.mkdir(parents=True, exist_ok=True)
            dbg.write_text(txt, encoding="utf-8")
            return None, f"JSON 파싱 실패 (원문 저장: {dbg})"
        return parsed, None
    except Exception as e:                                  # noqa: BLE001
        return None, f"LLM 검수 실패: {type(e).__name__}: {str(e)[:160]}"


def apply_patches(data, patches):
    applied = []
    cards = data.get("cards", [])
    for p in patches or []:
        idx = p.get("card")
        sets = p.get("set") or {}
        if not isinstance(idx, int) or not (1 <= idx <= len(cards)) or not sets:
            continue
        cards[idx - 1].update(sets)
        applied.append(f"{idx}번 카드 ← {', '.join(sets.keys())}")
    return applied


# ── 오케스트레이션 ────────────────────────────────────────

def review(slug, fix=False, rules_only=False):
    data = q.load(slug)
    rule_issues = rule_check(data)
    llm, err = (None, None) if rules_only else llm_review(data)

    issues = list(rule_issues)
    patches = []
    summary = ""
    llm_issues = []
    if llm:
        llm_issues = llm.get("issues", []) or []
        for i in llm_issues:
            i["source"] = "llm"
        patches = llm.get("patches", []) or []
        summary = llm.get("summary", "")

    # 룰 검사만 verdict 를 결정한다 (LLM 은 자문).
    # LLM 환각으로 정상 원고를 차단하지 않기 위함.
    if any(i["severity"] == "high" for i in rule_issues):
        verdict = "block"
    elif rule_issues or (llm and llm.get("verdict") in ("fix", "block")):
        verdict = "fix"
    else:
        verdict = "pass"

    issues += llm_issues

    applied = []
    if fix and patches and verdict != "block":
        applied = apply_patches(data, patches)
        if applied:
            path = ROOT / "content" / "queue" / f"{slug}.json"
            backup = path.with_suffix(".json.reviewbak")
            backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"slug": slug, "verdict": verdict, "summary": summary,
            "issues": issues, "patches": patches, "applied": applied, "llm_error": err}


def report(res, verbose=True):
    icon = {"pass": "✅", "fix": "🟡", "block": "❌"}.get(res["verdict"], "❓")
    print(f"{icon} {res['slug']} — {res['verdict'].upper()}"
          + (f" · {res['summary']}" if res["summary"] else ""))
    if res.get("llm_error"):
        print(f"    (LLM 생략: {res['llm_error']})")
    if verbose:
        for i in res["issues"]:
            c = f"{i['card']}번 " if i.get("card") else ""
            tag = "[LLM·검증필요] " if i.get("source") == "llm" else ""
            print(f"    {tag}[{i['severity']}] {c}{i['type']}: {i['detail']}")
        for a in res.get("applied", []):
            print(f"    ✏️  적용됨: {a}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--fix", action="store_true", help="LLM 패치를 원고에 적용")
    ap.add_argument("--rules-only", action="store_true", help="LLM 없이 룰 검사만")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    slugs = q.all_slugs() if a.all else [a.slug or q.next_slug()]
    slugs = [s for s in slugs if s]
    if not slugs:
        sys.exit("검수할 원고가 없습니다.")

    worst = 0
    for s in slugs:
        try:
            res = review(s, fix=a.fix, rules_only=a.rules_only)
        except Exception as e:                              # noqa: BLE001
            print(f"❌ {s} — 검수 중 예외: {type(e).__name__}: {e}")
            worst = max(worst, 1)
            continue
        report(res, verbose=not a.quiet)
        worst = max(worst, {"pass": 0, "fix": 2, "block": 1}[res["verdict"]])

    if worst:
        sys.exit(worst)


if __name__ == "__main__":
    main()
