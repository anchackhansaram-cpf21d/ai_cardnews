#!/usr/bin/env python3
"""원고 JSON → 9:16 릴스 영상 (1080x1920 mp4).

사용법:
  python reel.py --slug 043-dropout
  python reel.py --all        # 미리보기

흐름: 씬 HTML 생성 → Playwright로 씬별 PNG → FFmpeg로 페이드 연결 → out/<slug>/reel.mp4
"""

import argparse
import html
import pathlib
import shutil
import subprocess
import sys

from playwright.sync_api import sync_playwright

import postqueue as q

ROOT = pathlib.Path(__file__).resolve().parent.parent
W, H = 1080, 1920
FPS = 30
SCENE_SEC = 2.8        # 씬당 길이(초)
FADE = 0.45            # 크로스페이드 길이

CSS = """\
*{margin:0;padding:0;box-sizing:border-box}
body{background:#05060f;font-family:"Noto Sans CJK KR","Noto Sans KR","WenQuanYi Zen Hei",sans-serif}
.scene{position:relative;width:1080px;height:1920px;overflow:hidden;
  background:radial-gradient(circle at 25% 15%,#16203f 0%,#0B1020 45%,#05060f 100%);
  color:#EEF2FF;display:flex;flex-direction:column;justify-content:center;
  padding:150px 110px;}
.scene::before{content:"";position:absolute;inset:0;
  background-image:radial-gradient(rgba(255,255,255,.05) 1px,transparent 1px);
  background-size:44px 44px;opacity:.5}
.glow{position:absolute;width:900px;height:900px;border-radius:50%;filter:blur(180px);
  background:#7C9CFF;opacity:.22;top:-320px;right:-260px}
.badge{position:relative;z-index:2;display:inline-block;align-self:flex-start;
  font-size:44px;font-weight:800;letter-spacing:.12em;color:#7C9CFF;
  border:3px solid rgba(124,156,255,.45);border-radius:999px;padding:18px 40px;margin-bottom:64px}
.hook{position:relative;z-index:2;font-size:132px;font-weight:900;line-height:1.22;letter-spacing:-.03em}
.hook .hl{background:linear-gradient(transparent 58%,rgba(124,156,255,.35) 58%)}
.num{position:relative;z-index:2;font-size:56px;font-weight:900;color:#7C9CFF;letter-spacing:.1em;margin-bottom:40px}
.head{position:relative;z-index:2;font-size:96px;font-weight:900;line-height:1.28;letter-spacing:-.02em;margin-bottom:56px}
.body{position:relative;z-index:2;font-size:62px;font-weight:400;line-height:1.6;color:#C9D2EC}
.body .em{color:#fff;font-weight:800}
.rule{position:relative;z-index:2;width:220px;height:12px;border-radius:6px;background:#7C9CFF;margin:56px 0}
.cta{position:relative;z-index:2;font-size:72px;font-weight:800;line-height:1.5;color:#0B1020;
  background:#FFB870;border-radius:36px;padding:56px 64px;text-align:center}
.bullets{position:relative;z-index:2;font-size:58px;line-height:1.7;color:#D6DCF2}
.bullets div{margin-bottom:34px;padding-left:70px;position:relative}
.bullets div::before{content:"";position:absolute;left:0;top:26px;width:26px;height:26px;
  border-radius:50%;background:#FFB870}
.handle{position:absolute;z-index:2;bottom:90px;left:0;right:0;text-align:center;
  font-size:46px;font-weight:700;color:#7C9CFF;letter-spacing:.08em}
"""


def esc(t):
    t = html.escape(str(t))
    out, i = [], 0
    while True:
        a = t.find("**", i)
        if a == -1:
            out.append(t[i:]); break
        b = t.find("**", a + 2)
        if b == -1:
            out.append(t[i:]); break
        out.append(t[i:a]); out.append('<span class="em">' + t[a+2:b] + "</span>")
        i = b + 2
    return "".join(out)


def first_sentence(text, limit=120):
    t = str(text).replace("\n", " ").strip()
    for sep in (". ", "다. ", "!", "?", "。"):
        i = t.find(sep)
        if 0 < i < limit:
            return t[:i + len(sep)].strip()
    return t[:limit].strip()


