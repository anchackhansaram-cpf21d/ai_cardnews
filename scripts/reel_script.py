#!/usr/bin/env python3
"""릴스 나레이션 스크립트 생성 — 원고 JSON → 입말 스크립트(씬별).

캐러셀 원고는 "읽는 글"이라 그대로 낭독하면 어색하다.
이 스크립트가 릴스용 "듣는 글"로 다시 쓴다.

사용법:
  python reel_script.py --slug 043-dropout          # 생성 (있으면 재사용)
  python reel_script.py --slug 043-dropout --force  # 강제 재생성

출력: out/<slug>/reel_script.json
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
MODEL = os.environ.get("REEL_SCRIPT_MODEL") or "deepseek/deepseek-v4-flash"
VOICE = os.environ.get("REEL_VOICE") or "ko-KR-SunHiNeural"
TARGET_SEC = 28

PROMPT = """당신은 한국어 AI 교육 **릴스(쇼츠) 대본 작가**입니다.
아래 카드뉴스 원고를, **25~30초 분량**의 입말 나레이션 릴스 대본으로 다시 씁니다.

⚠️ 분량이 가장 중요하다. 낭독하면 25~30초여야 한다.
- 총 **5개 씬** (hook 1 + point 3 + cta 1)
- **나레이션은 씬당 20~28자** (공백 포함). 이보다 길면 안 된다.
- 화면 텍스트: head 10자 이내, sub 16자 이내

규칙:
- 나레이션은 **입말**. 문어체 금지. 한 씬당 딱 1문장.
- 숫자·비유는 살리고, 수식·전문용어 나열은 풀어서 말한다.
- 한국어만. 일본어·중국어 금지.
- 첫 씬은 질문이나 단정으로 강하게 시작. 마지막 씬은 저장/팔로우 유도.

출력(JSON만):
{
  "scenes": [
    {"kind":"hook","narration":"...","head":"...","sub":"..."},
    {"kind":"point","narration":"...","head":"...","sub":"..."},
    ...,
    {"kind":"cta","narration":"...","head":"...","sub":"..."}
  ]
}"""


def _loads(txt):
    txt = re.sub(r"^```(?:json)?|```$", "", (txt or "").strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(txt)
    except Exception:                                       # noqa: BLE001
        pass
    i, j = txt.find("{"), txt.rfind("}")
    if i == -1 or j <= i:
        return None
    try:
        return json.loads(txt[i:j + 1])
    except Exception:                                       # noqa: BLE001
        return None


def generate(slug):
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        sys.exit("OPENROUTER_API_KEY 없음")
    data = q.load(slug)
    payload = json.dumps(data, ensure_ascii=False)[:14000]

    last_raw = ""
    for attempt in (1, 2):
        body = {"model": MODEL, "messages": [
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": payload}],
            "temperature": 0.6, "max_tokens": 4000}
        if attempt == 1:
            body["response_format"] = {"type": "json_object"}
        r = requests.post("https://openrouter.ai/api/v1/chat/completions", json=body,
                          headers={"Authorization": f"Bearer {key}"}, timeout=180)
        if r.status_code != 200:
            last_raw = f"HTTP {r.status_code}: {r.text[:200]}"
            continue
        msg = (r.json().get("choices") or [{}])[0].get("message") or {}
        raw = msg.get("content") or msg.get("reasoning") or ""
        if not raw:
            last_raw = f"빈 응답 (finish={r.json().get('choices',[{}])[0].get('finish_reason')})"
            continue
        parsed = _loads(raw)
        if parsed and parsed.get("scenes"):
            scenes = parsed["scenes"]
            # 씬 수 방어: hook + cta 유지, point 는 3개로 자름
            hook = [s for s in scenes if s.get("kind") == "hook"][:1]
            cta = [s for s in scenes if s.get("kind") == "cta"][-1:]
            pts = [s for s in scenes if s.get("kind") not in ("hook", "cta")][:3]
            final = hook + pts + cta
            if len(final) >= 3:
                return {"slug": slug, "voice": VOICE,
                        "handle": data.get("handle", "dora_studyzy"), "scenes": final}
        last_raw = raw[:600]

    dbg = ROOT / "out" / f"_reelscript_raw_{slug}.txt"
    dbg.parent.mkdir(parents=True, exist_ok=True)
    dbg.write_text(str(last_raw), encoding="utf-8")
    sys.exit(f"스크립트 생성 실패 (2회 시도) — 원문: {dbg}\n{str(last_raw)[:300]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()

    slugs = q.all_slugs() if a.all else [a.slug or q.next_slug()]
    for slug in [s for s in slugs if s]:
        dest = ROOT / "out" / slug / "reel_script.json"
        if dest.exists() and not a.force:
            print(f"[{slug}] 기존 스크립트 재사용: {dest}")
            continue
        sc = generate(slug)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(sc, ensure_ascii=False, indent=2), encoding="utf-8")
        total = sum(len(s.get("narration", "")) for s in sc["scenes"])
        print(f"[{slug}] 씬 {len(sc['scenes'])}개 · 나레이션 {total}자 → {dest}")


if __name__ == "__main__":
    main()
