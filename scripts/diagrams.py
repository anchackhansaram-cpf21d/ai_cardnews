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
    # 라벨 + 격자를 한 덩어리로 보고 카드 가운데에 놓는다
    x0 = (CW - (lab_w + gw)) / 2 + lab_w
    y0 = lab_h + 8
    H = int(y0 + n_r * (cell + gap) - gap + 16)

    # 지표마다 범위가 다르면 열 단위로 정규화해야 차이가 보인다
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
            # text 행렬이 있으면 숫자 대신 그 문자열을 찍는다
            cellstr = s["text"][i][j] if s.get("text") else f"{v:.2f}"
            fsz = 22 if len(str(cellstr)) <= 4 else 19
            out.append(f'<text x="{cx+cell/2:.1f}" y="{cy+8:.1f}" text-anchor="middle" '
                       f'font-size="{fsz}" font-weight="700" fill="{fill}">'
                       f'{esc(cellstr)}</text>')
    return _wrap("".join(out), H)


# ── 2. 가로 막대 ────────────────────────────────────────────────
def bars(s):
    items = s["items"]
    unit = s.get("unit", "")
    lab_w = 250
    bar_h, gap = 62, 26
    H = len(items) * (bar_h + gap) - gap + 16
    # 눈금 최대값을 직접 지정할 수 있게 한다. 지정하지 않으면 차이가 과장된다.
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
        # show_values:false 이면 막대 길이로 상대 비교만 보여준다
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
    H = 470
    pad_l, pad_r, pad_t, pad_b = 86, 34, 26, 74
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
            out.append(f'<text x="{sx(ex)-14:.1f}" y="{sy(ey)-26:.1f}" text-anchor="end" '
                       f'font-size="23" font-weight="700" fill="{col}">'
                       f'{esc(sr["label"])}</text>')

    if s.get("xlabel"):
        out.append(f'<text x="{pad_l+w/2:.0f}" y="{H-22}" text-anchor="middle" '
                   f'font-size="22" font-weight="500" fill="var(--muted)">'
                   f'{esc(s["xlabel"])}</text>')
    if s.get("ylabel"):
        out.append(f'<text transform="translate(28,{pad_t+h/2:.0f}) rotate(-90)" '
                   f'text-anchor="middle" font-size="22" font-weight="500" '
                   f'fill="var(--muted)">{esc(s["ylabel"])}</text>')
    for a in s.get("ticks", []):
        out.append(f'<text x="{sx(a[0]):.0f}" y="{pad_t+h+34}" text-anchor="middle" '
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
    parts = s["parts"]           # [{text, note}]
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


BUILDERS = {"heatmap": heatmap, "bars": bars, "line": line,
            "flow": flow, "formula": formula, "compare": compare}


def build(spec):
    kind = spec.get("kind")
    fn = BUILDERS.get(kind)
    if not fn:
        raise ValueError(f"알 수 없는 visual kind: {kind} "
                         f"(가능: {', '.join(BUILDERS)})")
    return fn(spec)
