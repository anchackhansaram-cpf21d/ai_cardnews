#!/usr/bin/env python3
"""액세스 토큰 만료 점검. 만료가 임박하면 0이 아닌 코드로 종료해 알림을 띄운다.

  python token_check.py            # 상태 출력
  python token_check.py --warn 14  # 14일 이내 만료면 실패 처리
"""

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

API = "https://graph.facebook.com/v25.0"
KST = timezone(timedelta(hours=9))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--warn", type=int, default=14, help="경고 기준 (일)")
    a = ap.parse_args()

    token = os.environ.get("IG_ACCESS_TOKEN")
    app_id = os.environ.get("META_APP_ID")
    app_secret = os.environ.get("META_APP_SECRET")
    if not token:
        sys.exit("IG_ACCESS_TOKEN 이 없습니다.")

    # app_id/secret 이 있으면 정확한 만료일을, 없으면 단순 유효성만 확인한다.
    if app_id and app_secret:
        r = requests.get(f"{API}/debug_token",
                         params={"input_token": token,
                                 "access_token": f"{app_id}|{app_secret}"},
                         timeout=60).json()
        d = r.get("data", {})
        if not d.get("is_valid"):
            sys.exit(f"❌ 토큰이 무효합니다: {r}")
        exp = d.get("expires_at", 0)
        if exp == 0:
            print("✅ 토큰 유효 · 만료 없음 (영구 페이지 토큰)")
            return
        when = datetime.fromtimestamp(exp, KST)
        left = (when - datetime.now(KST)).days
        print(f"토큰 만료: {when:%Y-%m-%d %H:%M} (약 {left}일 남음)")
        if left <= a.warn:
            sys.exit(f"⚠️ {left}일 뒤 만료됩니다. 토큰을 새로 발급해 "
                     f"IG_ACCESS_TOKEN 시크릿을 갱신하세요.")
        print("✅ 여유 있음")
        return

    r = requests.get(f"{API}/me", params={"access_token": token}, timeout=60)
    if r.status_code != 200:
        sys.exit(f"❌ 토큰이 동작하지 않습니다: {r.text[:300]}")
    print(f"✅ 토큰 유효 ({r.json().get('name', '이름 없음')}) · "
          f"정확한 만료일 확인은 META_APP_ID/META_APP_SECRET 시크릿이 필요합니다.")


if __name__ == "__main__":
    main()
