#!/usr/bin/env python3
"""reel — AI 가십 릴스 렌더러 (시각화 중심 + TTS 나레이션).

씬 레이아웃 (텍스트 최소, 시각화가 주인공):
    ┌──────────────────────┐
    │ LABEL (작게)          │
    │                      │
    │   [ SVG 시각화 ]      │  ← 화면 절반 이상
    │                      │
    │ 한 줄 테이크어웨이     │
    │ @handle              │
    └──────────────────────┘

실행:
  PLAYWRIGHT_BROWSERS_PATH=... uv run --with playwright --with edge-tts \
      python3 reel.py --slug 001-xxx
"""

import argparse
import html
import json
import pathlib
import re
import subprocess
import sys

from playwright.sync_api import sync_playwright

import diagrams
import postqueue as q
import rules as R

ROOT = pathlib.Path(__file__).resolve().parent.parent
REELS = ROOT / "content" / "queue" / "reels"
W, H, FPS = 1080, 1920, 30
PAD_SEC = 0.35
TAIL_SEC = 0.7

CSS = """\
:root{
  --bg:#0B1020; --ink:#EEF2FF; --muted:#93A0C4; --line:rgba(255,255,255,.10);
  --accent:#7C9CFF; --accent2:#FFB870; --warm:#FFB870;
}
*{margin:0;padding:0;box-sizing:border-box}
body{background:#05060f;font-family:"Noto Sans CJK KR","Noto Sans KR","WenQuanYi Zen Hei",sans-serif}
.scene{position:relative;width:1080px;height:1920px;overflow:hidden;
  background:radial-gradient(circle at 30% 12%,#172142 0%,#0B1020 48%,#05060f 100%);
  color:var(--ink);display:flex;flex-direction:column;padding:120px 76px 110px;}
.scene::before{content:"";position:absolute;inset:0;
  background-image:radial-gradient(rgba(255,255,255,.05) 1px,transparent 1px);
  background-size:44px 44px;opacity:.45}
.glow{position:absolute;width:900px;height:900px;border-radius:50%;filter:blur(190px);
  background:#7C9CFF;opacity:.20;top:-330px;right:-280px}
.label{position:relative;z-index:2;font-size:58px;font-weight:900;letter-spacing:.08em;
  color:var(--accent);margin-bottom:34px}
.viz{position:relative;z-index:2;flex:1;display:flex;align-items:center;justify-content:center;
  width:100%;min-height:0}
.viz svg{width:100%;height:auto}
.take{position:relative;z-index:2;font-size:84px;font-weight:900;
  line-height:1.26;letter-spacing:-.025em;text-align:center;margin-top:34px}
.take .em{color:var(--warm)}
.src{position:absolute;z-index:2;left:0;right:0;bottom:52px;text-align:center;
  font-size:30px;color:var(--muted);font-weight:500}
.handle{position:absolute;z-index:2;right:76px;top:78px;font-size:40px;font-weight:800;
  color:var(--accent);letter-spacing:.06em}
"""

TAKEAWAY_ICON = {"hook": "", "fact": "무슨 일", "why": "왜 중요", "use": "얻어가는 것", "cta": ""}


def esc(t):
    return html.escape(str(t or ""))


def em(t):
    """**강조** → <span class='em'>"""
    t = esc(t)
    out, i = [], 0
    while True:
        a = t.find("**", i)
        if a == -1:
            out.append(t[i:]); break
        b = t.find("**", a + 2)
        if b == -1:
            out.append(t[i:]); break
        out.append(t[i:a] + '<span class="em">' + t[a+2:b] + "</span>")
        i = b + 2
    return "".join(out)


def build_html(reel):
    parts = []
    for s in reel["scenes"]:
        kind = s.get("kind", "fact")
        visual = dict(s.get("visual") or {"kind": "stat", "value": "?"})
        # 세로 화면에 맞게 흐름도는 세로 방향으로
        if visual.get("kind") == "flow":
            visual.setdefault("direction", "v")
        try:
            svg = diagrams.build(visual)
        except Exception:                                   # noqa: BLE001
            svg = diagrams.build({"kind": "stat", "value": "—"})
        label = esc(s.get("label") or TAKEAWAY_ICON.get(kind, ""))
        inner = [
            '<div class="glow"></div>',
            f'<div class="handle">{esc(reel.get("handle"))}</div>',
            f'<div class="label">{label}</div>',
            f'<div class="viz">{svg}</div>',
        ]
        if s.get("takeaway"):
            inner.append(f'<div class="take">{em(s["takeaway"])}</div>')
        src = reel.get("source_line")
        if src and kind == "cta":
            inner.append(f'<div class="src">{esc(src)}</div>')
        parts.append(f'<div class="scene">{"".join(inner)}</div>')
    return (f"<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
            f"<style>{CSS}</style></head><body>{''.join(parts)}</body></html>")


