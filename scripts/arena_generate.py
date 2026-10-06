#!/usr/bin/env python3
"""Arena: generate 3 candidate cardnews articles via OpenRouter API.

Usage: python arena_generate.py <number> <topic>
"""
import json
import os
import pathlib
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUTDIR = pathlib.Path("/tmp/arena-057")

# Load API key
env_path = pathlib.Path("/opt/data/.env")
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if line.startswith("OPENROUTER_API_KEY="):
            os.environ["OPENROUTER_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")
            break

API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
if not API_KEY or API_KEY == "***":
    print("ERROR: No OPENROUTER_API_KEY found", file=sys.stderr)
    sys.exit(1)

SYSTEM_PROMPT = """You are an expert AI educator creating cardnews (카드뉴스) for Instagram in Korean.
Each card is a compact, visually-oriented slide designed for mobile consumption.

RULES:
1. ALL text must be Korean ONLY. No Japanese (히라가나/가타카나/한자) or Chinese.
2. English tech terms: write in Korean pronunciation first then (English) in parentheses.
   Example: "어텐션(Attention)". Exception: proper model names (GPT, BERT, CLIP) stay in English.
3. Cover title must be exactly 3 lines, provocative, ending with ~다/~이다 assertion.
4. Cards: 8-10 total (결론 카드 포함). At least 40% (4+) must be type=visual with visual payload.
5. **CARD ORDER — 마지막 두 장은 반드시 이 순서다:**
   ... (본문/시각화 카드들) → {"type":"conclusion"} → {"type":"insight"}
   즉 **'실무자 인사이트'(insight) 바로 앞에 '결론'(conclusion) 카드**가 온다.
   conclusion 카드는 "이것만 가져가라" 성격의 서머리다. **heading 은 매회 고정이다:**
   {"type":"conclusion","label":"결론","heading":"이것만 가져가시면 됩니다",
    "body":"<90자 이하 한 문장 — 글 전체를 관통하는 결론>",
    "bullets":["<55자 이하>","<55자 이하>","<55자 이하>"]}
   bullets 는 서로 다른 축(원리/수치/적용)을 담고, 원고에 없는 숫자를 새로 만들지 마라.
   insight 카드는 언제나 **마지막 장**이다.
6. Each body card: max 230 chars Korean, use \\n for paragraph breaks.
7. Include examples, analogies, and practical insights.
8. Output ONLY valid JSON. No markdown fences, no extra text."""

def call_model(messages, model="deepseek/deepseek-v4-flash", temperature=0.7):
    """Call OpenRouter API and return response content."""
    data = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 4000,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        },
    )
    try:
        resp = urllib.request.urlopen(req, timeout=120)
        result = json.loads(resp.read())
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        return f"ERROR: {e}"

def extract_json(text):
    """Extract JSON object from response text (handles markdown fences)."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        start = 1 if lines[0].startswith("```") else 0
        end = -1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[start:end])
    # Find first { and last }
    s = text.find("{")
    e = text.rfind("}")
    if s >= 0 and e > s:
        text = text[s:e+1]
    return json.loads(text)

def get_current_events_context():
    """Return a string of current AI events for October 2026."""
    context = """2026년 10월 AI 트렌드:
