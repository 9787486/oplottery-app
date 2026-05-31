#!/usr/bin/env python3
"""
동행복권 당첨번호 자동 수집
공공데이터포털 공식 API 사용 → Cloudflare 차단 없음
API 키: GitHub Secrets → LOTTO_API_KEY
"""

import json, time, os, argparse, requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import unquote

KST      = timezone(timedelta(hours=9))
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"

# GitHub Secrets 에서 API 키 읽기
SERVICE_KEY = os.environ.get("LOTTO_API_KEY", "")

# 기준 회차
LOTTO_REF_DRW    = 1223
LOTTO_REF_DATE   = datetime(2026, 5, 9, 20, 45, tzinfo=KST)
PENSION_REF_DRW  = 317
PENSION_REF_DATE = datetime(2026, 5, 28, 19, 5, tzinfo=KST)


def calc_latest_lotto():
    diff = (datetime.now(KST) - LOTTO_REF_DATE).total_seconds()
    return LOTTO_REF_DRW + max(0, int(diff / (7*24*3600)))

def calc_latest_pension():
    diff = (datetime.now(KST) - PENSION_REF_DATE).total_seconds()
    return PENSION_REF_DRW + max(0, int(diff / (7*24*3600)))


def fetch_lotto(drw_no: int) -> dict | None:
    """공공데이터포털 API → 로또 당첨번호"""
    if not SERVICE_KEY:
        print("    ⚠️  LOTTO_API_KEY 없음 → GitHub Secrets 등록 필요")
        return None

    url = "https://apis.data.go.kr/B551015/LrsrsInfoService/getLottoNumber"
    params = {
        "serviceKey": SERVICE_KEY,
        "drwNo":      drw_no,
        "_type":      "json",
    }
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=15)
            print(f"    HTTP {r.status_code}", end=" ")
            d = r.json()
            # 공공데이터 API 응답 구조: response.body.items.item
            items = (d.get("response", {})
                      .get("body", {})
                      .get("items", {})
                      .get("item", {}))
            if isinstance(items, list):
                items = items[0] if items else {}
            if items.get("returnValue") == "success" or items.get("drwtNo1"):
                print(f"→ ✅")
                return {
                    "nums":  [int(items.get(f"drwtNo{i}", 0)) for i in range(1,7)],
                    "bonus": int(items.get("bnusNo", 0)),
                    "date":  items.get("drwNoDate", "")
                }
            else:
                # 일부 구버전 API는 직접 JSON 반환
                if d.get("returnValue") == "success":
                    print(f"→ ✅")
                    return {
                        "nums":  [int(d.get(f"drwtNo{i}", 0)) for i in range(1,7)],
                        "bonus": int(d.get("bnusNo", 0)),
                        "date":  d.get("drwNoDate", "")
                    }
                print(f"→ 미발표 또는 데이터 없음")
                return None
        except Exception as e:
            print(f"→ 예외({attempt+1}): {str(e)[:60]}")
            if attempt < 2:
                time.sleep(2)
    return None


def fetch_pension(drw_no: int) -> dict | None:
    """공공데이터포털 API → 연금복권 당첨번호"""
    if not SERVICE_KEY:
        return None

    url = "https://apis.data.go.kr/B551015/LrsrsInfoService/getPension720Number"
    params = {
        "serviceKey": SERVICE_KEY,
        "drwNo":      drw_no,
        "_type":      "json",
    }
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=15)
            print(f"    HTTP {r.status_code}", end=" ")
            d = r.json()
            items = (d.get("response", {})
                      .get("body", {})
                      .get("items", {})
                      .get("item", {}))
            if isinstance(items, list):
                items = items[0] if items else {}
            if items:
                jo   = int(items.get("pnsWinNm1", 1))
                nums = [int(items.get(f"pnsWin1Num{i}", 0)) for i in range(1,7)]
                print(f"→ ✅")
                return {"jo": jo, "nums": nums, "date": items.get("drwDate", "")}
            print(f"→ 미발표 또는 데이터 없음")
            return None
        except Exception as e:
            print(f"→ 예외({attempt+1}): {str(e)[:60]}")
            if attempt < 2:
                time.sleep(2)
    return None


def _save(path, data, draws, latest):
    data.update({
        "draws":      draws,
        "latest_drw": latest,
        "total":      len(draws),
        "updated":    datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    })
    DATA_DIR.mkdir(exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8"
    )


def update_lotto(mode="new"):
    path   = DATA_DIR / "lotto.json"
    data   = json.loads(path.read_text("utf-8")) if path.exists() else {"draws": {}}
    draws  = data.get("draws", {})
    latest = calc_latest_lotto()

    if mode == "all":
        targets = [n for n in range(1, latest+1) if str(n) not in draws]
    else:
        targets = [n for n in range(max(1, latest-2), latest+1) if str(n) not in draws]

    print(f"[로또] 수집 대상: {len(targets)}회차 (최신 {latest}회)")
    if not targets:
        print("[로또] 모두 수집 완료\n"); return

    collected = failed = 0
    for drw_no in targets:
        print(f"  → {drw_no}회 조회...", end=" ", flush=True)
        result = fetch_lotto(drw_no)
        if result:
            draws[str(drw_no)] = result
            collected += 1
            print(f"  {result['nums']} +{result['bonus']} ({result['date']})")
            if collected % 100 == 0:
                _save(path, data, draws, latest)
        else:
            failed += 1
            print(f"  ❌")
        time.sleep(0.2)

    _save(path, data, draws, latest)
    print(f"[로또] 완료: 수집 {collected} / 실패 {failed} / 누계 {len(draws)}회차\n")


def update_pension(mode="new"):
    path   = DATA_DIR / "pension.json"
    data   = json.loads(path.read_text("utf-8")) if path.exists() else {"draws": {}}
    draws  = data.get("draws", {})
    latest = calc_latest_pension()

    if mode == "all":
        targets = [n for n in range(1, latest+1) if str(n) not in draws]
    else:
        targets = [n for n in range(max(1, latest-2), latest+1) if str(n) not in draws]

    print(f"[연금복권] 수집 대상: {len(targets)}회차 (최신 {latest}회)")
    if not targets:
        print("[연금복권] 모두 수집 완료\n"); return

    collected = failed = 0
    for drw_no in targets:
        print(f"  → {drw_no}회 조회...", end=" ", flush=True)
        result = fetch_pension(drw_no)
        if result:
            draws[str(drw_no)] = result
            collected += 1
            print(f"  {result['jo']}조 {result['nums']} ({result['date']})")
            if collected % 100 == 0:
                _save(path, data, draws, latest)
        else:
            failed += 1
            print(f"  ❌")
        time.sleep(0.2)

    _save(path, data, draws, latest)
    print(f"[연금복권] 완료: 수집 {collected} / 실패 {failed} / 누계 {len(draws)}회차\n")


if __name__ == "__main__":
    if not SERVICE_KEY:
        print("❌ LOTTO_API_KEY 환경변수가 없습니다.")
        print("   GitHub → Settings → Secrets → LOTTO_API_KEY 등록 후 재실행하세요.")
        exit(1)

    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["all", "new"], default="new")
    args = parser.parse_args()

    print(f"=== 동행복권 수집 시작 (mode={args.mode}) ===")
    update_lotto(args.mode)
    update_pension(args.mode)
    print("=== 수집 완료 ===")
