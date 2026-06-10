#!/usr/bin/env python3
"""
동행복권 당첨번호 업데이트 스크립트
초기 데이터: 엑셀 파일로 생성 완료
이후 신규 회차: Selenium HTML 스크래핑으로 자동 추가
설치: pip install selenium webdriver-manager beautifulsoup4
실행: python scripts/fetch_lottery.py --mode new
"""

import json, time, argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

KST      = timezone(timedelta(hours=9))
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

LOTTO_REF_DRW    = 1227
LOTTO_REF_DATE   = datetime(2026, 6, 6, 20, 45, tzinfo=KST)
PENSION_REF_DRW  = 318
PENSION_REF_DATE = datetime(2026, 6, 4, 19, 5, tzinfo=KST)

def calc_latest_lotto():
    diff = (datetime.now(KST) - LOTTO_REF_DATE).total_seconds()
    return LOTTO_REF_DRW + max(0, int(diff / (7*24*3600)))

def calc_latest_pension():
    diff = (datetime.now(KST) - PENSION_REF_DATE).total_seconds()
    return PENSION_REF_DRW + max(0, int(diff / (7*24*3600)))


def make_driver():
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    from bs4 import BeautifulSoup

    options = webdriver.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--window-size=1280,800")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
    })
    driver.get("https://www.dhlottery.co.kr/")
    time.sleep(3)
    return driver


def fetch_lotto_html(driver, drw_no):
    from bs4 import BeautifulSoup
    url = f"https://www.dhlottery.co.kr/gameResult.do?method=byWin&drwNo={drw_no}"
    try:
        driver.get(url)
        time.sleep(1.5)
        soup = BeautifulSoup(driver.page_source, "html.parser")
        win = soup.select(".num.win span")
        bon = soup.select(".num.bonus span")
        if len(win) >= 6:
            nums  = sorted([int(e.text.strip()) for e in win[:6]])
            bonus = int(bon[0].text.strip()) if bon else 0
            return {"nums": nums, "bonus": bonus, "date": ""}
        balls = soup.select(".ball_645")
        if len(balls) >= 7:
            return {"nums": sorted([int(b.text.strip()) for b in balls[:6]]),
                    "bonus": int(balls[6].text.strip()), "date": ""}
    except: pass
    return None


def fetch_pension_html(driver, drw_no):
    from bs4 import BeautifulSoup
    url = f"https://www.dhlottery.co.kr/gameResult.do?method=byWin720Plus&drwNo={drw_no}"
    try:
        driver.get(url)
        time.sleep(1.5)
        soup = BeautifulSoup(driver.page_source, "html.parser")
        rows = soup.select(".tbl_data tbody tr")
        for row in rows:
            rank = row.select_one("td:first-child")
            if rank and "1등" in rank.text:
                tds = row.select("td")
                jo_el = row.select_one(".jo")
                nums_el = row.select(".num_ball") or row.select(".num")
                if jo_el and len(nums_el) >= 6:
                    jo   = int(jo_el.text.strip().replace("조",""))
                    nums = [int(n.text.strip()) for n in nums_el[:6]]
                    return {"jo": jo, "nums": nums, "date": ""}
    except: pass
    return None


def _save(path, data, draws, latest):
    data.update({"draws": draws, "latest_drw": latest,
                 "total": len(draws),
                 "updated": datetime.now(KST).strftime("%Y-%m-%d %H:%M")})
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",",":")), "utf-8")


def update_lotto(driver, mode):
    path   = DATA_DIR / "lotto.json"
    data   = json.loads(path.read_text("utf-8")) if path.exists() else {"draws":{}}
    draws  = data.get("draws", {})
    latest = calc_latest_lotto()
    targets= ([n for n in range(1,latest+1) if str(n) not in draws]
               if mode=="all"
               else [n for n in range(max(1,latest-1),latest+1) if str(n) not in draws])

    print(f"[로또] 신규 대상: {len(targets)}회차 (보유 {len(draws)}회 / 최신 {latest}회)")
    if not targets: print("[로또] 최신 상태\n"); return

    collected = failed = 0
    for drw_no in targets:
        print(f"  {drw_no}회 ", end="", flush=True)
        result = fetch_lotto_html(driver, drw_no)
        if result:
            draws[str(drw_no)] = result; collected += 1
            print(f"✅ {result['nums']} +{result['bonus']}")
        else:
            failed += 1; print("❌")
    _save(path, data, draws, latest)
    print(f"[로또] 완료 ✅{collected} ❌{failed}\n")


def update_pension(driver, mode):
    path   = DATA_DIR / "pension.json"
    data   = json.loads(path.read_text("utf-8")) if path.exists() else {"draws":{}}
    draws  = data.get("draws", {})
    latest = calc_latest_pension()
    targets= ([n for n in range(1,latest+1) if str(n) not in draws]
               if mode=="all"
               else [n for n in range(max(1,latest-1),latest+1) if str(n) not in draws])

    print(f"[연금복권] 신규 대상: {len(targets)}회차 (보유 {len(draws)}회 / 최신 {latest}회)")
    if not targets: print("[연금복권] 최신 상태\n"); return

    collected = failed = 0
    for drw_no in targets:
        print(f"  {drw_no}회 ", end="", flush=True)
        result = fetch_pension_html(driver, drw_no)
        if result:
            draws[str(drw_no)] = result; collected += 1
            print(f"✅ {result['jo']}조 {result['nums']}")
        else:
            failed += 1; print("❌")
    _save(path, data, draws, latest)
    print(f"[연금복권] 완료 ✅{collected} ❌{failed}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["all","new"], default="new")
    args = parser.parse_args()

    print("=== 신규 회차 업데이트 ===\n")
    driver = make_driver()
    try:
        update_lotto(driver, args.mode)
        update_pension(driver, args.mode)
    finally:
        driver.quit()
    print(f"\n저장 위치: {DATA_DIR}")
