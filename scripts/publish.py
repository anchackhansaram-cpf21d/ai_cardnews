#!/usr/bin/env python3
"""렌더링된 카드뉴스를 인스타그램 캐러셀로 발행한다.

이미지는 GitHub raw URL(커밋 SHA 고정)로 노출하고, Meta 서버가 그걸 받아간다.
필요한 환경변수:
  IG_USER_ID       인스타그램 프로페셔널 계정의 ID (숫자)
  IG_ACCESS_TOKEN  장기 액세스 토큰
  GITHUB_REPOSITORY  owner/repo   (Actions가 자동 주입)
  GITHUB_SHA         이미지가 포함된 커밋 SHA (Actions가 자동 주입)
"""

import argparse
import os
import pathlib
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

import postqueue as q

ROOT = pathlib.Path(__file__).resolve().parent.parent
API = "https://graph.facebook.com/v25.0"
MAX_CARDS = 10          # 인스타 캐러셀 상한
KST = timezone(timedelta(hours=9))


def need(name):
    v = os.environ.get(name)
    if not v:
        sys.exit(f"환경변수 {name} 가 없습니다.")
    return v


def raw_url(repo, sha, slug, n):
    return f"https://raw.githubusercontent.com/{repo}/{sha}/out/{slug}/{n:02d}.jpg"


def build_caption(data):
    cap = data.get("caption", "").strip()
    tags = " ".join(data.get("hashtags", []))
    return f"{cap}\n\n.\n.\n.\n{tags}".strip()


def post(url, params, tries=4):
    """Graph API 호출 + 지수 백오프 재시도."""
    delay = 5
    last = None
    for attempt in range(1, tries + 1):
        r = requests.post(url, data=params, timeout=90)
        if r.status_code == 200:
            return r.json()
        last = f"HTTP {r.status_code}: {r.text[:500]}"
        # 4xx 중 재시도가 무의미한 것은 즉시 중단
        if r.status_code == 400 and "rate limit" not in r.text.lower():
            break
        print(f"  재시도 {attempt}/{tries} ({last})")
        time.sleep(delay)
        delay *= 2
    sys.exit(f"Graph API 호출 실패 -> {url}\n{last}")


def check_images_public(urls):
    """Meta가 가져갈 수 있는 주소인지 먼저 확인한다.

    저장소가 private이거나 이미지 푸시가 실패하면 raw 주소가 404가 되고,
    Meta는 "미디어를 가져올 수 없다"(code 9004)로만 알려줘 원인 파악이 어렵다.
    """
    url = urls[0]
    # 푸시 직후에는 raw CDN에 파일이 아직 안 퍼져 404가 날 수 있다.
    # Meta가 그 타이밍에 받아가면 code 9004로 실패하므로, 먼저 여기서 기다린다.
    r = None
    for attempt in range(1, 13):          # 최대 약 60초
        try:
            r = requests.get(url, timeout=45, stream=True)
        except requests.RequestException as e:
            sys.exit(f"이미지 주소에 접속하지 못했습니다: {type(e).__name__}\n  {url}")
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/"):
            break
        if attempt == 1:
            print(f"이미지가 아직 공개되지 않았습니다 (HTTP {r.status_code}). "
                  f"CDN 반영을 기다립니다...")
        time.sleep(5)

    ctype = r.headers.get("content-type", "")
    if r.status_code == 404:
        sys.exit(
            "이미지 주소가 404입니다. Meta가 카드를 가져갈 수 없습니다.\n"
            f"  {url}\n"
            "  원인은 보통 둘 중 하나입니다:\n"
            "  1) 저장소가 Private — Settings → General → 맨 아래 Change visibility → Public\n"
            "  2) 이미지 커밋이 푸시되지 않음 — 위쪽 '이미지 커밋 & 푸시' 단계 로그를 확인하세요\n"
            "  브라우저 시크릿 창에서 위 주소를 열어보면 바로 확인됩니다."
        )
    if r.status_code != 200:
        sys.exit(f"이미지 주소가 HTTP {r.status_code} 입니다.\n  {url}")
    if not ctype.startswith("image/"):
        sys.exit(
            f"이미지 주소가 이미지가 아닌 응답을 돌려줍니다 (content-type: {ctype}).\n"
            f"  {url}\n"
            "  저장소가 Private이면 로그인 페이지가 반환되어 이 증상이 납니다."
        )
    # 첫 장만 되고 나머지가 아직인 경우가 있어 마지막 장도 확인한다
    if len(urls) > 1:
        for attempt in range(1, 13):
            last = requests.get(urls[-1], timeout=45, stream=True)
            if last.status_code == 200:
                break
            time.sleep(5)
        else:
            sys.exit(f"마지막 이미지가 아직 공개되지 않았습니다.\n  {urls[-1]}")

    size = int(r.headers.get("content-length") or 0)
    print(f"이미지 접근 확인: {len(urls)}장 · 첫 장 {size // 1024}KB · {ctype}")


