#!/usr/bin/env python3
"""
캬라푸 믹스패널 일일 리포트 → 슬랙 자동 전송 스크립트
Usage: python3 mixpanel_daily_report.py
"""

import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from urllib.error import URLError, HTTPError
import base64

# ── 설정 ──────────────────────────────────────────────────────────────────────
MIXPANEL_API_SECRET = os.getenv("MIXPANEL_API_SECRET", "d002689641d1ab6b4e2a8de2d4b7c7d6")
SLACK_BOT_TOKEN     = os.getenv("SLACK_BOT_TOKEN", "")       # 반드시 환경 변수로 설정
SLACK_CHANNEL_ID    = os.getenv("SLACK_CHANNEL_ID", "C088ZLH7NNR")
DASHBOARD_URL       = "https://mixpanel.com/s/r6YfI"

KST = timezone(timedelta(hours=9))


def get_yesterday_kst() -> str:
    return (datetime.now(KST) - timedelta(days=1)).strftime("%Y-%m-%d")


def mixpanel_request(endpoint: str, params: dict) -> list[dict]:
    url = f"https://data.mixpanel.com/api/2.0/{endpoint}?" + urlencode(params)
    creds = base64.b64encode(f"{MIXPANEL_API_SECRET}:".encode()).decode()
    req = Request(url, headers={"Authorization": f"Basic {creds}"})
    with urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8")
    # Export API returns newline-delimited JSON
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def fetch_events(date: str) -> list[dict]:
    return mixpanel_request("export", {"from_date": date, "to_date": date})


def analyze(events: list[dict]) -> dict:
    distinct_users: set = set()
    event_counts: Counter = Counter()

    for ev in events:
        props = ev.get("properties", {})
        uid = props.get("distinct_id")
        if uid:
            distinct_users.add(uid)
        name = ev.get("event", "unknown")
        event_counts[name] += 1

    return {
        "dau": len(distinct_users),
        "total_events": len(events),
        "top_events": event_counts.most_common(10),
    }


def build_slack_message(date: str, stats: dict) -> str:
    top_events_lines = "\n".join(
        f"  • {name}: {count:,}회"
        for name, count in stats["top_events"]
    )
    return f"""📊 **캬라푸 믹스패널 대시보드** - 일일 리포트
📅 기준일: {date} (한국 시간 기준)

🔗 대시보드 링크: {DASHBOARD_URL}

📈 **주요 지표:**
👥 DAU: {stats['dau']:,}명
🔢 총 이벤트: {stats['total_events']:,}건

📱 **상위 이벤트:**
{top_events_lines}

#데이터분석 #캬라푸 #일일지표"""


def build_fallback_message(date: str, error: str) -> str:
    return f"""📊 **캬라푸 믹스패널 대시보드** - 일일 리포트
📅 기준일: {date} (한국 시간 기준)

🔗 대시보드 링크: {DASHBOARD_URL}

⚠️ **API 데이터 수집 실패:** {error}
대시보드 링크에서 직접 확인해 주세요.

#데이터분석 #캬라푸 #일일지표"""


def send_slack(message: str) -> None:
    if not SLACK_BOT_TOKEN:
        raise ValueError("SLACK_BOT_TOKEN 환경 변수가 설정되지 않았습니다.")
    payload = json.dumps({
        "channel": SLACK_CHANNEL_ID,
        "text": message,
        "mrkdwn": True,
    }).encode()
    req = Request(
        "https://slack.com/api/chat.postMessage",
        data=payload,
        headers={
            "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
            "Content-Type": "application/json",
        },
    )
    with urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())
    if not result.get("ok"):
        raise RuntimeError(f"Slack 오류: {result.get('error')}")
    print(f"✅ 슬랙 전송 완료: {result.get('ts')}")


def main() -> None:
    date = get_yesterday_kst()
    print(f"📅 수집 날짜: {date} (KST)")

    try:
        print("📡 믹스패널 데이터 수집 중...")
        events = fetch_events(date)
        print(f"   → 이벤트 {len(events):,}건 수집됨")
        stats = analyze(events)
        message = build_slack_message(date, stats)
    except (URLError, HTTPError, json.JSONDecodeError, ValueError) as e:
        print(f"⚠️  데이터 수집 실패: {e}", file=sys.stderr)
        message = build_fallback_message(date, str(e))

    send_slack(message)


if __name__ == "__main__":
    main()
