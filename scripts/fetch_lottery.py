#!/usr/bin/env python3
"""
동행복권 당첨번호 자동 수집 스크립트
cloudscraper로 Cloudflare 봇 차단 우회
"""

import json
import time
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    import cloudscraper
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "cloudscraper"])
    import cloudscraper

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

KST      = timezone(timedelta(hours=9))
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"

# Cloudflare 우회 스크레이퍼 (브라우저 지문 자동 설정)
SCRAPER = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "mobile": False}
)

# 기준 회차
LOTTO_REF_DRW    = 1223
LOTTO_REF_DATE   = datetime(2026, 5, 9, 20, 45, tzinfo=KST)
PENSION_REF_DRW  = 314
PENSION_REF_DATE = datetime(2026, 5, 7, 19,  5, tzinfo=KST)


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
            r = SCRAPER.get(url, timeout=20)
            print(f"    HTTP {r.status_code}", end=" ")

            raw = r.text.strip()
            if not raw or raw.startswith("<"):
                print("→ HTML 응답 (Cloudflare 차단) → HTML 파싱 시도")
                return _fetch_lotto_html(drw_no)

            d = r.json()
            rv = d.get("returnValue", "")
            print(f"→ returnValue={rv}")

            if rv == "success":
                return {
                    "nums":  [int(d[f"drwtNo{i}"]) for i in range(1, 7)],
                    "bonus": int(d["bnusNo"]),
                    "date":  d.get("drwNoDate", "")
                }
            else:
                print("    ⚠️  미발표 회차")
                return None

        except Exception as e:
            print(f"→ 예외: {type(e).__name__}: {str(e)[:80]}")
            if attempt < retries - 1:
                time.sleep(3)

    return None


def _fetch_lotto_html(drw_no: int):
    """HTML 페이지에서 번호 파싱 (JSON API 차단 시 fallback)"""
    if not HAS_BS4:
        return None
    url = (
        f"https://www.dhlottery.co.kr/gameResult.do"
        f"?method=byWin&drwNo={drw_no}"
    )
    try:
        r = SCRAPER.get(url, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")

        # 당첨번호 파싱
        win_nums = soup.select(".num.win span")
        bonus_el = soup.select(".num.bonus span")

        if len(win_nums) >= 6:
            nums  = [int(el.text) for el in win_nums[:6]]
            bonus = int(bonus_el[0].text) if bonus_el else 0
            print(f"    ✅ HTML 파싱 성공: {nums} +{bonus}")
            return {"nums": nums, "bonus": bonus, "date": ""}
        else:
            # 대안 셀렉터
            balls = soup.select(".ball_645")
            if len(balls) >= 7:
                nums  = [int(b.text.strip()) for b in balls[:6]]
                bonus = int(balls[6].text.strip())
                print(f"    ✅ HTML 파싱(대안) 성공: {nums} +{bonus}")
                return {"nums": nums, "bonus": bonus, "date": ""}

    except Exception as e:
        print(f"    ❌ HTML 파싱 실패: {e}")
    return None


def fetch_pension(drw_no: int, retries: int = 3):
    url = (
        f"https://www.dhlottery.co.kr/common.do"
        f"?method=getPension720Number&drwNo={drw_no}"
    )
    for attempt in range(retries):
        try:
            r = SCRAPER.get(url, timeout=20)
            print(f"    HTTP {r.status_code}", end=" ")

            raw = r.text.strip()
            if not raw or raw.startswith("<"):
                print("→ HTML 응답 (차단됨)")
                if attempt < retries - 1:
                    time.sleep(5)
                continue

            d = r.json()
            rv = d.get("returnValue", "")
            print(f"→ returnValue={rv}")

            if rv == "success":
                jo   = int(d.get("pnsWinNm1") or d.get("wnPnsWinNm") or 1)
                nums = [int(d.get(f"pnsWin1Num{i}") or
                            d.get(f"wnPns1Num{i}") or 0)
                        for i in range(1, 7)]
                return {"jo": jo, "nums": nums, "date": d.get("drwDate", "")}
            else:
                print("    ⚠️  미발표 회차")
                return None

        except Exception as e:
            print(f"→ 예외: {type(e).__name__}: {str(e)[:80]}")
            if attempt < retries - 1:
                time.sleep(3)

    return None


def update_lotto(mode: str = "new"):
    path = DATA_DIR / "lotto.json"
    data = json.loads(path.read_text("utf-8")) if path.exists() else {"draws": {}}
    draws  = data.get("draws", {})
    latest = calc_latest_lotto()

    targets = ([n for n in range(1, latest + 1) if str(n) not in draws]
               if mode == "all"
               else [n for n in range(max(1, latest - 2), latest + 1)
                     if str(n) not in draws])

    print(f"[로또] 수집 대상: {len(targets)}회차 (최신 {latest}회)")
    if not targets:
        print("[로또] 모두 수집 완료\n"); return

    collected = failed = 0
    for drw_no in targets:
        print(f"  → {drw_no}회 조회 중...", end=" ")
        result = fetch_lotto(drw_no)
        if result:
            draws[str(drw_no)] = result
            collected += 1
            print(f"  ✅ {drw_no}회 → {result['nums']} +{result['bonus']}")
        else:
            failed += 1
            print(f"  ❌ {drw_no}회 실패")
        time.sleep(1)

    data.update({"draws": draws, "latest_drw": latest,
                 "total": len(draws),
                 "updated": datetime.now(KST).strftime("%Y-%m-%d %H:%M")})
    DATA_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), "utf-8")
    print(f"[로또] 완료: 수집 {collected} / 실패 {failed} / 누계 {len(draws)}회차\n")


def update_pension(mode: str = "new"):
    path = DATA_DIR / "pension.json"
    data = json.loads(path.read_text("utf-8")) if path.exists() else {"draws": {}}
    draws  = data.get("draws", {})
    latest = calc_latest_pension()

    targets = ([n for n in range(1, latest + 1) if str(n) not in draws]
               if mode == "all"
               else [n for n in range(max(1, latest - 2), latest + 1)
                     if str(n) not in draws])

    print(f"[연금복권] 수집 대상: {len(targets)}회차 (최신 {latest}회)")
    if not targets:
        print("[연금복권] 모두 수집 완료\n"); return

    collected = failed = 0
    for drw_no in targets:
        print(f"  → {drw_no}회 조회 중...", end=" ")
        result = fetch_pension(drw_no)
        if result:
            draws[str(drw_no)] = result
            collected += 1
            print(f"  ✅ {drw_no}회 → {result['jo']}조 {result['nums']}")
        else:
            failed += 1
            print(f"  ❌ {drw_no}회 실패")
        time.sleep(1)

    data.update({"draws": draws, "latest_drw": latest,
                 "total": len(draws),
                 "updated": datetime.now(KST).strftime("%Y-%m-%d %H:%M")})
    DATA_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), "utf-8")
    print(f"[연금복권] 완료: 수집 {collected} / 실패 {failed} / 누계 {len(draws)}회차\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["all", "new"], default="new")
    args = parser.parse_args()

    print(f"=== 동행복권 수집 시작 (mode={args.mode}) ===")
    update_lotto(args.mode)
    update_pension(args.mode)
    print("=== 수집 완료 ===")
