"""카드용 SVG 다이어그램 생성기.

원고 JSON의 visual 스펙을 받아 인라인 SVG 문자열을 돌려준다.
색은 CSS 변수(var(--accent) 등)를 그대로 쓰므로 카드 테마를 자동으로 따라간다.

    {"type":"visual","heading":"...","visual":{"kind":"heatmap", ...},"caption":"..."}
"""

import html

CW = 908          # 카드 본문 가용 너비


def esc(t):
    return html.escape(str(t))


def _wrap(inner, height, extra=""):
    return (f'<svg class="dia" viewBox="0 0 {CW} {height}" width="100%" '
            f'height="{height}" xmlns="http://www.w3.org/2000/svg" '
            f'font-family="Noto Sans CJK KR, sans-serif" {extra}>{inner}</svg>')


# ── 1. 히트맵 / 행렬 ─────────────────────────────────────────────
def heatmap(s):
    rows, cols = s["rows"], s["cols"]
    vals = s["values"]
    lab_w = 200 if any(rows) else 0
    lab_h = 46 if any(cols) else 0
    n_c, n_r = len(cols), len(rows)
    cell = min(104, (CW - lab_w - 20) // max(n_c, 1))
    gap = 6
    gw = n_c * (cell + gap) - gap
    x0 = (CW - (lab_w + gw)) / 2 + lab_w
    y0 = lab_h + 8
    H = int(y0 + n_r * (cell + gap) - gap + 16)

    if s.get("normalize", "all") == "col":
        lo = [min(r[j] for r in vals) for j in range(n_c)]
        hi = [max(r[j] for r in vals) for j in range(n_c)]
        norm = lambda v, j: ((v - lo[j]) / ((hi[j] - lo[j]) or 1))
    else:
        flat = [v for row in vals for v in row]
        lo_a, hi_a = min(flat), max(flat)
        norm = lambda v, j: ((v - lo_a) / ((hi_a - lo_a) or 1))
    out = []

    for j, c in enumerate(cols):
        cx = x0 + j * (cell + gap) + cell / 2
        out.append(f'<text x="{cx:.1f}" y="{lab_h-14}" text-anchor="middle" '
                   f'font-size="21" font-weight="600" fill="var(--muted)">{esc(c)}</text>')

    for i, r in enumerate(rows):
        cy = y0 + i * (cell + gap) + cell / 2
        if r:
            out.append(f'<text x="{lab_w-18}" y="{cy+8:.1f}" text-anchor="end" '
                       f'font-size="22" font-weight="600" fill="var(--ink)">{esc(r)}</text>')
        for j in range(len(cols)):
            v = vals[i][j]
            t = norm(v, j)
            cx = x0 + j * (cell + gap)
            op = 0.08 + 0.86 * t
            strong = t > 0.55
            out.append(f'<rect x="{cx:.1f}" y="{cy-cell/2:.1f}" width="{cell}" '
                       f'height="{cell}" rx="8" fill="var(--accent)" '
                       f'fill-opacity="{op:.2f}"/>')
            fill = "#0B1020" if strong else "var(--ink)"
            cellstr = s["text"][i][j] if s.get("text") else f"{v:.2f}"
            fsz = 22 if len(str(cellstr)) <= 4 else 19
            out.append(f'<text x="{cx+cell/2:.1f}" y="{cy+8:.1f}" text-anchor="middle" '
                       f'font-size="{fsz}" font-weight="700" fill="{fill}">'
                       f'{esc(cellstr)}</text>')
    return _wrap("".join(out), H)


# ── 2. 가로 막대 ────────────────────────────────────────────────
def bars(s):
    items = s.get("items") or s.get("bars") or s.get("values") or []
    # 라벨/값 키 정규화 (label|name, value|v|val|percent|pct)
    norm = []
    for it in items:
        if not isinstance(it, dict):
            continue
        lab = it.get("label") or it.get("name") or it.get("key") or ""
        val = it.get("value", it.get("v", it.get("val", it.get("percent", it.get("pct")))))
        if val is None or isinstance(val, bool):
            continue
        try:
            val = float(val)
        except (TypeError, ValueError):
            continue
        norm.append({**it, "label": lab, "value": val})
    items = norm
    if not items:
        raise ValueError("bars: no numeric items")
    unit = s.get("unit", "")
    lab_w = 250
    bar_h, gap = 62, 26
    H = len(items) * (bar_h + gap) - gap + 16
    vmax = s.get("max") or (max(i["value"] for i in items) * 1.15) or 1
    track = CW - lab_w - 30
    out = []
    for k, it in enumerate(items):
        y = k * (bar_h + gap)
        hot = it.get("highlight")
        col = "var(--warm)" if hot else "var(--accent)"
        w = max(6, track * it["value"] / vmax)
        out.append(f'<text x="{lab_w-22}" y="{y+bar_h/2+9:.0f}" text-anchor="end" '
                   f'font-size="24" font-weight="{700 if hot else 500}" '
                   f'fill="{"var(--ink)" if hot else "var(--ink)"}">{esc(it["label"])}</text>')
        out.append(f'<rect x="{lab_w}" y="{y}" width="{track}" height="{bar_h}" '
                   f'rx="10" fill="var(--ink)" fill-opacity=".07"/>')
        out.append(f'<rect x="{lab_w}" y="{y}" width="{w:.0f}" height="{bar_h}" '
                   f'rx="10" fill="{col}" fill-opacity="{.95 if hot else .72}"/>')
        if s.get("show_values", True):
            txt = f'{it["value"]:g}{unit}'
            inside = w > 150
            tx = lab_w + w - 18 if inside else lab_w + w + 18
            out.append(f'<text x="{tx:.0f}" y="{y+bar_h/2+9:.0f}" '
                       f'text-anchor="{"end" if inside else "start"}" font-size="24" '
                       f'font-weight="700" fill="{"#0B1020" if inside else "var(--muted)"}">'
                       f'{esc(txt)}</text>')
    return _wrap("".join(out), int(H))


# ── 3. 꺾은선 / 곡선 ────────────────────────────────────────────
def line(s):
    series = s["series"]
    H = 486
    pad_l, pad_r, pad_t, pad_b = 104, 40, 34, 86
    w, h = CW - pad_l - pad_r, H - pad_t - pad_b
    xs = [p[0] for sr in series for p in sr["points"]]
    ys = [p[1] for sr in series for p in sr["points"]]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(min(ys), 0), max(ys)
    sx = lambda v: pad_l + (v - x0) / ((x1 - x0) or 1) * w
    sy = lambda v: pad_t + h - (v - y0) / ((y1 - y0) or 1) * h

    out = [f'<rect x="{pad_l}" y="{pad_t}" width="{w}" height="{h}" fill="none"/>']
    for f in range(5):
        gy = pad_t + h * f / 4
        out.append(f'<line x1="{pad_l}" y1="{gy:.0f}" x2="{pad_l+w}" y2="{gy:.0f}" '
                   f'stroke="var(--ink)" stroke-opacity=".09" stroke-width="1"/>')
    out.append(f'<line x1="{pad_l}" y1="{pad_t+h}" x2="{pad_l+w}" y2="{pad_t+h}" '
               f'stroke="var(--ink)" stroke-opacity=".26" stroke-width="2"/>')

    cols = ["var(--accent)", "var(--warm)"]
    for k, sr in enumerate(series):
        col = cols[k % 2]
        pts = " ".join(f"{sx(p[0]):.1f},{sy(p[1]):.1f}" for p in sr["points"])
        if sr.get("fill", True) and k == 0:
            out.append(f'<polygon points="{sx(x0):.1f},{pad_t+h} {pts} '
                       f'{sx(x1):.1f},{pad_t+h}" fill="{col}" fill-opacity=".13"/>')
        out.append(f'<polyline points="{pts}" fill="none" stroke="{col}" '
                   f'stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>')
        ex, ey = sr["points"][-1]
        out.append(f'<circle cx="{sx(ex):.1f}" cy="{sy(ey):.1f}" r="9" fill="{col}"/>')
        if sr.get("label"):
            dy = -26 if k == 0 else 40
            out.append(f'<text x="{sx(ex)-16:.1f}" y="{sy(ey)+dy:.1f}" text-anchor="end" '
                       f'font-size="23" font-weight="700" fill="{col}">'
                       f'{esc(sr["label"])}</text>')

    if s.get("xlabel"):
        out.append(f'<text x="{pad_l+w/2:.0f}" y="{H-10}" text-anchor="middle" '
                   f'font-size="22" font-weight="500" fill="var(--muted)">'
                   f'{esc(s["xlabel"])}</text>')
    if s.get("ylabel"):
        out.append(f'<text transform="translate(34,{pad_t+h/2:.0f}) rotate(-90)" '
                   f'text-anchor="middle" font-size="22" font-weight="500" '
                   f'fill="var(--muted)">{esc(s["ylabel"])}</text>')
    for a in s.get("ticks", []):
        out.append(f'<text x="{sx(a[0]):.0f}" y="{pad_t+h+32}" text-anchor="middle" '
                   f'font-size="21" fill="var(--muted)">{esc(a[1])}</text>')
    return _wrap("".join(out), H)


# ── 4. 흐름도 ───────────────────────────────────────────────────
def flow(s):
    steps = s["steps"]
    vertical = s.get("direction", "h") == "v"
    out = []
    if vertical:
        bh, gap = 104, 46
        H = len(steps) * (bh + gap) - gap + 10
        bw = CW - 130
        for k, st in enumerate(steps):
            y = k * (bh + gap)
            hot = st.get("highlight")
            out += _box(65, y, bw, bh, st, hot)
            if k < len(steps) - 1:
                cy = y + bh
                out.append(f'<path d="M{CW/2:.0f},{cy+8} L{CW/2:.0f},{cy+gap-12}" '
                           f'stroke="var(--accent)" stroke-width="4" '
                           f'marker-end="url(#ar)"/>')
    else:
        n = len(steps)
        gap = 34
        bw = (CW - gap * (n - 1)) / n
        bh, H = 168, 178
        for k, st in enumerate(steps):
            x = k * (bw + gap)
            out += _box(x, 4, bw, bh, st, st.get("highlight"), small=True)
            if k < n - 1:
                cx = x + bw
                out.append(f'<path d="M{cx+6:.0f},{4+bh/2:.0f} L{cx+gap-10:.0f},'
                           f'{4+bh/2:.0f}" stroke="var(--accent)" stroke-width="4" '
                           f'marker-end="url(#ar)"/>')
    marker = ('<defs><marker id="ar" viewBox="0 0 10 10" refX="8" refY="5" '
              'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
              '<path d="M0,1 L9,5 L0,9 z" fill="var(--accent)"/></marker></defs>')
    return _wrap(marker + "".join(out), int(H))


def _box(x, y, w, h, st, hot, small=False):
    col = "var(--warm)" if hot else "var(--accent)"
    o = [f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" rx="16" '
         f'fill="{col}" fill-opacity="{.20 if hot else .11}" stroke="{col}" '
         f'stroke-opacity="{.85 if hot else .45}" stroke-width="2"/>']
    cx, cy = x + w / 2, y + h / 2
    sub = st.get("sub")
    fs = 26 if small else 30
    if sub:
        o.append(f'<text x="{cx:.0f}" y="{cy-4:.0f}" text-anchor="middle" '
                 f'font-size="{fs}" font-weight="700" fill="var(--ink)">'
                 f'{esc(st["label"])}</text>')
        o.append(f'<text x="{cx:.0f}" y="{cy+32:.0f}" text-anchor="middle" '
                 f'font-size="21" font-weight="500" fill="var(--muted)">{esc(sub)}</text>')
    else:
        o.append(f'<text x="{cx:.0f}" y="{cy+10:.0f}" text-anchor="middle" '
                 f'font-size="{fs}" font-weight="700" fill="var(--ink)">'
                 f'{esc(st["label"])}</text>')
    return o


# ── 5. 주석 달린 수식 ───────────────────────────────────────────
def formula(s):
    parts = s["parts"]
    H = 330
    total = sum(len(p["text"]) for p in parts) or 1
    unit = (CW - 60) / total
    x = 30
    out = []
    for p in parts:
        w = unit * len(p["text"])
        hot = bool(p.get("note"))
        col = p.get("color", "accent")
        c = {"accent": "var(--accent)", "warm": "var(--warm)"}.get(col, "var(--accent)")
        if hot:
            out.append(f'<rect x="{x:.0f}" y="86" width="{w:.0f}" height="96" rx="12" '
                       f'fill="{c}" fill-opacity=".14"/>')
        out.append(f'<text x="{x+w/2:.0f}" y="152" text-anchor="middle" '
                   f'font-size="46" font-weight="700" '
                   f'fill="{c if hot else "var(--ink)"}">{esc(p["text"])}</text>')
        if hot:
            out.append(f'<path d="M{x+w/2:.0f},188 L{x+w/2:.0f},214" stroke="{c}" '
                       f'stroke-width="2.5" stroke-opacity=".7"/>')
            ty = 246
            for i, ln in enumerate(str(p["note"]).split("\n")[:3]):
                out.append(f'<text x="{x+w/2:.0f}" y="{ty+i*30}" text-anchor="middle" '
                           f'font-size="22" font-weight="600" fill="{c}">{esc(ln)}</text>')
        x += w
    if s.get("title"):
        out.insert(0, f'<text x="{CW/2:.0f}" y="42" text-anchor="middle" font-size="23" '
                      f'font-weight="600" fill="var(--muted)">{esc(s["title"])}</text>')
    return _wrap("".join(out), H)


# ── 6. 좌우 비교 ────────────────────────────────────────────────
def compare(s):
    L, R = s["left"], s["right"]
    gap = 30
    w = (CW - gap) / 2
    rows = max(len(L["items"]), len(R["items"]))
    H = 96 + rows * 56 + 26
    out = []
    for k, (side, x, col) in enumerate(((L, 0, "var(--muted)"),
                                        (R, w + gap, "var(--accent)"))):
        out.append(f'<rect x="{x:.0f}" y="0" width="{w:.0f}" height="{H-8:.0f}" rx="18" '
                   f'fill="{col}" fill-opacity="{.06 if k==0 else .11}" '
                   f'stroke="{col}" stroke-opacity=".34" stroke-width="2"/>')
        out.append(f'<text x="{x+w/2:.0f}" y="56" text-anchor="middle" font-size="29" '
                   f'font-weight="800" fill="{col}">{esc(side["title"])}</text>')
        for i, it in enumerate(side["items"]):
            out.append(f'<text x="{x+30:.0f}" y="{112+i*56}" font-size="24" '
                       f'font-weight="500" fill="var(--ink)" fill-opacity=".88">'
                       f'{esc(it)}</text>')
    return _wrap("".join(out), int(H))


# ── 7. 아키텍처 블록 다이어그램 ─────────────────────────────────
def arch(s):
    blocks = s["blocks"]
    direction = s.get("direction", "h")
    gap, pad = 46, 36
    if direction == "v":
        bh, bw = 110, 460
        H = len(blocks) * (bh + gap) - gap + pad
        x = (CW - bw) / 2
        out = []
        for k, blk in enumerate(blocks):
            y = k * (bh + gap) + pad / 2
            col = ["var(--accent)", "var(--warm)", "#6ED4B3"][k % 3]
            out.append(f'<rect x="{x:.0f}" y="{y:.0f}" width="{bw}" height="{bh}" rx="14" '
                       f'fill="{col}" fill-opacity=".12" stroke="{col}" stroke-opacity=".55" stroke-width="2"/>')
            out.append(f'<text x="{CW/2:.0f}" y="{y+bh/2+10:.0f}" text-anchor="middle" '
                       f'font-size="26" font-weight="700" fill="{col}">{esc(blk["label"])}</text>')
            if blk.get("sub"):
                out.append(f'<text x="{CW/2:.0f}" y="{y+bh-18:.0f}" text-anchor="middle" '
                           f'font-size="19" font-weight="500" fill="var(--muted)">{esc(blk["sub"])}</text>')
            if k < len(blocks) - 1:
                cy = y + bh
                out.append(f'<path d="M{CW/2},{cy+6} L{CW/2},{cy+gap-12}" stroke="{col}" '
                           f'stroke-width="3.5" marker-end="url(#ar)"/>')
    else:
        n = len(blocks)
        bw = min(280, (CW - gap * (n - 1)) / n)
        bh, H = 180, 224
        x0 = (CW - (n * bw + (n - 1) * gap)) / 2
        out = []
        for k, blk in enumerate(blocks):
            x = x0 + k * (bw + gap)
            col = ["var(--accent)", "var(--warm)", "#6ED4B3"][k % 3]
            out.append(f'<rect x="{x:.0f}" y="6" width="{bw}" height="{bh}" rx="14" '
                       f'fill="{col}" fill-opacity=".10" stroke="{col}" stroke-opacity=".45" stroke-width="2"/>')
            out.append(f'<text x="{x+bw/2:.0f}" y="{bh/2+8:.0f}" text-anchor="middle" '
                       f'font-size="{24 if len(blk.get("label",""))>8 else 28}" font-weight="700" '
                       f'fill="{col}">{esc(blk["label"])}</text>')
            if blk.get("sub"):
                out.append(f'<text x="{x+bw/2:.0f}" y="{bh-22:.0f}" text-anchor="middle" '
                           f'font-size="18" font-weight="500" fill="var(--muted)">{esc(blk["sub"])}</text>')
            if k < n - 1:
                cx = x + bw
                out.append(f'<path d="M{cx+8},{bh/2+6} L{cx+gap-12},{bh/2+6}" stroke="{col}" '
                           f'stroke-width="3.5" marker-end="url(#ar)"/>')
    marker = ('<defs><marker id="ar" viewBox="0 0 10 10" refX="8" refY="5" '
              'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
              '<path d="M0,1 L9,5 L0,9 z" fill="var(--accent)"/></marker></defs>')
    return _wrap(marker + "".join(out), int(H))


# ── 8. 벤 다이어그램 ─────────────────────────────────────────────
def venn(s):
    sets = s.get("sets", [])
    H = 440
    cx, cy = CW / 2, H / 2 + 10
    r = 180
    out = []
    colors = ["var(--accent)", "var(--warm)"]
    for k, item in enumerate(sets[:3]):
        dx = (k - (len(sets) - 1) / 2) * r * 0.8
        col = colors[k % 2]
        out.append(f'<circle cx="{cx+dx:.0f}" cy="{cy:.0f}" r="{r}" '
                   f'fill="{col}" fill-opacity=".09" stroke="{col}" stroke-opacity=".40" stroke-width="2.5"/>')
        out.append(f'<text x="{cx+dx:.0f}" y="{cy+8:.0f}" text-anchor="middle" '
                   f'font-size="24" font-weight="600" fill="{col}">{esc(item)}</text>')
    if s.get("overlap"):
        out.append(f'<text x="{cx:.0f}" y="{cy-42:.0f}" text-anchor="middle" '
                   f'font-size="25" font-weight="800" fill="var(--ink)">{esc(s["overlap"])}</text>')
    if s.get("labels"):
        for k, lbl in enumerate(s["labels"]):
            dx = (k - (len(sets) - 1) / 2) * r * 0.8
            out.append(f'<text x="{cx+dx:.0f}" y="{cy-r-14:.0f}" text-anchor="middle" '
                       f'font-size="30" font-weight="800" fill="var(--ink)">{esc(lbl)}</text>')
    return _wrap("".join(out), H)


# ── 9. 범용 폴백 (스펙이 어긋나도 크래시 없이 렌더) ─────────────
_SEV_COLOR = {"매우 높음": "#FF6B6B", "높음": "var(--warm)", "중간": "var(--accent)",
              "낮음": "#6ED4B3", "매우 낮음": "#6ED4B3"}


def _fallback_rows(rows, title=None):
    """임의의 dict 리스트를 라벨+서브텍스트 행으로 렌더한다."""
    n = len(rows)
    row_h, gap = 76, 16
    top = 46 if title else 8
    H = top + n * (row_h + gap) - gap + 16
    out = []
    if title:
        out.append(f'<text x="{CW/2:.0f}" y="30" text-anchor="middle" font-size="23" '
                   f'font-weight="600" fill="var(--muted)">{esc(title)}</text>')
    for i, it in enumerate(rows):
        if not isinstance(it, dict):
            it = {"label": str(it)}
        y = top + i * (row_h + gap)
        label = it.get("label") or it.get("name") or it.get("title") or it.get("key") or ""
        sub = it.get("sub") or it.get("desc") or it.get("description") or it.get("value") or ""
        sev = str(it.get("severity") or "")
        cname = str(it.get("color") or "").lower()
        col = _SEV_COLOR.get(sev) or {
            "red": "#FF6B6B", "green": "#6ED4B3", "orange": "var(--warm)",
            "warm": "var(--warm)", "blue": "var(--accent)",
        }.get(cname, "var(--accent)")
        out.append(f'<rect x="24" y="{y}" width="{CW-48}" height="{row_h}" rx="12" '
                   f'fill="{col}" fill-opacity=".10" stroke="{col}" '
                   f'stroke-opacity=".40" stroke-width="1.5"/>')
        if sub:
            out.append(f'<text x="52" y="{y+34:.0f}" font-size="25" font-weight="700" '
                       f'fill="{col}">{esc(str(label))}</text>')
            out.append(f'<text x="52" y="{y+62:.0f}" font-size="19" font-weight="500" '
                       f'fill="var(--muted)">{esc(str(sub)[:54])}</text>')
        else:
            out.append(f'<text x="52" y="{y+row_h/2+9:.0f}" font-size="26" font-weight="700" '
                       f'fill="{col}">{esc(str(label))}</text>')
    return _wrap("".join(out), int(H))


def _has_numeric(rows):
    for it in rows:
        if not isinstance(it, dict):
            continue
        for k in ("value", "v", "val", "percent", "pct"):
            val = it.get(k)
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                return True
    return False


def fallback(s):
    """스펙이 예상 스키마와 달라도 최소한 차트/텍스트로 렌더한다 (crash 방지)."""
    rows = []
    for key in ("items", "bars", "values", "blocks", "layers", "steps",
                "series", "parts", "rows", "sets", "data", "entries"):
        v = s.get(key)
        if isinstance(v, list) and v:
            rows = v
            break
    if not rows:
        rows = [{"label": str(k), "sub": str(v)} for k, v in s.items()
                if k not in ("kind", "title") and isinstance(v, (str, int, float))]
    if not rows:
        return _fallback_rows([], s.get("title") or "(시각자료 없음)")
    # 숫자 값이 있으면 막대 차트로 그린다
    if _has_numeric(rows):
        try:
            return bars({**s, "items": rows})
        except Exception:
            pass
    return _fallback_rows(rows, s.get("title"))


# ── 10. 표(테이블) 렌더러 ────────────────────────────────────────
def table(s):
    """마크다운 표를 SVG 표로 그린다. {headers:[...], rows:[[...],...]}"""
    headers = s.get("headers") or []
    rows = s.get("rows") or []
    ncol = 0
    if headers:
        ncol = max(ncol, len(headers))
    for r in rows:
        if isinstance(r, list):
            ncol = max(ncol, len(r))
    if ncol == 0:
        raise ValueError("table: empty")
    col_w = CW / ncol
    row_h = 58
    H = (len(rows) + (1 if headers else 0)) * row_h + 20
    out = []
    y = 10
    if headers:
        out.append(f'<rect x="0" y="{y}" width="{CW}" height="{row_h}" rx="10" '
                   f'fill="var(--accent)" fill-opacity=".16"/>')
        for j, h in enumerate(headers):
            out.append(f'<text x="{j*col_w+col_w/2:.0f}" y="{y+row_h/2+8:.0f}" '
                       f'text-anchor="middle" font-size="20" font-weight="800" '
                       f'fill="var(--accent)">{esc(str(h)[:16])}</text>')
        y += row_h + 6
    for i, r in enumerate(rows):
        if not isinstance(r, list):
            r = [r]
        if i % 2 == 1:
            out.append(f'<rect x="0" y="{y}" width="{CW}" height="{row_h-6}" rx="8" '
                       f'fill="var(--ink)" fill-opacity=".05"/>')
        for j in range(ncol):
            cell = r[j] if j < len(r) else ""
            col = "var(--ink)" if j == 0 else "var(--muted)"
            weight = 700 if j == 0 else 500
            out.append(f'<text x="{j*col_w+col_w/2:.0f}" y="{y+(row_h-6)/2+8:.0f}" '
                       f'text-anchor="middle" font-size="18" font-weight="{weight}" '
                       f'fill="{col}">{esc(str(cell)[:16])}</text>')
        y += row_h
    return _wrap("".join(out), int(H))


# BUILDERS (모든 draw 함수가 정의된 후에 위치해야 함)
BUILDERS = {"heatmap": heatmap, "bars": bars, "line": line,
            "flow": flow, "formula": formula, "compare": compare,
            "arch": arch, "venn": venn, "list": fallback, "table": table}


def build(spec):
    """어떤 스키마가 와도 크래시 없이 렌더한다.

    1) {"kind":..., "data": {...}} 형태면 data 키를 최상위로 펼친다.
    2) 빌더가 KeyError/TypeError 등으로 실패하면 범용 폴백으로 렌더한다.
    """
    if isinstance(spec, dict) and isinstance(spec.get("data"), dict):
        merged = {**spec, **spec["data"]}
        merged.pop("data", None)
        spec = merged
    kind = spec.get("kind")
    fn = BUILDERS.get(kind)
    if not fn:
        return fallback(spec)
    try:
        return fn(spec)
    except (KeyError, TypeError, ValueError, IndexError):
        return fallback(spec)