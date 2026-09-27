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
MIN_VISUAL_RATIO = 0.4          # 시각화 카드 최소 비율
VISUAL_TYPES = ("visual", "diagram", "table", "chart", "compare", "flow")

# 1 빌더 + 2 리뷰어 구조 (영상: Claude=진보 / OpenRouter·NVIDIA=보수 게이트키퍼)
REVIEWERS = {
    "progressive": os.environ.get("REVIEW_MODEL_PROGRESSIVE")
    or os.environ.get("REVIEW_MODEL") or "anthropic/claude-sonnet-4",
    "conservative": os.environ.get("REVIEW_MODEL_CONSERVATIVE")
    or "deepseek/deepseek-v4-flash",
}

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

PROGRESSIVE_PROMPT = """당신은 한국어 AI 교육 카드뉴스의 수석 리뷰어입니다.
역할: **진보적 리뷰어** — 오류 지적뿐 아니라 "어떻게 하면 더 좋아지는가"를 적극 제안합니다.

검수 기준:
1. 사실 정확성 — AI/ML 개념 설명이 틀렸거나 과장됐는지
2. 설명 충분성 — 그림만 있고 설명이 빈약하지 않은지
3. 후킹 — 커버 제목이 3줄 도발·단정형인지
4. 언어 — 한국어만 사용(일본어/중국어 금지)
5. 카드 완결성 — type=visual 인데 시각화 페이로드가 비어 있지 않은지
6. 캡션 — 첫 문장이 후킹인지
7. 개선 제안 — 더 좋은 비유, 더 강한 수치 예시, 빠진 관점

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

CONSERVATIVE_PROMPT = """당신은 한국어 AI 교육 카드뉴스의 **보수적 게이트키퍼 리뷰어**입니다.
역할: 관대하게 넘기지 말고, 발행을 막아야 할 결함을 찾아내는 것이 임무입니다.
확신이 없으면 지적하지 말고, 근거를 대라 수 있는 결함만 보고하세요.

검수 기준(엄격):
1. 사실 정확성 — 논문/연도/버전/모델명 등 출처 표기가 틀렸거나 검증 불가능하면 지적
2. 과장·단정 — 근거 없는 최상급·절대 표현("무조건", "100%", "역대 최고") 지적
3. 내부 모순 — 카드 간 수치·서술이 서로 어긋나는지
4. 설명 충분성 — 그림만 있고 설명이 부족한 카드
5. 언어 — 한국어만 (일본어/중국어 금지)
6. 시각화 카드에 렌더 가능한 페이로드가 있는지

