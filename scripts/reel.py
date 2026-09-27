#!/usr/bin/env python3
"""reel — 원고 → 나레이션 릴스 영상 (9:16 TTS 릴스).

파이프라인:
  reel_script.json  (대본: 씬별 나레이션 + 화면 텍스트)
      │
      ├─① 씬별 TTS (edge-tts, 한국어)      → voiceNN.mp3 + 길이 측정
      ├─② 씬별 화면 렌더 (Playwright)      → sceneNN.png (1080x1920)
      ├─③ 씬 길이 = 나레이션 길이 + 여백
      └─④ FFmpeg: 영상 + 음성 합성         → reel.mp4

실행 (uv 필요):
  PLAYWRIGHT_BROWSERS_PATH=... uv run --with playwright --with edge-tts python3 reel.py --slug 043-dropout
"""

import argparse
import html
import json
import pathlib
import shutil
import subprocess
import sys

from playwright.sync_api import sync_playwright

import postqueue as q
import reel_script as rs

ROOT = pathlib.Path(__file__).resolve().parent.parent
W, H, FPS = 1080, 1920, 30
PAD_SEC = 0.35          # 씬 끝 여백
TAIL_SEC = 0.7          # 마지막 씬 추가 여백

CSS = """\
*{margin:0;padding:0;box-sizing:border-box}
body{background:#05060f;font-family:"Noto Sans CJK KR","Noto Sans KR","WenQuanYi Zen Hei",sans-serif}
.scene{position:relative;width:1080px;height:1920px;overflow:hidden;
  background:radial-gradient(circle at 25% 15%,#16203f 0%,#0B1020 45%,#05060f 100%);
  color:#EEF2FF;display:flex;flex-direction:column;justify-content:center;padding:170px 110px;}
.scene::before{content:"";position:absolute;inset:0;
  background-image:radial-gradient(rgba(255,255,255,.05) 1px,transparent 1px);
  background-size:44px 44px;opacity:.5}
.glow{position:absolute;width:900px;height:900px;border-radius:50%;filter:blur(180px);
  background:#7C9CFF;opacity:.22;top:-320px;right:-260px}
.badge{position:relative;z-index:2;align-self:flex-start;font-size:44px;font-weight:800;
  letter-spacing:.12em;color:#7C9CFF;border:3px solid rgba(124,156,255,.45);
  border-radius:999px;padding:18px 40px;margin-bottom:60px}
.hook{position:relative;z-index:2;font-size:150px;font-weight:900;line-height:1.18;letter-spacing:-.035em}
.num{position:relative;z-index:2;font-size:54px;font-weight:900;color:#7C9CFF;letter-spacing:.12em;margin-bottom:36px}
.head{position:relative;z-index:2;font-size:112px;font-weight:900;line-height:1.24;letter-spacing:-.03em}
.sub{position:relative;z-index:2;font-size:62px;color:#C9D2EC;margin-top:52px;line-height:1.5}
.rule{position:relative;z-index:2;width:220px;height:12px;border-radius:6px;background:#7C9CFF;margin:60px 0}
.cta{position:relative;z-index:2;font-size:76px;font-weight:900;color:#0B1020;background:#FFB870;
  border-radius:40px;padding:60px 64px;text-align:center;line-height:1.35}
.handle{position:absolute;z-index:2;bottom:110px;left:0;right:0;text-align:center;
  font-size:48px;font-weight:700;color:#7C9CFF;letter-spacing:.08em}
"""


def esc(t):
    return html.escape(str(t or ""))


def build_html(script):
    parts = []
    for i, s in enumerate(script["scenes"], 1):
        kind = s.get("kind", "point")
        head = esc(s.get("head", ""))
        sub = esc(s.get("sub", ""))
        if kind == "hook":
            inner = (f'<div class="glow"></div><div class="badge">{esc(script.get("handle"))}</div>'
                     f'<div class="hook">{head}</div>'
                     + (f'<div class="rule"></div><div class="sub">{sub}</div>' if sub else ""))
        elif kind == "cta":
            inner = (f'<div class="glow"></div><div class="cta">{head}</div>'
                     + (f'<div class="sub" style="text-align:center">{sub}</div>' if sub else ""))
        else:
            inner = (f'<div class="glow"></div><div class="num">{i - 1:02d}</div>'
                     f'<div class="head">{head}</div>'
                     + (f'<div class="rule"></div><div class="sub">{sub}</div>' if sub else ""))
        parts.append(f'<div class="scene">{inner}</div>')
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