def scenes(data):
    """원고 → 씬 리스트 [{type, ...}]"""
    out = []
    cards = data.get("cards", [])
    cover = next((c for c in cards if c.get("type") == "cover"), None)
    insight = next((c for c in cards if c.get("type") == "insight"), None)
    handle = "@" + (data.get("handle") or "dora_studyzy").lstrip("@")

    if cover:
        title = esc(cover.get("title", "")).replace("\n", "<br>")
        for w in cover.get("highlight", []) or []:
            title = title.replace(esc(w), f'<span class="hl">{esc(w)}</span>')
        out.append({"kind": "hook", "eyebrow": esc(cover.get("eyebrow", "AI 이론")),
                    "title": title, "handle": handle})

    # 핵심 카드 4장 (body/visual) → 포인트 씬
    points = [c for c in cards if c.get("type") in ("body", "visual")][:4]
    for i, c in enumerate(points, 1):
        body = c.get("body") or c.get("lead") or ""
        out.append({"kind": "point", "num": i,
                    "head": esc(c.get("heading") or c.get("title") or ""),
                    "body": esc(first_sentence(body)), "handle": handle})

    if insight:
        bullets = (insight.get("bullets") or [])[:3]
        out.append({"kind": "cta", "bullets": [esc(b) for b in bullets],
                    "cta": esc(insight.get("cta") or "저장하고 팔로우!"), "handle": handle})
    return out


def build_html(data):
    parts = []
    for s in scenes(data):
        if s["kind"] == "hook":
            inner = (f'<div class="glow"></div><div class="badge">{s["eyebrow"]}</div>'
                     f'<div class="hook">{s["title"]}</div><div class="rule"></div>')
        elif s["kind"] == "point":
            inner = (f'<div class="glow"></div><div class="num">POINT {s["num"]}</div>'
                     f'<div class="head">{s["head"]}</div>'
                     f'<div class="body">{s["body"]}</div>')
        else:
            b = "".join(f"<div>{x}</div>" for x in s["bullets"])
            inner = (f'<div class="glow"></div><div class="bullets">{b}</div>'
                     f'<div style="height:56px"></div><div class="cta">{s["cta"]}</div>')
        parts.append(f'<div class="scene">{inner}<div class="handle">{s["handle"]}</div></div>')
    return (f"<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
            f"<style>{CSS}</style></head><body>{''.join(parts)}</body></html>")


def render(slug, keep=False):
    data = q.load(slug)
    out_dir = ROOT / "out" / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / "_reel.html"
    html_path.write_text(build_html(data), encoding="utf-8")

    # 1) 씬 PNG
    pngs = []
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--force-color-profile=srgb",
                                          "--font-render-hinting=none"])
        page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        page.goto(html_path.as_uri())
        page.wait_for_timeout(900)
        for i, sc in enumerate(page.query_selector_all(".scene"), 1):
            dest = out_dir / f"scene{i:02d}.png"
            sc.screenshot(path=str(dest), type="png")
            pngs.append(dest)
        browser.close()
    if not pngs:
        sys.exit(f"[{slug}] 씬이 없습니다.")

    # 2) 씬별 클립 (정지 이미지 → 영상)
    clips = []
    for i, png in enumerate(pngs, 1):
        clip = out_dir / f"clip{i:02d}.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-loop", "1", "-i", str(png), "-t", str(SCENE_SEC),
            "-vf", f"scale={W}:{H},format=yuv420p", "-r", str(FPS),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip),
        ], check=True, capture_output=True)
        clips.append(clip)

    # 3) 크로스페이드 연결
    reel = out_dir / "reel.mp4"
    if len(clips) == 1:
        shutil.copy(clips[0], reel)
    else:
        inputs = []
        for c in clips:
            inputs += ["-i", str(c)]
        filt, prev, offset = [], "0:v", SCENE_SEC - FADE
        for i in range(1, len(clips)):
            out_tag = f"v{i}"
            filt.append(f"[{prev}][{i}:v]xfade=transition=fade:duration={FADE}"
                        f":offset={offset:.2f}[{out_tag}]")
            prev, offset = out_tag, offset + SCENE_SEC - FADE
        subprocess.run([
            "ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filt),
            "-map", f"[{prev}]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-r", str(FPS), str(reel),
        ], check=True, capture_output=True)

    if not keep:
        for f in pngs + clips:
            f.unlink(missing_ok=True)
    print(f"[{slug}] 릴스 {len(pngs)}씬 → out/{slug}/reel.mp4 "
          f"({SCENE_SEC*len(pngs)-FADE*(len(pngs)-1):.1f}초)")
    return reel


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    if a.all:
        for s in q.all_slugs():
            render(s, keep=a.keep)
        return
    slug = a.slug or q.next_slug()
    if not slug:
        sys.exit("원고 없음")
    render(slug, keep=a.keep)


if __name__ == "__main__":
    main()