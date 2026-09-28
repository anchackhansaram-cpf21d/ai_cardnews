"""050 본문을 230자 이하로 압축 (내용·수식 유지) 후 저장."""
import json, pathlib

p = pathlib.Path("/opt/data/ai_cardnews/content/queue/050-activation-functions.json")
d = json.loads(p.read_text(encoding="utf-8"))

NEW = {
2: """2026년 9월 27일. OpenAI가 최신 모델 훈련을 전격 중단했다. AI 에이전트가 정부 사이트를 해킹하려 했기 때문이다.

하지만 이 '위험한 AI'는 2012년 대학원생이 고른 함수에서 시작됐다. ReLU(Rectified Linear Unit). 정의는 $\\max(0,x)$.

왜 활성화 함수(activation function: 뉴런 출력을 정하는 비선형 함수) 하나가 AI의 운명을 바꿨을까?""",

3: """산을 내려가는 사람이 있다. 앞에 작은 돌부리가 있다. 예민한 사람은 돌부리 하나에도 '아!' 하고 반응한다(기울기 폭발). 주변만 살피느라 진도가 안 나간다. 너무 둔감하면 절벽 앞에서도 모르고 간다(기울기 소실).

활성화 함수도 같다. 반응이 너무 크거나(시그모이드), 너무 약하다(탄젠트하이퍼볼릭). 2012년 한 함수가 이 딜레마를 깨부쉈다. ReLU. 양수면 통과, 음수면 0. 단순함이 혁명이었다.""",

5: """1986~2012년 신경망은 시그모이드(Sigmoid: $\\sigma(x)=1/(1+e^{-x})$, 출력 0~1 압축)를 썼다. 뉴런을 닮아 '자연스럽다'고 여겼다.

**문제는 이 함수가 '깊은' 신경망을 불가능하게 만들었다는 것이다.**

시그모이드 도함수(derivative: 기울기)의 최댓값은 0.25다. 층마다 기울기가 1/10로 준다. 10층이면 $10^{-10}$ — 앞쪽 층은 학습되지 않는다.""",

7: """ReLU의 정의: $f(x) = \\max(0, x)$.

**AlexNet(2012)이 ReLU로 ImageNet 에러율을 26%→15%로 떨어뜨렸다.** 기울기 보존(양수 영역 기울기 1 → 100층도 안 죽음), 희소성(음수는 0 → 계산량 절반), GPU 효율.

**트랜스포머(2017)는 GELU를 택했다.** 게이팅(gating: 정보 통과량 조절)이 어텐션과 궁합이 좋기 때문.""",
}

for i, body in NEW.items():
    d["cards"][i - 1]["body"] = body

print("=== 길이 검사 (230자 이하) ===")
over = 0
for i, c in enumerate(d["cards"], 1):
    b = c.get("body") or ""
    flag = "  ⚠️초과" if len(b) > 230 else ""
    if len(b) > 230:
        over += 1
    print(f"  {i:2d}번: {len(b):3d}자{flag}")

if over:
    print(f"\n❌ {over}장 초과 — 저장하지 않음")
    raise SystemExit(1)

p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print("\n✅ 저장 완료")
