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

KST = timezone(timedelta(hours=9))
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"

# ── 기준 회차 (기준날짜 이후 매주 +1) ──
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
    url = f"https://www.dhlottery.co.kr/common.do?method=getLottoNumber&drwNo={drw_no}"
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=10)
            d = r.json()
            if d.get("returnValue") == "success":
                return {
                    "nums": [int(d[f"drwtNo{i}"]) for i in range(1, 7)],
                    "bonus": int(d["bnusNo"]),
                    "date": d.get("drwNoDate", "")
                }
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(1)
    return None


def fetch_pension(drw_no: int, retries: int = 3):
    url = f"https://www.dhlottery.co.kr/common.do?method=getPension720Number&drwNo={drw_no}"
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=10)
            d = r.json()
            if d.get("returnValue") == "success":
                jo = int(d.get("pnsWinNm1") or d.get("wnPnsWinNm") or 1)
                nums = []
                for i in range(1, 7):
                    v = d.get(f"pnsWin1Num{i}") or d.get(f"wnPns1Num{i}") or 0
                    nums.append(int(v))
                return {
                    "jo": jo,
                    "nums": nums,
                    "date": d.get("drwDate", "")
                }
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(1)
    return None


def update_lotto(mode: str = "new"):
    path = DATA_DIR / "lotto.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = {"draws": {}, "latest_drw": 0, "total": 0}

    draws = data.get("draws", {})
    latest = calc_latest_lotto()

    # 수집할 회차 목록
    if mode == "all":
        targets = [n for n in range(1, latest + 1) if str(n) not in draws]
    else:
        targets = [n for n in range(latest - 2, latest + 1) if str(n) not in draws]

    print(f"[로또] 수집 대상: {len(targets)}회차 (최신 {latest}회)")

    collected, failed = 0, 0
    for drw_no in targets:
        result = fetch_lotto(drw_no)
        if result:
            draws[str(drw_no)] = result
            collected += 1
            print(f"  ✅ {drw_no}회 → {result['nums']} +{result['bonus']}")
        else:
            failed += 1
            print(f"  ❌ {drw_no}회 실패")
        time.sleep(0.3)

    data["draws"]      = draws
    data["latest_drw"] = latest
    data["total"]      = len(draws)
    data["updated"]    = datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    DATA_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8")
    print(f"[로또] 완료: 수집 {collected} / 실패 {failed} / 누계 {len(draws)}회차\n")


def update_pension(mode: str = "new"):
    path = DATA_DIR / "pension.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = {"draws": {}, "latest_drw": 0, "total": 0}

    draws = data.get("draws", {})
    latest = calc_latest_pension()

    if mode == "all":
        targets = [n for n in range(1, latest + 1) if str(n) not in draws]
    else:
        targets = [n for n in range(latest - 2, latest + 1) if str(n) not in draws]

    print(f"[연금복권] 수집 대상: {len(targets)}회차 (최신 {latest}회)")

    collected, failed = 0, 0
    for drw_no in targets:
        result = fetch_pension(drw_no)
        if result:
            draws[str(drw_no)] = result
            collected += 1
            print(f"  ✅ {drw_no}회 → {result['jo']}조 {result['nums']}")
        else:
            failed += 1
            print(f"  ❌ {drw_no}회 실패")
        time.sleep(0.3)

    data["draws"]      = draws
    data["latest_drw"] = latest
    data["total"]      = len(draws)
    data["updated"]    = datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    DATA_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8")
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
