#!/usr/bin/env python3
"""원고 형식 검사. 발행 전에 걸러야 할 실수를 잡는다."""

import json
import sys

import postqueue as q

MAX_CAPTION = 2200      # 인스타 캡션 상한
MAX_HASHTAGS = 30       # 인스타 해시태그 상한
REQUIRED = 10           # 캐러셀 카드 수


def check(slug):
    errs, warns = [], []
    try:
        d = q.load(slug)
    except json.JSONDecodeError as e:
        return [f"JSON 문법 오류: {e}"], []

    cards = d.get("cards", [])
    if len(cards) != REQUIRED:
        errs.append(f"카드가 {len(cards)}장입니다. 정확히 {REQUIRED}장이어야 합니다.")

    if cards and cards[0].get("type") != "cover":
        errs.append("첫 카드는 type이 'cover' 여야 합니다.")
    if not any(c.get("type") == "insight" for c in cards):
        warns.append("insight 카드가 없습니다.")
    if cards and not cards[-1].get("cta"):
        warns.append("마지막 카드에 cta(다음 편 예고)가 없습니다.")

    for i, c in enumerate(cards, 1):
        t = c.get("type", "body")
        if t == "cover":
            if not c.get("title"):
                errs.append(f"{i}번 카드: title 없음")
            if len(c.get("title", "")) > 30:
                warns.append(f"{i}번 카드: 표지 제목이 {len(c['title'])}자로 깁니다 (30자 이하 권장)")
        else:
            if not c.get("heading"):
                errs.append(f"{i}번 카드: heading 없음")
            if len(c.get("heading", "")) > 26:
                warns.append(f"{i}번 카드: heading {len(c['heading'])}자 (26자 이하 권장)")
            body_len = len(c.get("body", ""))
            if body_len > 220:
                warns.append(f"{i}번 카드: 본문 {body_len}자 — 글자가 작게 축소될 수 있습니다")

    cap = d.get("caption", "")
    tags = d.get("hashtags", [])
    full = len(cap) + len(" ".join(tags)) + 8
    if full > MAX_CAPTION:
        errs.append(f"캡션+해시태그가 {full}자입니다 (상한 {MAX_CAPTION}자)")
    if len(tags) > MAX_HASHTAGS:
        errs.append(f"해시태그가 {len(tags)}개입니다 (상한 {MAX_HASHTAGS}개)")
    bad = [t for t in tags if not t.startswith("#")]
    if bad:
        errs.append(f"'#'로 시작하지 않는 해시태그: {bad}")

    for f in ("topic", "handle", "caption"):
        if not d.get(f):
            errs.append(f"필수 필드 누락: {f}")

    return errs, warns


def main():
    slugs = sys.argv[1:] or q.all_slugs()
    failed = False
    for s in slugs:
        errs, warns = check(s)
        status = "❌" if errs else ("⚠️ " if warns else "✅")
        print(f"{status} {s}")
        for e in errs:
            print(f"    오류: {e}")
        for w in warns:
            print(f"    주의: {w}")
        failed |= bool(errs)
    if failed:
        sys.exit(1)
    print(f"\n검사 완료 · 총 {len(slugs)}편 · 발행 대기 {q.remaining()}편")


if __name__ == "__main__":
    main()
