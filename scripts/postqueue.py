"""발행 큐 관리: 다음에 올릴 원고를 고르고 발행 기록을 남긴다."""

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
QUEUE = ROOT / "content" / "queue"
STATE = ROOT / "state.json"
CONFIG = ROOT / "config.json"


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"posted": [], "last_run": None}


def save_state(state):
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                     encoding="utf-8")


def all_slugs():
    return sorted(p.stem for p in QUEUE.glob("*.json"))


def next_slug():
    """아직 발행하지 않은 원고 중 가장 앞선 것. 없으면 None."""
    posted = set(load_state()["posted"])
    for slug in all_slugs():
        if slug not in posted:
            return slug
    return None


def config():
    if CONFIG.exists():
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    return {}


def load(slug):
    """원고를 읽고 config.json 값(핸들·시리즈명)을 채워 넣는다.

    원고 파일에 같은 키가 있으면 원고 쪽이 우선합니다.
    """
    data = json.loads((QUEUE / f"{slug}.json").read_text(encoding="utf-8"))
    for k, v in config().items():
        data.setdefault(k, v)
    return data


def mark_posted(slug, permalink=None, media_id=None, when=None):
    state = load_state()
    if slug not in state["posted"]:
        state["posted"].append(slug)
    state.setdefault("log", []).append({
        "slug": slug, "posted_at": when, "media_id": media_id,
        "permalink": permalink,
    })
    state["last_run"] = when
    save_state(state)


def remaining():
    return len(all_slugs()) - len(load_state()["posted"])