출력: JSON 객체 하나만. 사고 과정·설명·마크다운·영어/중국어 금지.
{"verdict":"pass|fix|block","summary":"한 줄","issues":[{"card":<번호>,"type":"<종류>","severity":"high|medium|low","detail":"<근거 포함 설명>"}]}
문제 없으면 issues를 빈 배열로. patches 는 출력하지 마라 (게이트키퍼는 판정만 한다)."""

PROMPTS = {"progressive": PROGRESSIVE_PROMPT, "conservative": CONSERVATIVE_PROMPT}


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


def llm_review(data, role="progressive", timeout=180):
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return None, "OPENROUTER_API_KEY 없음 (룰 검사만 수행)"

    model = REVIEWERS.get(role)
    prompt = PROMPTS.get(role, PROGRESSIVE_PROMPT)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(
                {k: v for k, v in data.items() if k != "user_profile"},
                ensure_ascii=False)[:14000]},
        ],
        "temperature": 0.1 if role == "conservative" else 0.3,
        "max_tokens": 3000,
        "response_format": {"type": "json_object"},
    }
    try:
        r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                          json=payload, timeout=timeout,
                          headers={"Authorization": f"Bearer {key}",
                                   "Content-Type": "application/json"})
        if r.status_code != 200:
            return None, f"[{role}] {model} HTTP {r.status_code}: {r.text[:160]}"
        txt = r.json()["choices"][0]["message"]["content"]
        parsed = _loads_lenient(txt)
        if parsed is None:
            dbg = ROOT / "out" / f"_review_raw_{role}.txt"
            dbg.parent.mkdir(parents=True, exist_ok=True)
            dbg.write_text(txt, encoding="utf-8")
            return None, f"[{role}] JSON 파싱 실패 (원문: {dbg})"
        parsed["_model"] = model
        return parsed, None
    except Exception as e:                                  # noqa: BLE001
        return None, f"[{role}] LLM 검수 실패: {type(e).__name__}: {str(e)[:140]}"


def rule_fixes(data):
    """결정적으로 안전한 수정만. (LLM 패치는 절대 여기서 적용하지 않는다)"""
    patches = []
    cards = data.get("cards", [])
    if cards and cards[0].get("type") == "cover":
        title = (cards[0].get("title") or "").strip()
        if title and "\n" not in title and len(title) > 10:
            words = title.split()
            if len(words) >= 4:
                n = len(words)
                a, b = round(n / 3), round(2 * n / 3)
                new = "\n".join([" ".join(words[:a]), " ".join(words[a:b]),
                                 " ".join(words[b:])]).strip()
                if new.count("\n") == 2:
                    patches.append({"card": 1, "set": {"title": new},
                                    "why": "커버 제목 3줄 분할 (기계적)"})
    return patches


def save_suggestions(slug, patches, summary):
    """LLM 패치는 적용하지 않고 제안 파일로만 남긴다."""
    if not patches:
        return None
    dest = ROOT / "out" / "review_suggestions" / f"{slug}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"slug": slug, "summary": summary,
                                "suggested_patches": patches},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    return dest


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

def review(slug, fix=False, rules_only=False, roles=None):
    roles = roles or ["progressive", "conservative"]
    data = q.load(slug)
    rule_issues = rule_check(data)

    llm_issues, patches, summaries, errors, models = [], [], {}, [], {}
    if not rules_only:
        for role in roles:
            parsed, err = llm_review(data, role=role)
            if err or not isinstance(parsed, dict):
                errors.append(err or f"[{role}] 빈 응답")
                continue
            models[role] = parsed.get("_model", REVIEWERS.get(role))
            summaries[role] = parsed.get("summary", "")
            for i in (parsed.get("issues") or []):
                i["source"] = role
                llm_issues.append(i)
            if role == "progressive":
                patches = parsed.get("patches") or []

    # 합의(consensus): 두 리뷰어가 같은 카드를 지적 → 신뢰도 상승
    by_card = {}
    for i in llm_issues:
        by_card.setdefault(i.get("card"), set()).add(i.get("source"))
    for i in llm_issues:
        if len(by_card.get(i.get("card"), ())) > 1:
            i["consensus"] = True

    # verdict 는 룰 검사가 결정한다. LLM 차단은 기본 OFF
    # (두 모델이 같은 학습 컷오프로 같은 환각을 낼 수 있음 — 예: "2026년은 미래")
    llm_block = os.environ.get("REVIEW_LLM_BLOCK", "").lower() in ("1", "true", "yes")
    consensus_high = any(i.get("consensus") and i.get("severity") == "high" for i in llm_issues)
    if any(i["severity"] == "high" for i in rule_issues) or (llm_block and consensus_high):
        verdict = "block"
    elif rule_issues or llm_issues:
        verdict = "fix"
    else:
        verdict = "pass"

    issues = rule_issues + llm_issues

    # LLM 패치는 자동 적용하지 않는다 (환각 위험) — 제안 파일로만 남긴다.
    sug = save_suggestions(slug, patches, summaries.get("progressive", "")) if patches else None

    applied = []
    if fix and verdict != "block":
        rp = rule_fixes(data)
        if rp:
            applied = apply_patches(data, rp)
            path = ROOT / "content" / "queue" / f"{slug}.json"
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                            encoding="utf-8")
            rule_issues = rule_check(data)
            if any(i["severity"] == "high" for i in rule_issues):
                verdict = "block"
            elif rule_issues or llm_issues:
                verdict = "fix"
            else:
                verdict = "pass"
            issues = rule_issues + llm_issues

    return {"slug": slug, "verdict": verdict, "summaries": summaries,
            "summary": " / ".join(f"[{k}] {v}" for k, v in summaries.items() if v),
            "models": models, "issues": issues, "patches": patches,
            "applied": applied, "suggestions_file": str(sug) if sug else None,
            "llm_errors": errors, "llm_error": " ; ".join(errors) if errors else None}


ROLE_LABEL = {"progressive": "진보", "conservative": "보수"}


def report(res, verbose=True):
    icon = {"pass": "✅", "fix": "🟡", "block": "❌"}.get(res["verdict"], "❓")
    print(f"{icon} {res['slug']} — {res['verdict'].upper()}")
    for role, model in (res.get("models") or {}).items():
        print(f"    {ROLE_LABEL.get(role, role)} 리뷰어: {model}")
    if res.get("summary"):
        print(f"    총평: {res['summary']}")
    if res.get("llm_error"):
        print(f"    (LLM 생략: {res['llm_error']})")
    if verbose:
        for i in res["issues"]:
            c = f"{i['card']}번 " if i.get("card") else ""
            src = ROLE_LABEL.get(i.get("source"), "")
            tags = ""
            if src:
                tags = f"[{src}] "
            if i.get("consensus"):
                tags += "[합의⭐] "
            print(f"    {tags}[{i['severity']}] {c}{i['type']}: {i['detail']}")
        for a in res.get("applied", []):
            print(f"    ✏️  적용됨: {a}")
        if res.get("suggestions_file"):
            print(f"    📄 LLM 제안 저장됨(미적용): {res['suggestions_file']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--fix", action="store_true", help="LLM 패치를 원고에 적용")
    ap.add_argument("--rules-only", action="store_true", help="LLM 없이 룰 검사만")
    ap.add_argument("--reviewer", default="both",
                    choices=["both", "progressive", "conservative"],
                    help="LLM 리뷰어 선택 (기본 both: 진보+보수)")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    roles = {"both": ["progressive", "conservative"],
             "progressive": ["progressive"],
             "conservative": ["conservative"]}[a.reviewer]

    slugs = q.all_slugs() if a.all else [a.slug or q.next_slug()]
    slugs = [s for s in slugs if s]
    if not slugs:
        sys.exit("검수할 원고가 없습니다.")

    worst = 0
    for s in slugs:
        try:
            res = review(s, fix=a.fix, rules_only=a.rules_only, roles=roles)
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