def render(slug, keep=False, zoom=False):
    data = q.load(slug)
    out_dir = ROOT / "out" / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    # ① 대본 확보
    script_path = out_dir / "reel_script.json"
    if not script_path.exists():
        sc = rs.generate(slug)
        script_path.write_text(json.dumps(sc, ensure_ascii=False, indent=2), encoding="utf-8")
    script = json.loads(script_path.read_text(encoding="utf-8"))
    voice = script.get("voice") or rs.VOICE

    # ② 씬별 TTS → 길이
    for i, s in enumerate(script["scenes"], 1):
        mp3 = out_dir / f"voice{i:02d}.mp3"
        dur = tts(s["narration"], voice, mp3)
        s["sec"] = round(dur + (TAIL_SEC if i == len(script["scenes"]) else PAD_SEC), 3)
        print(f"  TTS {i}/{len(script['scenes'])}: {dur:.1f}s + 여백 → {s['sec']:.2f}s")

    # ③ 화면 렌더
    html_path = out_dir / "_reel.html"
    html_path.write_text(build_html(script), encoding="utf-8")
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
    if len(pngs) != len(script["scenes"]):
        sys.exit(f"씬 렌더 수 불일치: {len(pngs)} vs {len(script['scenes'])}")

    # ④ 씬별 클립 (길이 = 나레이션 길이)
    clips = []
    for i, (png, s) in enumerate(zip(pngs, script["scenes"]), 1):
        clip = out_dir / f"clip{i:02d}.mp4"
        vf = f"scale={W}:{H},format=yuv420p"
        if zoom:
            frames = int(s["sec"] * FPS)
            vf = (f"scale={W*2}:{H*2},zoompan=z='min(zoom+0.0004,1.06)':"
                  f"d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},"
                  f"format=yuv420p")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-i", str(png),
                        "-t", str(s["sec"]), "-vf", vf, "-r", str(FPS),
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip)],
                       check=True)
        clips.append(clip)

    # ⑤ 영상 concat
    vl = out_dir / "_vlist.txt"
    vl.write_text("".join(f"file '{c.as_posix()}'\n" for c in clips), encoding="utf-8")
    vid = out_dir / "_video.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                    "-i", str(vl), "-c", "copy", str(vid)], check=True)

    # ⑥ 음성 concat
    voices = [out_dir / f"voice{i:02d}.mp3" for i in range(1, len(script["scenes"]) + 1)]
    al = out_dir / "_alist.txt"
    al.write_text("".join(f"file '{v.as_posix()}'\n" for v in voices), encoding="utf-8")
    aud = out_dir / "_audio.m4a"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                    "-i", str(al), "-c:a", "aac", "-b:a", "192k", str(aud)], check=True)

    # ⑦ 합성 + 페이드
    total = sum(s["sec"] for s in script["scenes"])
    reel = out_dir / "reel.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(vid), "-i", str(aud),
                    "-filter_complex",
                    f"[0:v]fade=t=in:st=0:d=0.5,fade=t=out:st={max(total-0.6,0):.2f}:d=0.6[v];"
                    f"[1:a]afade=t=in:st=0:d=0.3,afade=t=out:st={max(total-0.8,0):.2f}:d=0.8[a]",
                    "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", str(reel)], check=True)

    if not keep:
        for f in pngs + clips + [vid, aud, vl, al]:
            f.unlink(missing_ok=True)
    print(f"[{slug}] 릴스 완성: {total:.1f}초 · {len(script['scenes'])}씬 → {reel}")
    return reel


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--zoom", action="store_true", help="느린 줌(켄번스) 효과")
    a = ap.parse_args()
    if a.all:
        for s in q.all_slugs():
            render(s, keep=a.keep, zoom=a.zoom)
        return
    slug = a.slug or q.next_slug()
    if not slug:
        sys.exit("원고 없음")
    render(slug, keep=a.keep, zoom=a.zoom)


if __name__ == "__main__":
    main()
