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
| 7 | 2026-09-16 | 📝 036-multihead-attention 생성 (멀티헤드 어텐션) | — |
| 8 | 2026-09-17 | 📝 037-adam-optimizer 생성 (Adam) | — |
| 9 | 2026-09-17 | 📝 038-feedforward-layer 생성 (FFN) | — |
| 10 | 2026-09-17 | 📝 039-encoder-vs-decoder 생성 (인코더 vs 디코더) | — |
| 11 | 2026-09-18 | 📝 040-clip 생성 (CLIP) | — |
| 12 | 2026-09-19 | 📝 041-prompt-injection 생성 (프롬프트 인젝션의 원리) | — |
| 13 | 2026-09-20 | 📝 042-quantization 생성 (양자화 — 정밀도를 버려 속도를 얻는 마법) | — |
| 14 | 2026-09-21 | 📝 043-dropout 생성 (드롭아웃 — 일부러 망가뜨려 더 강해지기) | — |
| 15 | 2026-09-22 | 📝 044-softmax-temperature 생성 (소프트맥스와 온도 — 창의성 다이얼의 정체) | — |
| 16 | 2026-09-23 | 📝 045-chain-of-thought 생성 (CoT — 생각을 적으면 정답률이 오르는 이유) | — |
| 17 | 2026-09-24 | 📝 046-ensemble-always-wins 생성 (앙상블이 거의 항상 이기는 이유) | — |
| 18 | 2026-09-25 | 📝 047-mamba-ssm 생성 (상태공간 모델 — Mamba와 SSM) | — |
| 19 | 2026-09-26 | 📝 048-self-supervised-learning 생성 (자기지도학습 — SSL) | — |
| 20 | 2026-09-27 | 📝 049-batch-inference-continuous-batching 생성 (배치 추론과 연속 배칭) | — |
| 21 | 2026-09-28 | 📝 050-activation-functions 생성 (활성화 함수 — ReLU가 이긴 이유) | — |
| 22 | 2026-09-29 | 📝 051-overfitting-generalization 생성 (과적합과 일반화) | — |
| 23 | 2026-09-30 | 📝 052-mixed-precision 생성 (혼합 정밀도 — FP16/BF16) | — |
| 24 | 2026-09-30 | 📝 053-lr-scheduling-warmup 생성 (학습률 스케줄링과 웜업) | — |
| 25 | 2026-10-02 | 📝 054-flow-matching 생성 (플로우 매칭 — 확산의 다음 세대) | — |
| 26 | 2026-10-03 | 📝 055-bert-vs-gpt 생성 (BERT vs GPT — 10년 대립의 진실) | — |
| 27 | 2026-10-04 | 📝 056-pruning-and-sparsity 생성 (가지치기와 희소성 — 모델 다이어트) | — |
| 28 | 2026-10-05 | 📝 057-gradient-vanishing-explosion 생성 (기울기 소실과 폭발 — 딥러닝 빙하기를 깬 기술) | — |
| 29 | 2026-10-06 | 📝 058-scaling-laws 생성 (스케일링 법칙 — 3가지 법칙과 테스트타임 컴퓨팅 혁명) | — |
| 30 | 2026-10-07 | 📝 059-gradient-clipping 생성 (그래디언트 클리핑 — AGGC와 스펙트럴 클리핑) | — |
| 31 | 2026-10-08 | 📝 060-regularization-l1-l2-weight-decay 생성 (정규화 — L1, L2, 그리고 가중치 감쇠) | — |
| 32 | 2026-10-09 | 📝 061-emergence-debate 생성 (창발 논쟁 — 진짜 도약인가 지표의 착시인가) | — |
| 33 | 2026-10-10 | 📝 062-tokenizer-bpe 생성 (토크나이저와 BPE — 모델이 보는 건 글자가 아니다) | — |
|| 34 | 2026-10-11 | 📝 063-reward-hacking 생성 (보상 해킹 — AI가 보상을 속이는 법) | — |
|| ... | ... | ... | ... |
| 100 | 2026-12-19 | 🏁 1000명 달성 | 0/1000 |

> 이 트래커는 매일 02:00 KST에 Hermes 크론이 자동 업데이트합니다.
> 구독자 수는 수동으로 업데이트해주세요.