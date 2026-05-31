#!/usr/bin/env python3
"""
동행복권 당첨번호 자동 수집
Playwright(실제 Chromium) → Cloudflare 완전 우회
"""

import json, time, argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

KST      = timezone(timedelta(hours=9))
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"

LOTTO_REF_DRW    = 1223
LOTTO_REF_DATE   = datetime(2026, 5, 9, 20, 45, tzinfo=KST)
PENSION_REF_DRW  = 314
PENSION_REF_DATE = datetime(2026, 5, 7, 19,  5, tzinfo=KST)


def calc_latest_lotto():
    diff = (datetime.now(KST) - LOTTO_REF_DATE).total_seconds()
    return LOTTO_REF_DRW + max(0, int(diff / (7*24*3600)))

def calc_latest_pension():
    diff = (datetime.now(KST) - PENSION_REF_DATE).total_seconds()
    return PENSION_REF_DRW + max(0, int(diff / (7*24*3600)))


def make_browser():
    from playwright.sync_api import sync_playwright
    pw      = sync_playwright().start()
    browser = pw.chromium.launch(
        headless = True,
        args     = [
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
        ]
    )
    context = browser.new_context(
        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        viewport        = {"width": 1366, "height": 768},
        locale          = "ko-KR",
        timezone_id     = "Asia/Seoul",
        java_script_enabled = True,
    )
    # 봇 감지 스크립트 숨기기
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins',   {get: () => [1,2,3]});
        window.chrome = {runtime: {}};
    """)
    page = context.new_page()
    # 메인 페이지 먼저 방문 → 쿠키/세션 획득
    try:
        page.goto("https://www.dhlottery.co.kr/", wait_until="domcontentloaded", timeout=20000)
        time.sleep(2)
    except:
        pass
    return pw, browser, context, page


def fetch_lotto_pw(page, drw_no):
    url = f"https://www.dhlottery.co.kr/common.do?method=getLottoNumber&drwNo={drw_no}"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        time.sleep(0.5)
        body = page.inner_text("body").strip()
        if not body or body.startswith("<"):
            return None
        d = json.loads(body)
        if d.get("returnValue") == "success":
            return {
                "nums":  [int(d[f"drwtNo{i}"]) for i in range(1,7)],
                "bonus": int(d["bnusNo"]),
                "date":  d.get("drwNoDate","")
            }
    except Exception as e:
        print(f"      예외: {e}")
    return None


def fetch_pension_pw(page, drw_no):
    url = f"https://www.dhlottery.co.kr/common.do?method=getPension720Number&drwNo={drw_no}"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        time.sleep(0.5)
        body = page.inner_text("body").strip()
        if not body or body.startswith("<"):
            return None
        d = json.loads(body)
        if d.get("returnValue") == "success":
            jo   = int(d.get("pnsWinNm1") or d.get("wnPnsWinNm") or 1)
            nums = [int(d.get(f"pnsWin1Num{i}") or d.get(f"wnPns1Num{i}") or 0) for i in range(1,7)]
            return {"jo": jo, "nums": nums, "date": d.get("drwDate","")}
    except Exception as e:
        print(f"      예외: {e}")
    return None


def update_lotto(mode="new"):
    path  = DATA_DIR / "lotto.json"
    data  = json.loads(path.read_text("utf-8")) if path.exists() else {"draws":{}}
    draws = data.get("draws", {})
    latest= calc_latest_lotto()

    targets = ([n for n in range(1, latest+1) if str(n) not in draws]
               if mode=="all"
               else [n for n in range(max(1,latest-2), latest+1) if str(n) not in draws])

    print(f"[로또] 수집 대상: {len(targets)}회차 (최신 {latest}회)")
    if not targets:
        print("[로또] 모두 수집 완료\n"); return

    pw, browser, ctx, page = make_browser()
    collected = failed = 0
    try:
        for drw_no in targets:
            print(f"  → {drw_no}회 조회...", end=" ", flush=True)
            result = fetch_lotto_pw(page, drw_no)
            if result:
                draws[str(drw_no)] = result
                collected += 1
                print(f"✅ {result['nums']} +{result['bonus']}")
                # 50회마다 중간 저장
                if collected % 50 == 0:
                    _save(path, data, draws, latest)
            else:
                failed += 1
                print("❌ 실패")
            time.sleep(0.3)
    finally:
        browser.close(); pw.stop()

    _save(path, data, draws, latest)
    print(f"[로또] 완료: 수집 {collected} / 실패 {failed} / 누계 {len(draws)}회차\n")


def update_pension(mode="new"):
    path  = DATA_DIR / "pension.json"
    data  = json.loads(path.read_text("utf-8")) if path.exists() else {"draws":{}}
    draws = data.get("draws", {})
    latest= calc_latest_pension()

    targets = ([n for n in range(1, latest+1) if str(n) not in draws]
               if mode=="all"
               else [n for n in range(max(1,latest-2), latest+1) if str(n) not in draws])

    print(f"[연금복권] 수집 대상: {len(targets)}회차 (최신 {latest}회)")
    if not targets:
        print("[연금복권] 모두 수집 완료\n"); return

    pw, browser, ctx, page = make_browser()
    collected = failed = 0
    try:
        for drw_no in targets:
            print(f"  → {drw_no}회 조회...", end=" ", flush=True)
            result = fetch_pension_pw(page, drw_no)
            if result:
                draws[str(drw_no)] = result
                collected += 1
                print(f"✅ {result['jo']}조 {result['nums']}")
                if collected % 50 == 0:
                    _save(path, data, draws, latest)
            else:
                failed += 1
                print("❌ 실패")
            time.sleep(0.3)
    finally:
        browser.close(); pw.stop()

    _save(path, data, draws, latest)
    print(f"[연금복권] 완료: 수집 {collected} / 실패 {failed} / 누계 {len(draws)}회차\n")


def _save(path, data, draws, latest):
    data.update({"draws": draws, "latest_drw": latest,
                 "total": len(draws),
                 "updated": datetime.now(KST).strftime("%Y-%m-%d %H:%M")})
    DATA_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",",":")), "utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["all","new"], default="new")
    args = parser.parse_args()
    print(f"=== 동행복권 수집 시작 (mode={args.mode}) ===")
    update_lotto(args.mode)
    update_pension(args.mode)
    print("=== 수집 완료 ===")
