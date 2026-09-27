#!/usr/bin/env python3
"""Growth engine: helper functions for the auto-improvement cron.

사용법:
  python growth_generate.py next_number     -> 다음 원고 번호와 slug prefix 출력
  python growth_generate.py add <number> <slug> <json_string>  -> 큐에 원고 추가

크론(LLM 에이전트)이 생성한 원고를 큐에 추가하는 용도.
"""

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
QUEUE = ROOT / "content" / "queue"
STATE = ROOT / "state.json"
EPISODE = re.compile(r"^(\d{3})-(.+)")

def all_slugs():
    return sorted(p.stem for p in QUEUE.glob("*.json") if EPISODE.match(p.stem))

def next_episode_number():
    """Returns the next 3-digit episode number as str."""
    slugs = all_slugs()
    if not slugs:
        return "001"
    last = max(int(EPISODE.match(s).group(1)) for s in slugs if EPISODE.match(s))
    return f"{last + 1:03d}"

def unpicked_topics(topic_file):
    """TOPICS.md에서 아직 큐에 없는 토픽 목록 반환."""
    if not topic_file.exists():
        return []
    text = topic_file.read_text(encoding="utf-8")
    # Pick lines with [ ] (unchecked) or [x] (checked)
    # We want unchecked ones
    picked = set()
    for slug_file in QUEUE.glob("*.json"):
        if EPISODE.match(slug_file.stem):
            try:
                data = json.loads(slug_file.read_text(encoding="utf-8"))
                if "topic" in data:
                    picked.add(data["topic"])
            except:
                pass
    # Also check what's been posted
    if STATE.exists():
        state = json.loads(STATE.read_text(encoding="utf-8"))
        for log_entry in state.get("log", []):
            slug = log_entry.get("slug", "")
            if slug:
                data_file = QUEUE / f"{slug}.json"
                if data_file.exists():
                    try:
                        data = json.loads(data_file.read_text(encoding="utf-8"))
                        if "topic" in data:
                            picked.add(data["topic"])
                    except:
                        pass

    return picked

def add_manuscript(number, slug, content_dict, force=False):
    """Queue에 새 원고 추가. content_dict는 JSON-serializable dict.

    규칙 게이트(L3): high 위반이면 추가를 거부한다.
    """
    import rules as R
    bad = R.blocking(content_dict)
    if bad and not force:
        lines = [f"  - [{v['severity']}] {v['rule']}: {v['detail']}" for v in bad]
        raise SystemExit(
            "❌ 규칙 위반으로 추가 거부 (발행 파이프라인에서도 차단됩니다)\n"
            + "\n".join(lines)
            + "\n\n고칠 수 없으면 --force 로 강제 추가 (비권장)")
    filename = f"{number}-{slug}.json"
    path = QUEUE / filename
    path.write_text(
        json.dumps(content_dict, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8"
    )
    return filename

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: growth_generate.py next_number | add <num> <slug> <json>", file=sys.stderr)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "next_number":
        print(next_episode_number())
    elif cmd == "briefing":
        # L3 → L1: 원고 생성 전에 반드시 읽어야 하는 규칙/교훈
        import rules as R
        print(R.briefing())
        try:
            import feedback as F
            s = F.summary()
            if s.get("bad_notes"):
                print("\n## 최근 ❌ 사유 (반복 금지)")
                for n in s["bad_notes"]:
                    print(f"- {n}")
        except Exception:                                   # noqa: BLE001
            pass
    elif cmd == "add":
        args = [a for a in sys.argv[2:] if a != "--force"]
        force = "--force" in sys.argv[2:]
        if len(args) < 3:
            print("Usage: growth_generate.py add <number> <slug> <json_string> [--force]", file=sys.stderr)
            sys.exit(1)
        num, slug, json_str = args[0], args[1], args[2]
        content = json.loads(json_str)
        fn = add_manuscript(num, slug, content, force=force)
        print(f"Added: {fn}")
    elif cmd == "unpicked":
        picked = unpicked_topics(ROOT / "content" / "TOPICS.md")
        print("\n".join(sorted(picked)))
    else:
        print(f"Unknown: {cmd}", file=sys.stderr)
        sys.exit(1)