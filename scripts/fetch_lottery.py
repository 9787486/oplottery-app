#!/usr/bin/env python3
"""
동행복권 당첨번호 자동 수집 스크립트
- 로또 6/45: 1회 ~ 현재 회차
- 연금복권 720+: 1회 ~ 현재 회차
"""

import json
import time
import argparse
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

KST      = timezone(timedelta(hours=9))
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"

# 브라우저처럼 보이게 하는 헤더 (봇 차단 우회)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer":  "https://www.dhlottery.co.kr/gameInfo.do?method=lotteryInfo",
    "Accept":   "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}

# ── 기준 회차 ──
LOTTO_REF_DRW  = 1223
LOTTO_REF_DATE = datetime(2026, 5, 9, 20, 45, tzinfo=KST)

PENSION_REF_DRW  = 314
PENSION_REF_DATE = datetime(2026, 5, 7, 19, 5, tzinfo=KST)


def calc_latest_lotto():
    diff = (datetime.now(KST) - LOTTO_REF_DATE).total_seconds()
    return LOTTO_REF_DRW + max(0, int(diff / (7 * 24 * 3600)))


def calc_latest_pension():
    diff = (datetime.now(KST) - PENSION_REF_DATE).total_seconds()
    return PENSION_REF_DRW + max(0, int(diff / (7 * 24 * 3600)))


def fetch_lotto(drw_no: int, retries: int = 3):
    url = (
        f"https://www.dhlottery.co.kr/common.do"
        f"?method=getLottoNumber&drwNo={drw_no}"
    )
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            print(f"    HTTP {r.status_code}", end=" ")
            if r.status_code != 200:
                print(f"→ 응답 오류")
                time.sleep(2)
                continue
            raw = r.text.strip()
            if not raw or raw.startswith("<"):
                print(f"→ HTML 응답 (차단됨)")
                time.sleep(3)
                continue
            d = r.json()
            rv = d.get("returnValue", "")
            print(f"→ returnValue={rv}")
            if rv == "success":
                return {
                    "nums": [int(d[f"drwtNo{i}"]) for i in range(1, 7)],
                    "bonus": int(d["bnusNo"]),
                    "date": d.get("drwNoDate", "")
                }
            else:
                print(f"    ⚠️  미발표 회차이거나 데이터 없음")
                return None  # 재시도 불필요
        except Exception as e:
            print(f"→ 예외: {e}")
            if attempt < retries - 1:
                time.sleep(2)
    return None


def fetch_pension(drw_no: int, retries: int = 3):
    url = (
        f"https://www.dhlottery.co.kr/common.do"
        f"?method=getPension720Number&drwNo={drw_no}"
    )
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            print(f"    HTTP {r.status_code}", end=" ")
            if r.status_code != 200:
                print(f"→ 응답 오류")
                time.sleep(2)
                continue
            raw = r.text.strip()
            if not raw or raw.startswith("<"):
                print(f"→ HTML 응답 (차단됨)")
                time.sleep(3)
                continue
            d = r.json()
            rv = d.get("returnValue", "")
            print(f"→ returnValue={rv}")
            if rv == "success":
                jo   = int(d.get("pnsWinNm1") or d.get("wnPnsWinNm") or 1)
                nums = []
                for i in range(1, 7):
                    v = d.get(f"pnsWin1Num{i}") or d.get(f"wnPns1Num{i}") or 0
                    nums.append(int(v))
                return {
                    "jo":   jo,
                    "nums": nums,
                    "date": d.get("drwDate", "")
                }
            else:
                print(f"    ⚠️  미발표 회차이거나 데이터 없음")
                return None
        except Exception as e:
            print(f"→ 예외: {e}")
            if attempt < retries - 1:
                time.sleep(2)
    return None


def update_lotto(mode: str = "new"):
    path = DATA_DIR / "lotto.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = {"draws": {}, "latest_drw": 0, "total": 0}

    draws  = data.get("draws", {})
    latest = calc_latest_lotto()

    if mode == "all":
        targets = [n for n in range(1, latest + 1) if str(n) not in draws]
    else:
        # new: 최신 3회차 중 미수집분만
        targets = [n for n in range(max(1, latest - 2), latest + 1)
                   if str(n) not in draws]

    print(f"[로또] 수집 대상: {len(targets)}회차 (최신 {latest}회)")
    if not targets:
        print("[로또] 모두 수집 완료 — 건너뜀\n")
        return

    collected, failed = 0, 0
    for drw_no in targets:
        print(f"  → {drw_no}회 조회 중...", end=" ")
        result = fetch_lotto(drw_no)
        if result:
            draws[str(drw_no)] = result
            collected += 1
            print(f"  ✅ {drw_no}회 → {result['nums']} +{result['bonus']} ({result['date']})")
        else:
            failed += 1
            print(f"  ❌ {drw_no}회 실패")
        time.sleep(0.5)

    data["draws"]      = draws
    data["latest_drw"] = latest
    data["total"]      = len(draws)
    data["updated"]    = datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    DATA_DIR.mkdir(exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8"
    )
    print(f"[로또] 완료: 수집 {collected} / 실패 {failed} / 누계 {len(draws)}회차\n")


def update_pension(mode: str = "new"):
    path = DATA_DIR / "pension.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = {"draws": {}, "latest_drw": 0, "total": 0}

    draws  = data.get("draws", {})
    latest = calc_latest_pension()

    if mode == "all":
        targets = [n for n in range(1, latest + 1) if str(n) not in draws]
    else:
        targets = [n for n in range(max(1, latest - 2), latest + 1)
                   if str(n) not in draws]

    print(f"[연금복권] 수집 대상: {len(targets)}회차 (최신 {latest}회)")
    if not targets:
        print("[연금복권] 모두 수집 완료 — 건너뜀\n")
        return

    collected, failed = 0, 0
    for drw_no in targets:
        print(f"  → {drw_no}회 조회 중...", end=" ")
        result = fetch_pension(drw_no)
        if result:
            draws[str(drw_no)] = result
            collected += 1
            print(f"  ✅ {drw_no}회 → {result['jo']}조 {result['nums']} ({result['date']})")
        else:
            failed += 1
            print(f"  ❌ {drw_no}회 실패")
        time.sleep(0.5)

    data["draws"]      = draws
    data["latest_drw"] = latest
    data["total"]      = len(draws)
    data["updated"]    = datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    DATA_DIR.mkdir(exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8"
    )
    print(f"[연금복권] 완료: 수집 {collected} / 실패 {failed} / 누계 {len(draws)}회차\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["all", "new"], default="new",
                        help="all=전체 수집, new=최신 회차만")
    args = parser.parse_args()

    print(f"=== 동행복권 수집 시작 (mode={args.mode}) ===")
    update_lotto(args.mode)
    update_pension(args.mode)
    print("=== 수집 완료 ===")
