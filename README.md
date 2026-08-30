# AI 이론 카드뉴스 자동 발행

매일 한국시간 11:30에 AI 이론 카드뉴스 10장을 인스타그램 캐러셀로 자동 발행합니다.
GitHub Actions가 이미지를 만들고, 인스타그램 Graph API로 올립니다.

## 가장 먼저 할 일

`config.json`의 `handle`을 본인 인스타 아이디로 바꾸세요. 모든 카드 하단에 찍힙니다.

```json
{ "handle": "@내아이디", "series_label": "AI 이론 한 장 정리" }
```

## 구조

```
config.json            핸들·시리즈명 (여기 한 곳만 고치면 전부 반영)
content/queue/*.json   원고 (발행 대기열, 파일명 순서대로 나갑니다)
content/TOPICS.md      토픽 뱅크 (약 130편)
content/STYLE.md       원고 작성 규칙
scripts/template.py    카드 디자인 (HTML/CSS)
scripts/render.py      원고 -> 1080x1350 JPEG
scripts/validate.py    원고 형식 검사
scripts/publish.py     인스타그램 캐러셀 발행
scripts/postqueue.py   큐·발행기록 관리
state.json             발행 기록 (자동 갱신)
out/<slug>/*.jpg       렌더링된 카드
```

## 필요한 GitHub Secrets

`Settings → Secrets and variables → Actions → New repository secret`

| 이름 | 설명 | 필수 |
|---|---|---|
| `IG_USER_ID` | 인스타그램 프로페셔널 계정 ID (숫자) | ✅ |
| `IG_ACCESS_TOKEN` | 페이지 액세스 토큰 | ✅ |
| `META_APP_ID` | 토큰 만료 점검용 | 선택 |
| `META_APP_SECRET` | 토큰 만료 점검용 | 선택 |

> ⚠️ 이미지를 Meta 서버가 직접 받아가야 해서 **저장소는 public이어야 합니다.**
> 시크릿은 public 저장소에서도 노출되지 않습니다.

## 자주 하는 일

**원고 추가** — `content/STYLE.md`를 읽고 `content/queue/NNN-슬러그.json`을 만듭니다.

**미리보기** (로컬)

```bash
pip install playwright requests && playwright install chromium
cd scripts
python validate.py                              # 전체 원고 검사
python render.py --slug 002-positional-encoding # 이미지 생성
open ../out/002-positional-encoding/_preview.html
```

**수동 발행 / 테스트** — Actions 탭 → `매일 인스타 카드뉴스 발행` → `Run workflow`
- `dry_run` 체크 → 실제 업로드 없이 이미지 URL과 캡션만 확인
- `slug` 입력 → 순서를 건너뛰고 특정 편 발행

**하루 쉬기** — Actions 탭에서 워크플로우를 `Disable`. 큐는 그대로 밀립니다.

**디자인 바꾸기** — `scripts/template.py` 상단의 `:root` 색상 변수와 `CSS`만 고치면 됩니다.

## 알아둘 제약

- 캐러셀은 **10장까지**입니다. 11장 이상은 잘립니다.
- 인스타 API 발행은 **24시간에 100건**까지. 하루 1건이면 여유롭습니다.
- JPEG만 지원합니다 (렌더러가 JPEG로 뽑습니다).
- GitHub 크론은 러너 상황에 따라 몇 분~수십 분 늦게 시작될 수 있습니다.
- 페이지 액세스 토큰은 보통 만료되지 않지만, 비밀번호 변경·권한 회수 시 무효화됩니다.
  매주 월요일 `토큰 만료 점검` 워크플로우가 상태를 확인하고, 문제가 생기면
  워크플로우 실패 알림 메일이 갑니다.

## 문제가 생기면

| 증상 | 원인 |
|---|---|
| `발행 대기 중인 원고가 없습니다` | 큐가 비었습니다. 원고를 추가하세요. |
| `The image is not accessible` | 저장소가 private이거나 이미지 커밋이 푸시되지 않았습니다. |
| `(#10) Application does not have permission` | 토큰 권한 부족. `instagram_content_publish` 확인. |
| `Invalid OAuth access token` | 토큰 만료·무효. 재발급 후 시크릿 갱신. |
| 글자가 작게 나옴 | 그 카드 본문이 깁니다. `STYLE.md`의 분량 기준을 지키세요. |
