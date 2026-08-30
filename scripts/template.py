"""카드뉴스 HTML 템플릿 (1080x1350, 인스타 4:5)."""

import html

import diagrams

W, H = 1080, 1350

CSS = """
* { margin:0; padding:0; box-sizing:border-box; }

:root{
  --bg:#0B1020;
  --bg2:#0E1428;
  --ink:#EEF2FF;
  --muted:#93A0C4;
  --line:rgba(255,255,255,.10);
  --accent:#7C9CFF;
  --accent2:#FFB870;
  --warm:#FFB870;      /* 다이어그램 강조색 */
}

body{
  background:#050710;
  font-family:"Noto Sans CJK KR","Noto Sans KR",sans-serif;
  -webkit-font-smoothing:antialiased;
  text-rendering:optimizeLegibility;
  word-break:keep-all;          /* 한글 어절 단위 줄바꿈 */
  overflow-wrap:break-word;
}

.card{
  position:relative;
  width:1080px; height:1350px;
  padding:78px 86px 68px;
  display:flex; flex-direction:column;
  background:var(--bg);
  color:var(--ink);
  overflow:hidden;
  margin-bottom:40px;
}

/* 배경 장식 */
.card::before{
  content:""; position:absolute; inset:0;
  background-image:radial-gradient(rgba(255,255,255,.055) 1px, transparent 1px);
  background-size:34px 34px;
  opacity:.55;
}
.glow{
  position:absolute; border-radius:50%; filter:blur(120px); opacity:.30; pointer-events:none;
}
.glow.a{ width:640px; height:640px; background:var(--accent); top:-260px; right:-220px; }
.glow.b{ width:520px; height:520px; background:#3B2E7A; bottom:-260px; left:-200px; opacity:.42; }

.card.insight{ --accent:var(--accent2); --warm:#7C9CFF; background:#0D0A1C; }
.card.insight .glow.a{ background:#FF9A4D; opacity:.24; }
.card.insight .glow.b{ background:#5B2E6E; opacity:.40; }

.card.cover{ background:linear-gradient(160deg,#0C1226 0%,#0A0E1F 55%,#0D0A1C 100%); }

/* 상·하단 바 */
.topbar,.bottombar{
  position:relative; z-index:2;
  display:flex; align-items:center; justify-content:space-between;
  font-size:23px; letter-spacing:.01em; color:var(--muted);
  flex:0 0 auto;
}
.topbar{ padding-bottom:30px; border-bottom:1px solid var(--line); }
.bottombar{ padding-top:26px; border-top:1px solid var(--line); font-size:22px; }
.series{ display:flex; align-items:center; gap:14px; font-weight:500; }
.series .dot{ width:11px; height:11px; border-radius:50%; background:var(--accent); box-shadow:0 0 18px var(--accent); }
.pager{ font-variant-numeric:tabular-nums; font-weight:500; letter-spacing:.06em; }
.pager b{ color:var(--ink); font-weight:700; }
.handle{ font-weight:500; letter-spacing:.02em; }
.tag{ color:var(--accent); font-weight:700; letter-spacing:.04em; }

/* 본문 무대 */
.stage{ position:relative; z-index:2; flex:1 1 auto; min-height:0; display:flex; overflow:hidden; }
.stage.center{ align-items:center; }
.stage.top{ align-items:center; }
.inner{ width:100%; font-size:calc(var(--s,1) * 16px); }

/* 표지 */
.eyebrow{
  display:inline-block; font-size:1.6em; font-weight:700; letter-spacing:.14em;
  color:var(--accent); margin-bottom:1.5em;
}
.cover-title{
  font-size:5.5em; font-weight:900; line-height:1.24; letter-spacing:-.022em;
}
.cover-title .hl{
  background:linear-gradient(transparent 62%, rgba(124,156,255,.30) 62%);
  padding:0 .06em;
}
.rule{ width:132px; height:7px; border-radius:4px; background:var(--accent); margin:1.5em 0 1.1em; }
.cover-sub{ font-size:2.15em; line-height:1.62; color:var(--muted); font-weight:400; max-width:27ch; }

/* 본문 카드 */
.kicker{
  display:flex; align-items:baseline; gap:.6em;
  font-size:1.55em; font-weight:800; letter-spacing:.12em; color:var(--accent);
  margin-bottom:1.2em;
}
.kicker .num{ font-size:1.5em; letter-spacing:0; }
.heading{
  font-size:3.35em; font-weight:900; line-height:1.34; letter-spacing:-.02em;
  margin-bottom:.72em;
}
.para{ font-size:2.08em; line-height:1.72; color:#D3DAF0; font-weight:400; letter-spacing:-.005em; }
.para + .para{ margin-top:.85em; }
.para .em{ color:#fff; font-weight:700; }
.para .code{
  font-family:"DejaVu Sans Mono",monospace; font-size:.92em;
  background:rgba(124,156,255,.14); color:#BFD0FF;
  padding:.08em .38em; border-radius:6px;
}

.note{
  margin-top:1.5em; padding:1.15em 1.35em;
  background:rgba(255,255,255,.045);
  border-left:6px solid var(--accent);
  border-radius:0 14px 14px 0;
}
.note .nlabel{
  font-size:1.42em; font-weight:800; letter-spacing:.1em; color:var(--accent);
  display:block; margin-bottom:.55em;
}
.note .ntext{ font-size:1.88em; line-height:1.66; color:#C9D2EC; }

.chips{ display:flex; flex-wrap:wrap; gap:.6em; margin-top:1.5em; }
.chip{
  font-size:1.5em; font-weight:600; color:#C3CFF5;
  border:1px solid rgba(124,156,255,.42); background:rgba(124,156,255,.10);
  padding:.42em .9em; border-radius:999px;
}

/* 인사이트 카드 */
.badge{
  display:inline-block; font-size:1.48em; font-weight:800; letter-spacing:.1em;
  color:#0D0A1C; background:var(--accent2);
  padding:.5em 1.05em; border-radius:999px; margin-bottom:1.35em;
}
.bullets{ list-style:none; margin-top:1.3em; }
.bullets li{
  position:relative; padding-left:1.5em; margin-top:.85em;
  font-size:2.0em; line-height:1.66; color:#D6DCF2;
}
.bullets li::before{
  content:""; position:absolute; left:0; top:.62em;
  width:.42em; height:.42em; border-radius:50%; background:var(--accent2);
}
.bullets li b{ color:#fff; font-weight:700; }

/* 시각화 카드 */
.dia{ display:block; margin:.2em 0 0; overflow:visible; }
.vcap{
  margin-top:1.4em; padding-top:1.1em; border-top:1px solid var(--line);
  font-size:1.92em; line-height:1.62; color:#C9D2EC; font-weight:400;
}
.vcap .em{ color:#fff; font-weight:700; }
.vlead{ font-size:1.98em; line-height:1.66; color:#D3DAF0; margin-bottom:1.1em; }

/* 마지막 CTA */
.cta{
  margin-top:1.7em; padding:1.25em 1.4em;
  border:1px solid rgba(255,184,112,.40); border-radius:18px;
  background:rgba(255,184,112,.08);
  font-size:1.92em; line-height:1.6; color:#F0E2D2; font-weight:500;
}
.swipe{
  position:absolute; right:86px; bottom:120px; z-index:3;
  font-size:24px; color:var(--muted); font-weight:600; letter-spacing:.04em;
  display:flex; align-items:center; gap:10px;
}
.swipe .arrow{ font-size:30px; color:var(--accent); }
"""

