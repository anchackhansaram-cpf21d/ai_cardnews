#!/usr/bin/env python3
"""원고 JSON -> out/<slug>/01.jpg ... 인스타 캐러셀용 JPEG 렌더러.

사용법:
  python render.py                 # 큐에서 다음 발행분 1건 렌더링
  python render.py --slug 001-attention
  python render.py --all           # 큐 전체 렌더링 (미리보기용)
"""

import argparse
import pathlib
import sys

from playwright.sync_api import sync_playwright

import postqueue as q
from template import H, W, build_html

ROOT = pathlib.Path(__file__).resolve().parent.parent


def render(slug: str) -> list:
    data = q.load(slug)
    out_dir = ROOT / "out" / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    html_path = out_dir / "_preview.html"
    html_path.write_text(build_html(data), encoding="utf-8")

    files = []
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--force-color-profile=srgb",
                                          "--font-render-hinting=none"])
        page = browser.new_page(viewport={"width": W, "height": H},
                                device_scale_factor=1)
        page.goto(html_path.as_uri())
        page.wait_for_timeout(700)  # 폰트 로드 + autofit 안정화
        cards = page.query_selector_all(".card")
        if not cards:
            browser.close()
            sys.exit(f"[{slug}] 카드가 없습니다.")
        if len(cards) > 10:
            print(f"⚠️  [{slug}] 카드 {len(cards)}장 — 인스타 캐러셀은 10장까지만 "
                  f"올라갑니다. 앞 10장만 발행됩니다.")
        for i, card in enumerate(cards, 1):
            dest = out_dir / f"{i:02d}.jpg"
            card.screenshot(path=str(dest), type="jpeg", quality=92)
            files.append(dest)
        browser.close()
    print(f"[{slug}] {len(files)}장 렌더링 -> out/{slug}/")
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()

    if a.all:
        for s in q.all_slugs():
            render(s)
        return
    slug = a.slug or q.next_slug()
    if not slug:
        sys.exit("발행 대기 중인 원고가 없습니다. 원고를 더 채워주세요.")
    render(slug)
    print(slug)  # 워크플로우가 읽어가는 값


if __name__ == "__main__":
    main()
