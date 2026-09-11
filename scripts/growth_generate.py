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

def add_manuscript(number, slug, content_dict):
    """Queue에 새 원고 추가. content_dict는 JSON-serializable dict."""
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
    elif cmd == "add":
        if len(sys.argv) < 5:
            print("Usage: growth_generate.py add <number> <slug> <json_string>", file=sys.stderr)
            sys.exit(1)
        num, slug, json_str = sys.argv[2], sys.argv[3], sys.argv[4]
        content = json.loads(json_str)
        fn = add_manuscript(num, slug, content)
        print(f"Added: {fn}")
    elif cmd == "unpicked":
        picked = unpicked_topics(ROOT / "content" / "TOPICS.md")
        print("\n".join(sorted(picked)))
    else:
        print(f"Unknown: {cmd}", file=sys.stderr)
        sys.exit(1)