import json, pathlib
p = pathlib.Path("/opt/data/ai_cardnews/content/queue/050-activation-functions.json")
d = json.loads(p.read_text(encoding="utf-8"))
for i in (2, 3, 5, 7):
    c = d["cards"][i - 1]
    b = c.get("body", "")
    print(f"===== {i}번 ({len(b)}자) | heading: {c.get('heading','')} =====")
    print(b)
    print()
