"""재발행을 위해 state.json 에서 050 을 posted 목록에서 제거."""
import json, pathlib

p = pathlib.Path("/opt/data/ai_cardnews/state.json")
d = json.loads(p.read_text(encoding="utf-8"))
SLUG = "050-activation-functions"

before = len(d.get("posted", []))
d["posted"] = [s for s in d.get("posted", []) if s != SLUG]
d["log"] = [e for e in d.get("log", []) if e.get("slug") != SLUG]
p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

print(f"posted: {before} → {len(d['posted'])}")
print("마지막:", d["posted"][-3:])
print("050 남아있나:", SLUG in d["posted"])