def preflight(ig_user, token):
    """발행을 시작하기 전에 계정 ID와 토큰이 맞는지 먼저 확인한다."""
    try:
        r = requests.get(f"{API}/{ig_user}",
                         params={"fields": "username", "access_token": token},
                         timeout=60)
    except requests.RequestException as e:
        sys.exit(f"Meta 서버에 접속하지 못했습니다: {type(e).__name__}. "
                 f"잠시 뒤 다시 실행해 주세요.")
    if r.status_code == 200:
        print(f"계정 확인: @{r.json().get('username', '?')}")
        return

    err = {}
    try:
        err = r.json().get("error", {})
    except Exception:
        pass
    code, sub = err.get("code"), err.get("error_subcode")

    if code == 100:
        sys.exit(
            "IG_USER_ID 를 찾을 수 없습니다.\n"
            "  인스타그램 계정 ID 대신 페이지 ID를 넣으셨을 가능성이 큽니다.\n"
            "  아래 주소로 진짜 ID를 확인하세요 (결과의 instagram_business_account.id):\n"
            f"  https://graph.facebook.com/v25.0/[페이지ID]"
            f"?fields=instagram_business_account&access_token=[페이지토큰]\n"
            f"  (현재 설정된 값의 길이: {len(str(ig_user))}자 · 정상은 17자 안팎)"
        )
    if code == 190:
        sys.exit("IG_ACCESS_TOKEN 이 만료되었거나 무효합니다. 토큰을 재발급하세요.")

    # 아래는 사전 점검(읽기)에서만 나는 오류일 수 있다.
    # 읽기 권한(instagram_basic)이 없어도 발행 권한은 살아있을 수 있으므로
    # 여기서 멈추지 않고 경고만 남기고 진행한다. 진짜 문제면 발행 단계에서 걸린다.
    if code in (10, 200, 3):
        print("::warning::계정 정보를 읽지 못했습니다 (권한 부족일 수 있음). "
              "instagram_basic 권한을 확인해 보세요. 발행은 그대로 시도합니다.")
        return
    print(f"::warning::계정 사전 확인을 건너뜁니다 "
          f"(code={code}, subcode={sub}): {r.text[:200]}")


def wait_ready(container_id, token, timeout=300):
    """컨테이너가 FINISHED 될 때까지 대기."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.get(f"{API}/{container_id}",
                         params={"fields": "status_code,status",
                                 "access_token": token}, timeout=60)
        j = r.json()
        code = j.get("status_code")
        if code == "FINISHED":
            return True
        if code == "ERROR":
            sys.exit(f"컨테이너 처리 실패: {j}")
        time.sleep(5)
    sys.exit(f"컨테이너 {container_id} 처리 대기 시간 초과")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--dry-run", action="store_true",
                    help="Graph API 호출 없이 URL과 캡션만 출력")
    a = ap.parse_args()

    repo = need("GITHUB_REPOSITORY")
    sha = need("GITHUB_SHA")
    data = q.load(a.slug)

    img_dir = ROOT / "out" / a.slug
    imgs = sorted(img_dir.glob("*.jpg"))[:MAX_CARDS]
    if not imgs:
        sys.exit(f"out/{a.slug}/ 에 이미지가 없습니다. 먼저 render.py를 실행하세요.")

    urls = [raw_url(repo, sha, a.slug, i) for i in range(1, len(imgs) + 1)]
    caption = build_caption(data)

    if a.dry_run:
        # 수동 업로드용으로 캡션을 파일로도 남긴다 (이미지와 함께 내려받게)
        (img_dir / "caption.txt").write_text(caption, encoding="utf-8")
        print("--- 이미지 URL ---")
        print("\n".join(urls))
        print("\n--- 캡션 (out/%s/caption.txt 에도 저장) ---" % a.slug)
        print(caption)
        return

    ig_user = need("IG_USER_ID").strip()
    token = need("IG_ACCESS_TOKEN").strip()

    # 0) 계정·토큰, 그리고 이미지 주소 사전 점검
    preflight(ig_user, token)
    check_images_public(urls)

    # 1) 이미지별 컨테이너 생성
    children = []
    for i, u in enumerate(urls, 1):
        print(f"[{i}/{len(urls)}] 컨테이너 생성")
        j = post(f"{API}/{ig_user}/media",
                 {"image_url": u, "is_carousel_item": "true",
                  "access_token": token})
        children.append(j["id"])

    # 2) 캐러셀 컨테이너 생성
    print("캐러셀 컨테이너 생성")
    carousel = post(f"{API}/{ig_user}/media",
                    {"media_type": "CAROUSEL",
                     "children": ",".join(children),
                     "caption": caption,
                     "access_token": token})["id"]

    # 3) 처리 완료 대기 후 발행
    wait_ready(carousel, token)
    print("발행 중")
    media_id = post(f"{API}/{ig_user}/media_publish",
                    {"creation_id": carousel, "access_token": token})["id"]

    permalink = None
    try:
        permalink = requests.get(f"{API}/{media_id}",
                                 params={"fields": "permalink",
                                         "access_token": token},
                                 timeout=60).json().get("permalink")
    except Exception:
        pass

    now = datetime.now(KST).isoformat(timespec="seconds")
    q.mark_posted(a.slug, permalink=permalink, media_id=media_id, when=now)
    print(f"✅ 발행 완료: {permalink or media_id}")
    print(f"남은 원고: {q.remaining()}편")


if __name__ == "__main__":
    main()