FIT_JS = """
document.querySelectorAll('.card').forEach(card => {
  const stage = card.querySelector('.stage');
  const inner = card.querySelector('.inner');
  let s = 1.0;
  let guard = 0;
  while (inner.scrollHeight > stage.clientHeight && s > 0.62 && guard < 80) {
    s -= 0.02; guard++;
    inner.style.setProperty('--s', s.toFixed(3));
  }
});
"""


def esc(t):
    """텍스트 이스케이프 + 인라인 마크업(**강조**, `코드`) 지원."""
    t = html.escape(str(t))
    out, i = [], 0
    while True:
        a = t.find("**", i)
        if a == -1:
            out.append(t[i:])
            break
        b = t.find("**", a + 2)
        if b == -1:
            out.append(t[i:])
            break
        out.append(t[i:a])
        out.append('<span class="em">' + t[a + 2:b] + "</span>")
        i = b + 2
    t = "".join(out)
    out, i = [], 0
    while True:
        a = t.find("`", i)
        if a == -1:
            out.append(t[i:])
            break
        b = t.find("`", a + 1)
        if b == -1:
            out.append(t[i:])
            break
        out.append(t[i:a])
        out.append('<span class="code">' + t[a + 1:b] + "</span>")
        i = b + 1
    return "".join(out)