def probe_duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                         capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def tts(text, voice, dest, rate="+15%"):
    """TTS 후 앞뒤 무음을 잘라낸다 (씬당 0.5~0.8초 낭비 제거)."""
    raw = dest.with_name(dest.stem + ".raw.mp3")
    subprocess.run(["edge-tts", "--voice", voice, "--rate", rate, "--text", text,
                    "--write-media", str(raw)], check=True, capture_output=True)
    trim = ("silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05:detection=peak,"
            "areverse,"
            "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05:detection=peak,"
            "areverse")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-af", trim,
                    "-c:a", "libmp3lame", "-b:a", "128k", str(dest)], check=True)
    raw.unlink(missing_ok=True)
    return probe_duration(dest)


def find_reel(slug):
    """릴스 원고 JSON 을 찾는다 (reels 큐 우선, 없으면 out/<slug>)."""
    sc = REELS / f"{slug}.json"
    if sc.exists():
        return sc
    hits = [p for p in REELS.glob("*.json") if slug in p.stem] if REELS.exists() else []
    if hits:
        return sorted(hits)[-1]
    legacy = ROOT / "out" / slug / "reel_script.json"
    if legacy.exists():
        return legacy
    return None


def render(slug, keep=False):
    src = find_reel(slug)
    if not src:
        sys.exit(f"릴스 원고 없음: {slug} (content/queue/reels/ 또는 out/{slug}/reel_script.json)")
    reel = json.loads(src.read_text(encoding="utf-8"))
    if src.parent == REELS:
        bad = R.reel_blocking(reel)
        if bad:
            for v in bad:
                print(f"  [{v['severity']}] {v['rule']}: {v['detail']}")
            sys.exit("❌ 릴스 규칙 위반 — 고친 뒤 다시 실행")
    out_dir = ROOT / "out" / f"reel-{slug}"
    out_dir.mkdir(parents=True, exist_ok=True)
    voice = reel.get("voice") or "ko-KR-SunHiNeural"

    # ① 씬별 TTS
    for i, s in enumerate(reel["scenes"], 1):
        dur = tts(s["narration"], voice, out_dir / f"voice{i:02d}.mp3")
        s["sec"] = round(dur + (TAIL_SEC if i == len(reel["scenes"]) else PAD_SEC), 3)
        print(f"  TTS {i}/{len(reel['scenes'])}: {dur:.1f}s → {s['sec']:.2f}s")

    # ② 화면 렌더
    html_path = out_dir / "_reel.html"
    html_path.write_text(build_html(reel), encoding="utf-8")
    pngs = []
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--force-color-profile=srgb", "--font-render-hinting=none"])
        page = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        page.goto(html_path.as_uri())
        page.wait_for_timeout(900)
        for i, el in enumerate(page.query_selector_all(".scene"), 1):
            dest = out_dir / f"scene{i:02d}.png"
            el.screenshot(path=str(dest), type="png")
            pngs.append(dest)
        b.close()
    if len(pngs) != len(reel["scenes"]):
        sys.exit(f"씬 렌더 수 불일치: {len(pngs)} vs {len(reel['scenes'])}")

    # ③ 클립
    clips = []
    for i, (png, s) in enumerate(zip(pngs, reel["scenes"]), 1):
        clip = out_dir / f"clip{i:02d}.mp4"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-i", str(png),
                        "-t", str(s["sec"]), "-vf", f"scale={W}:{H},format=yuv420p",
                        "-r", str(FPS), "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip)],
                       check=True)
        clips.append(clip)

    # ④ 영상 concat
    vl = out_dir / "_vlist.txt"
    vl.write_text("".join(f"file '{c.as_posix()}'\n" for c in clips), encoding="utf-8")
    vid = out_dir / "_video.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                    "-i", str(vl), "-c", "copy", str(vid)], check=True)

    # ⑤ 음성 concat
    voices = [out_dir / f"voice{i:02d}.mp3" for i in range(1, len(reel["scenes"]) + 1)]
    al = out_dir / "_alist.txt"
    al.write_text("".join(f"file '{v.as_posix()}'\n" for v in voices), encoding="utf-8")
    aud = out_dir / "_audio.m4a"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                    "-i", str(al), "-c:a", "aac", "-b:a", "192k", str(aud)], check=True)

    # ⑥ 합성
    total = sum(s["sec"] for s in reel["scenes"])
    out = out_dir / "reel.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(vid), "-i", str(aud),
                    "-filter_complex",
                    f"[0:v]fade=t=in:st=0:d=0.4,fade=t=out:st={max(total-0.6,0):.2f}:d=0.6[v];"
                    f"[1:a]afade=t=in:st=0:d=0.25,afade=t=out:st={max(total-0.8,0):.2f}:d=0.8[a]",
                    "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)], check=True)

    if not keep:
        for f in pngs + clips + [vid, aud, vl, al]:
            f.unlink(missing_ok=True)
    print(f"[{slug}] 릴스 완성: {total:.1f}초 · {len(reel['scenes'])}씬 → {out}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    if a.all:
        for p in sorted(REELS.glob("*.json")):
            render(p.stem, keep=a.keep)
        return
    if not a.slug:
        sys.exit("Usage: reel.py --slug <slug> | --all")
    render(a.slug, keep=a.keep)


if __name__ == "__main__":
    main()
