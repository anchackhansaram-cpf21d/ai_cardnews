#!/usr/bin/env bash
# KaTeX 를 저장소에 내장한다 (CDN 미로딩 → $...$ 원문 노출 방지)
set -e
ROOT=/opt/data/ai_cardnews
DEST="$ROOT/assets/katex"
TMP=$(mktemp -d)
cd "$TMP"
echo "다운로드: katex 0.16.11 (npm registry)"
curl -sSL -o katex.tgz "https://registry.npmjs.org/katex/-/katex-0.16.11.tgz"
tar xzf katex.tgz
mkdir -p "$DEST"
cp package/dist/katex.min.js      "$DEST/"
cp package/dist/katex.min.css     "$DEST/"
cp package/dist/contrib/auto-render.min.js "$DEST/"
mkdir -p "$DEST/fonts"
cp package/dist/fonts/*.woff2 "$DEST/fonts/" 2>/dev/null || true
echo "--- 내장 결과 ---"
du -sh "$DEST"
ls "$DEST"
echo "폰트 $(ls "$DEST/fonts" | wc -l)개"
cd / && rm -rf "$TMP"
