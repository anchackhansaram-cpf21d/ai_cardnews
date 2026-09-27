#!/usr/bin/env python3
"""피드백 루프 — 발행물에 대한 인간 피드백을 적재한다 (L2 클로즈드 루프).

영상의 "슬랙 이모지 피드백 → DB 적재" 를 텔레그램으로 이식한 것.

사용법:
  python feedback.py add --slug 044-softmax-temperature --vote good
  python feedback.py add --slug 044-... --vote bad --note "설명이 너무 짧고 수식이 없다"
  python feedback.py add --vote bad --note "..."            # slug 생략 가능(최근 발행분)
  python feedback.py list [--limit 20]
  python feedback.py summary
  python feedback.py lessons          # L3 자가개선 반영용 (거절 패턴)
"""

import argparse
import datetime
import json
import pathlib
import sys
import zoneinfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
STORE = ROOT / "analytics" / "feedback.jsonl"
KST = zoneinfo.ZoneInfo("Asia/Seoul")


def now_kst():
    return datetime.datetime.now(KST).isoformat(timespec="seconds")


def read_all():
    if not STORE.exists():
        return []
    out = []
    for line in STORE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def last_posted_slug():
    try:
        state = json.loads((ROOT / "state.json").read_text(encoding="utf-8"))
        posted = state.get("posted") or []
        return posted[-1] if posted else None
    except Exception:                                       # noqa: BLE001
        return None


def add(slug, vote, note, source="cli"):
    vote = (vote or "").lower()
    if vote not in ("good", "bad"):
        return None, "vote 는 good 또는 bad 여야 합니다."
    slug = slug or last_posted_slug() or "unknown"
    rec = {"ts": now_kst(), "slug": slug, "vote": vote,
           "note": (note or "").strip(), "source": source}
    STORE.parent.mkdir(parents=True, exist_ok=True)
    with STORE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec, None


def summary():
    rows = read_all()
    if not rows:
        return {"total": 0, "good": 0, "bad": 0, "rate": None, "bad_notes": []}
    good = sum(1 for r in rows if r["vote"] == "good")
    bad = sum(1 for r in rows if r["vote"] == "bad")
    recent_bad = [r for r in rows if r["vote"] == "bad"][-10:]
    return {"total": len(rows), "good": good, "bad": bad,
            "rate": good / len(rows) * 100,
            "bad_notes": [f"{r['slug']}: {r['note']}" for r in recent_bad if r["note"]]}


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add")
    a.add_argument("--slug")
    a.add_argument("--vote", required=True, choices=["good", "bad"])
    a.add_argument("--note", default="")
    a.add_argument("--source", default="cli")

    l = sub.add_parser("list")
    l.add_argument("--limit", type=int, default=20)

    sub.add_parser("summary")
    sub.add_parser("lessons")

    args = ap.parse_args()

    if args.cmd == "add":
        rec, err = add(args.slug, args.vote, args.note, args.source)
        if err:
            sys.exit(err)
        icon = "👍" if rec["vote"] == "good" else "❌"
        print(f"{icon} 기록됨 · {rec['slug']} · {rec['ts']}")
        if rec["note"]:
            print(f"   메모: {rec['note']}")
        s = summary()
        print(f"   누적: 좋아요 {s['good']} / 별로 {s['bad']} (총 {s['total']})")

    elif args.cmd == "list":
        rows = read_all()[-args.limit:]
        if not rows:
            print("기록 없음")
        for r in rows:
            icon = "👍" if r["vote"] == "good" else "❌"
            print(f"{icon} {r['ts']}  {r['slug']}  {r['note']}")

    elif args.cmd == "summary":
        s = summary()
        if not s["total"]:
            print("피드백 없음")
        else:
            print(f"총 {s['total']}건 · 👍 {s['good']} · ❌ {s['bad']} "
                  f"(만족도 {s['rate']:.0f}%)")
            if s["bad_notes"]:
                print("최근 ❌ 사유:")
                for n in s["bad_notes"]:
                    print(f"  - {n}")

    elif args.cmd == "lessons":
        s = summary()
        if not s["bad_notes"]:
            print("아직 거절 패턴 없음 (반영할 교훈 없음)")
            return
        print("# L3 자가개선 입력 — 거절된 패턴")
        for n in s["bad_notes"]:
            print(f"- {n}")
        print("\n→ 다음 원고 생성 시 이 패턴을 피할 것. 반복되면 스킬에 규칙으로 추가.")


if __name__ == "__main__":
    main()