def paras(text):
    return "".join(f'<p class="para">{esc(p.strip())}</p>'
                   for p in str(text).split("\n") if p.strip())


def render_card(card, idx, total, meta):
    kind = card.get("type", "body")
    klass = {"cover": "cover", "insight": "insight"}.get(kind, "body")
    series = esc(meta.get("series_label", "AI 이론 한 장 정리"))
    no = meta.get("series_no")
    handle = esc(meta.get("handle", ""))
    topic = esc(meta.get("topic", ""))

    top_left = f'<div class="series"><span class="dot"></span>{series}</div>'
    if no:
        top_right = f'<div class="pager">EP.{int(no):03d}</div>' if kind == "cover" \
            else f'<div class="pager"><b>{idx}</b> / {total}</div>'
    else:
        top_right = f'<div class="pager"><b>{idx}</b> / {total}</div>'

    bottom_left = f'<div class="handle">{handle}</div>'
    bottom_right = f'<div class="tag">{topic}</div>' if kind != "cover" else \
        '<div class="tag">SAVE &amp; SHARE</div>'

    swipe = ""
    if kind == "cover":
        title = esc(card.get("title", ""))
        for w in card.get("highlight", []) or []:
            title = title.replace(esc(w), f'<span class="hl">{esc(w)}</span>')
        body = (f'<div class="eyebrow">{esc(card.get("eyebrow","오늘의 AI 이론"))}</div>'
                f'<h1 class="cover-title">{title}</h1>'
                f'<div class="rule"></div>'
                f'<p class="cover-sub">{esc(card.get("subtitle",""))}</p>')
        align = "center"
        swipe = ('<div class="swipe"><span>밀어서 보기</span>'
                 '<span class="arrow">&#8250;&#8250;</span></div>')
    elif kind == "visual":
        body = ""
        if card.get("kicker") or card.get("kicker_label"):
            body += (f'<div class="kicker"><span class="num">{idx:02d}</span>'
                     f'<span>{esc(card.get("kicker_label",""))}</span></div>')
        body += f'<h2 class="heading">{esc(card.get("heading",""))}</h2>'
        if card.get("lead"):
            body += f'<p class="vlead">{esc(card["lead"])}</p>'
        body += diagrams.build(card["visual"])
        if card.get("caption"):
            body += f'<div class="vcap">{esc(card["caption"])}</div>'
        align = "center"

    elif kind == "insight":
        body = f'<div class="badge">{esc(card.get("label","실무자 인사이트"))}</div>'
        body += f'<h2 class="heading">{esc(card.get("heading",""))}</h2>'
        body += paras(card.get("body", ""))
        if card.get("bullets"):
            body += '<ul class="bullets">' + "".join(
                f"<li>{esc(b)}</li>" for b in card["bullets"]) + "</ul>"
        if card.get("cta"):
            body += f'<div class="cta">{esc(card["cta"])}</div>'
        align = "top"
    else:
        body = ""
        if card.get("kicker") or card.get("kicker_label"):
            # 번호는 캐러셀 페이지와 항상 일치시킨다 (원고의 kicker 값은 무시)
            body += (f'<div class="kicker"><span class="num">{idx:02d}</span>'
                     f'<span>{esc(card.get("kicker_label",""))}</span></div>')
        body += f'<h2 class="heading">{esc(card.get("heading",""))}</h2>'
        body += paras(card.get("body", ""))
        if card.get("note"):
            n = card["note"]
            body += (f'<div class="note"><span class="nlabel">'
                     f'{esc(n.get("label","쉽게 말하면"))}</span>'
                     f'<div class="ntext">{esc(n.get("text",""))}</div></div>')
        if card.get("chips"):
            body += '<div class="chips">' + "".join(
                f'<span class="chip">{esc(c)}</span>' for c in card["chips"]) + "</div>"
        align = "top"

    return f"""<div class="card {klass}">
  <div class="glow a"></div><div class="glow b"></div>
  <div class="topbar">{top_left}{top_right}</div>
  <div class="stage {align}"><div class="inner">{body}</div></div>
  {swipe}
  <div class="bottombar">{bottom_left}{bottom_right}</div>
</div>"""


def build_html(data):
    cards = data["cards"]
    total = len(cards)
    body = "\n".join(render_card(c, i + 1, total, data) for i, c in enumerate(cards))
    return (f"<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
            f"<style>{CSS}</style></head><body>{body}"
            f"<script>{FIT_JS}</script></body></html>")
