#!/usr/bin/env python3
"""Instagram 미디어 인사이트 수집 → analytics/insights.json

Graph API로 발행 게시물의 좋아요/저장/공유/도달을 모은다.
GITHUB Actions에서 실행 (IG_ACCESS_TOKEN, IG_USER_ID 환경변수 필요).
"""

import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

VER = "v25.0"
TOKEN = os.environ.get("IG_ACCESS_TOKEN", "")
USER = os.environ.get("IG_USER_ID", "")

# 미디어 인사이트 지표 (버전별로 지원이 다르므로 순차 시도)
METRIC_SETS = [
    "reach,saved,shares,total_interactions",
    "reach,saved,shares",
    "reach,impressions",
]


def api(path, **params):
    params["access_token"] = TOKEN
    url = f"https://graph.facebook.com/{VER}/{path}?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:400]
        raise RuntimeError(f"HTTP {e.code}: {body}") from None


def fetch_insights(media_id):
    last = "unknown"
    for metrics in METRIC_SETS:
        try:
            r = api(f"{media_id}/insights", metric=metrics)
            out = {}
            for d in r.get("data", []):
                name = d.get("name")
                vals = d.get("values")
                if vals:
                    out[name] = vals[0].get("value")
                elif "value" in d:
                    out[name] = d["value"]
            if out:
                return out, metrics
        except Exception as e:
            last = str(e)[:120]
            continue
    return {"_error": last}, ""


def main():
    if not TOKEN or not USER:
        sys.exit("IG_ACCESS_TOKEN / IG_USER_ID 환경변수가 필요합니다")

    media = api(f"{USER}/media",
                fields="id,caption,timestamp,permalink,media_type,like_count,comments_count",
                limit=50)
    items = []
    for m in media.get("data", []):
        mid = m["id"]
        ins, metric_used = fetch_insights(mid)
        cap = (m.get("caption") or "").split("\n")[0][:80]
        items.append({
            "id": mid,
            "timestamp": m.get("timestamp"),
            "permalink": m.get("permalink"),
            "type": m.get("media_type"),
            "caption_head": cap,
            "like_count": m.get("like_count"),
            "comments_count": m.get("comments_count"),
            "insights": ins,
            "metrics_used": metric_used,
        })

    dest = pathlib.Path("analytics/insights.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "count": len(items),
        "media": items,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"수집 완료: {len(items)}개 게시물")


if __name__ == "__main__":
    main()