- GPT-6.1 Sol 출시: GPT-6 Sol 업그레이드 버전, 에이전트 코딩 성능 향상, $2/$10 per M tokens
- Google Gemini 4 Argon: 100만 토큰 출력, DeepSWE 77.9%, 사이버보안 우선 배포
- Claude Sonnet 5.5: $2/$10 동일 가격 — 프론티어 모델 3사 동일 가격 경쟁
- DeepSeek V41: 로컬 GPU 없는 환경에서도 프론티어 모델 실행 가능한 ds4 런타임
- FTC, OpenAI/Anthropic 조사 개시 — 제품 리스크 관련
- Cloudflare Clef/Clef-flash: 자체 훈련한 첫 모델, Apache 2.0 오픈소스
- MSign optimizer: 안정 랭크 복원으로 LLM 훈련 폭발 방지 (arXiv 2602.01734)
- Keel: Highway 연결로 1000층 Post-LN 트랜스포머 안정 훈련 (arXiv 2601.19895)
- 미국 AI 관련 해고 12만 명 돌파 (2026년, Challenger data)
- Tavus Griffin: 실시간 비디오 튜링 테스트 통과 (48%가 사람으로 착각)
- Armadin: $255.5M 시리즈 B (AI 사이버보안)"""
    return context

# —— Candidate prompts ——

def candidate_1_prompt(number, topic):
    return [
        {"role": "system", "content": SYSTEM_PROMPT + "\n\nFocus: Clear explanations with strong everyday analogies. Make complex concepts accessible to beginners."},
        {"role": "user", "content": f"""Create a cardnews article (episode #{number}) about "{topic}" (기울기 소실과 폭발 - Vanishing/Exploding Gradients).

This is B-track (딥러닝 기초) for Monday release — target: beginners and intermediate learners.

Current events to reference in caption/hook:
{get_current_events_context()}

Requirements:
- Cover: 3-line provocative title ending with ~다/~이다
- 8-10 cards total, at least 4 visual cards (type=visual with visual payload)
- Explain: what vanishing/exploding gradients are, why they happen (chain rule multiplication), historical crisis, and modern solutions
- Visuals: gradient flow comparison (bars), activation function gradients (line/compare), solution timeline (flow or bars)
- Body cards: use analogies (factory assembly line, car accelerating downhill, etc.)
- Insight card: practical debugging tips (gradient clipping, proper init, normalization)
- Caption: 3-4 paragraphs connecting to 2026 trends
- Hashtags: 20-25

Output as JSON matching this schema:
{{
  "series_no": {number},
  "topic": "{topic}",
  "source": "growth",
  "cards": [
    {{"type": "cover", "eyebrow": "🔥 이모지 포함 세 줄", "title": "도발적\\n3줄\\n헤드라인", "highlight": ["핵심"], "subtitle": "한 줄 요약"}},
    ... body/visual/insight cards ...
  ],
  "caption": "3~4문단",
  "hashtags": ["#태그1", ...]
}}
""" + "\n\nReturn ONLY valid JSON."}
    ]

def candidate_2_prompt(number, topic):
    return [
        {"role": "system", "content": SYSTEM_PROMPT + "\n\nFocus: VISUAL-FIRST approach. Design at least 5 visual cards with strong charts. Each visual must have a meaningful data story. Use bars, line, compare, flow kinds."},
        {"role": "user", "content": f"""Create a cardnews article (episode #{number}) about "{topic}" (기울기 소실과 폭발 - Vanishing/Exploding Gradients).

This is B-track (딥러닝 기초) for Monday release. Use current trends for relevance:
{get_current_events_context()}

MAKE IT VISUAL HEAVY:
- 10 cards total
- Cover: 3-line provocative
- AT LEAST 5 visual cards with these chart ideas:
  1. bars: "층별 그래디언트 크기" — 얕은 층 vs 깊은 층에서 gradient 크기 비교 (시그모이드 vs ReLU)
  2. line: "시그모이드 함수의 기울기 소실" — x=-5~5, 기울기가 0에 가까워지는 구간
  3. compare: "시그모이드 vs ReLU" — 기울기 전파 특성 비교
  4. flow: "역전파에서 기울기가 소실되는 과정" — 단계별 흐름
  5. bars: "현대 솔루션 효과 비교" — 초기화/정규화/잔차 연결/그래디언트 클리핑
- Insight card with practical debugging checklist
- Strong caption connecting to 2026 trends (MSign, Keel, 1000-layer models)

Output as JSON. Return ONLY valid JSON.
{{
  "series_no": {number},
  "topic": "{topic}",
  "source": "growth",
  "cards": [...],
  "caption": "...",
  "hashtags": ["#태그1", ...]
}}""" + "\n\nReturn ONLY valid JSON."}
    ]

def candidate_3_prompt(number, topic):
    return [
        {"role": "system", "content": SYSTEM_PROMPT + "\n\nFocus: TECHNICAL DEPTH with practical engineering insights. Target intermediate-level readers who know basic backprop. Include actual numbers, paper references, and code-friendly explanations."},
        {"role": "user", "content": f"""Create a cardnews article (episode #{number}) about "{topic}" (기울기 소실과 폭발 - Vanishing/Exploding Gradients).

This is B-track for Monday release. Connect to cutting-edge 2026 research:
{get_current_events_context()}

TECHNICAL EMPHASIS:
- 8-9 cards total, at least 4 visual
- Cover: 3-line provocative, hook = "500층 신경망이 가능했던 비밀"
- Deep explanations of:
  1. Why chain rule causes exponential decay/growth in gradients
  2. Sigmoid's saturation region (|gradient| < 0.25 → 0^L for L layers)
  3. Modern solutions: Xavier/He init, Batch/LayerNorm, ReLU, Residual connections, Gradient clipping
  4. 2026 cutting-edge: MSign optimizer (stable rank restoration), Keel (Highway for 1000-layer Post-LN)
- Visuals:
  1. bars: "활성화 함수별 기울기 범위" — sigmoid(0~0.25), tanh(0~1), ReLU(0 or 1), GELU
  2. line: "층 깊이에 따른 기울기 크기 변화" — 10층부터 100층까지
  3. compare: "고전 해결책 vs 2026 최신 기법"
  4. table: "문제 진단 체크리스트"
- Insight card: training debugging checklist
- Caption: connect to real-world cost of gradient explosion (wasted training runs)

Output as JSON. Return ONLY valid JSON.
{{
  "series_no": {number},
  "topic": "{topic}",
  "source": "growth",
  "cards": [...],
  "caption": "...",
  "hashtags": ["#태그1", ...]
}}""" + "\n\nReturn ONLY valid JSON."}
    ]

def main():
    number = sys.argv[1] if len(sys.argv) > 1 else "057"
    topic = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "기울기 소실과 폭발(Vanishing/Exploding Gradients)"

    OUTDIR.mkdir(parents=True, exist_ok=True)

    prompts = [
        ("candidate-1-prompt", candidate_1_prompt(number, topic)),
        ("candidate-2-prompt", candidate_2_prompt(number, topic)),
        ("candidate-3-prompt", candidate_3_prompt(number, topic)),
    ]

    results = []

    for name, msgs in prompts:
        print(f"\n=== Generating {name}... ===")
        raw = call_model(msgs, temperature=0.7)
        # Save raw response
        raw_path = OUTDIR / f"{name}.raw.txt"
        raw_path.write_text(raw, encoding="utf-8")
        print(f"Raw response length: {len(raw)} chars")
        print(f"First 200 chars: {raw[:200]}")

        try:
            parsed = extract_json(raw)
            out_path = OUTDIR / f"{name.replace('-prompt', '')}.json"
            out_path.write_text(
                json.dumps(parsed, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8"
            )
            cards = parsed.get("cards", [])
            visual_count = sum(1 for c in cards if c.get("type") == "visual")
            print(f"  ✅ Parsed OK — {len(cards)} cards, {visual_count} visual")
            results.append((name.replace("-prompt", ""), parsed, True))
        except Exception as e:
            print(f"  ❌ Parse error: {e}")
            results.append((name.replace("-prompt", ""), None, False))

    # Summary
    print("\n" + "=" * 50)
    print("ARENA GENERATION SUMMARY")
    print("=" * 50)
    for name, data, ok in results:
        status = "✅" if ok else "❌"
        cards_n = len(data.get("cards", [])) if data else 0
        visual_n = sum(1 for c in data.get("cards", []) if c.get("type") == "visual") if data else 0
        print(f"  {status} {name}: {cards_n} cards, {visual_n} visual")
    print(f"\nFiles saved in: {OUTDIR}")

if __name__ == "__main__":
    main()