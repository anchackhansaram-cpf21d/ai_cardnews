# AI 이론 카드뉴스 자동 발행

매일 한국시간 11:30에 AI 이론 카드뉴스 10장을 인스타그램 캐러셀로 자동 발행합니다.
GitHub Actions가 이미지를 만들고, 인스타그램 Graph API로 올립니다.

## 가장 먼저 할 일

`config.json`의 `handle`을 본인 인스타 아이디로 바꾸세요. 모든 카드 하단에 찍힙니다.

```json
{
  "handle": "@your_instagram_id",
  "series_title": "AI 이론 한 장"
}
```

## 스크립트 사용법

```bash
# 새 원고 만들기
python scripts/new.py "내용"

# 렌더링 (특정 slug)
python scripts/render.py --slug 001-attention

# 발행
python scripts/publish.py --slug 001-attention

# 마크다운으로 받아보기
python scripts/md.py 001-attention
```

## 카드 디자인

10장 카드뉴스. 각 카드에는 `handle`이 하단에 찍힙니다.
- 1장 표지
- 8장 본문
- 1장 마무리

---

## 100일 트래커

**목표: 100일 안에 인스타그램 구독자 1000명**

`@dora_studyzy` → 구독자 1000명

| Day | 날짜 (KST) | 액션 | 구독자 |
|-----|-----------|------|--------|
| 1 | 2026-09-11 | 🚀 성장 엔진 가동 | — |
| 2 | 2026-09-12 | 📝 031-hallucination 생성 | — |
| 3 | 2026-09-13 | 📝 032-diffusion 생성 (확산 모델) | — |
| 4 | 2026-09-14 | 📝 033-sparse-autoencoder 생성 (SAE와 특징 분해) | — |
| 5 | 2026-09-14 | 📝 034-speculative-decoding 생성 (추측 디코딩) | — |
| 6 | 2026-09-15 | 📝 035-moe 생성 (MoE — 파라미터는 크고 연산은 작게) | — |
| 7 | 2026-09-16 | 📝 036-multihead-attention 생성 (멀티헤드 어텐션 — 왜 여러 개의 눈이 필요한가) | — |
| 8 | 2026-09-17 | 📝 037-adam-optimizer 생성 (Adam — 왜 기본값이 되었나) | — |
| 9 | 2026-09-17 | 📝 038-feedforward-layer 생성 (FFN — 트랜스포머 파라미터의 3분의 2가 여기 있다) | — |
| ... | ... | ... | ... |
| 100 | 2026-12-20 | 🏁 1000명 달성 | 0/1000 |

> 이 트래커는 매일 02:00 KST에 Hermes 크론이 자동 업데이트합니다.
> 구독자 수는 수동으로 업데이트해주세요.