"""규칙 회귀 테스트 — 050 사고를 다시 잡아내는지 확인."""
import json, pathlib, sys
sys.path.insert(0, "/opt/data/ai_cardnews/scripts")
import rules

D = json.loads(pathlib.Path("/opt/data/ai_cardnews/content/queue/050-activation-functions.json")
               .read_text(encoding="utf-8"))


def run(name, mutate):
    d = json.loads(json.dumps(D))
    mutate(d)
    v = rules.evaluate(d)
    hi = [x for x in v if x.get("severity") == "high"]
    print(f"[{name}] high 위반 {len(hi)}건")
    for x in hi[:4]:
        print("   -", x.get("rule"), x.get("detail"))
    return len(hi)


print("--- 1) 050 원본 (본문 과다만 남아야 함) ---")
run("원본", lambda d: None)

print("\n--- 2) heatmap 을 잘못된 스펙으로 되돌리면? (050 사고 재현) ---")
def bad_heat(d):
    d["cards"][3]["visual"] = {"kind": "heatmap", "rows": None}
run("heatmap깨짐", bad_heat)

print("\n--- 3) visual 페이로드 삭제 ---")
run("페이로드삭제", lambda d: d["cards"][7].pop("visual", None))

print("\n--- 4) 본문 230자 초과 ---")
run("본문과다", lambda d: d["cards"][6].update({"body": "가" * 400}))

print("\n--- 5) 일본어 섞임 ---")
run("일본어", lambda d: d["cards"][2].update({"body": "これはテスト"}))
