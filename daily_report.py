#!/usr/bin/env python3
"""Download the most recent published official TDX daily package and publish TRIN."""
import argparse
import json
import sys
from datetime import datetime, timedelta, date
from pathlib import Path
from zoneinfo import ZoneInfo
from calc_sh_trin import get_data, parse_sh_stock_rows, calc_trin, SOURCE_URL

TZ=ZoneInfo("Asia/Shanghai")

def run(trade_day, local_zip=None):
    raw, origin=get_data(trade_day.isoformat(),local_zip)
    rows, n=parse_sh_stock_rows(raw,trade_day.isoformat())
    r=calc_trin(rows)
    if r["total_count"] != r["adv_count"]+r["dec_count"]+r["flat_count"]:
        raise ValueError("inconsistent classification")
    return dict(trading_date=trade_day.isoformat(),updated_at_beijing=datetime.now(TZ).isoformat(timespec="seconds"),
        source_url=SOURCE_URL.format(ymd=trade_day.strftime("%Y%m%d")),retrieved_from=origin,
        stock_count=r["total_count"],advance_count=r["adv_count"],decline_count=r["dec_count"],
        unchanged_count=r["flat_count"],advance_volume_shares=r["adv_volume"],
        decline_volume_shares=r["dec_volume"],priced_records_in_sh_package=n,
        advance_decline_count_ratio=round(r["adv_decl_ratio"],8),
        advance_decline_volume_ratio=round(r["vol_ratio"],8),trin=round(r["trin"],8))

def save(r,folder):
    folder=Path(folder)
    history=folder/"history"
    history.mkdir(parents=True,exist_ok=True)
    latest=folder/"trin_latest.json"
    if latest.exists():
        old=json.loads(latest.read_text(encoding="utf8"))
        if old.get("trading_date","")>r["trading_date"]:
            raise RuntimeError("Refusing stale overwrite")
    body=json.dumps(r,ensure_ascii=False,indent=2)+"\n"
    (history/(r["trading_date"]+".json")).write_text(body,encoding="utf8")
    latest.write_text(body,encoding="utf8")
    report=f"""# 上证TRIN日报 {r['trading_date']}

- TRIN：**{r['trin']:.4f}**
- 上涨：{r['advance_count']}只，成交量：{r['advance_volume_shares']/1e8:.4f}亿股
- 下跌：{r['decline_count']}只，成交量：{r['decline_volume_shares']/1e8:.4f}亿股
- 平盘：{r['unchanged_count']}只；有效沪市A股：{r['stock_count']}只
- 涨跌家数比：{r['advance_decline_count_ratio']:.6f}
- 涨跌成交量比：{r['advance_decline_volume_ratio']:.6f}
- 来源：{r['source_url']}
- 生成时间（北京时间）：{r['updated_at_beijing']}

TRIN衡量上涨股和下跌股的相对平均成交量，不是预测涨跌的保证。
"""
    (folder/"trin_latest.md").write_text(report,encoding="utf8")
    print(report)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--zip")
    ap.add_argument("--output-dir",default="data")
    args=ap.parse_args()
    if args.zip and not args.date: ap.error("--zip needs --date")
    today=datetime.now(TZ).date()
    if args.date:
        days=[date.fromisoformat(args.date)]
    else:
        days=[today-timedelta(days=i) for i in range(0,18) if (today-timedelta(days=i)).weekday()<5]
    errors=[]
    for d in days:
        try:
            r=run(d,args.zip)
            save(r,args.output_dir)
            return
        except Exception as e:
            errors.append(f"{d.isoformat()}: {e}")
            if args.date: break
    raise RuntimeError("No valid official package found. "+" | ".join(errors[-3:]))
if __name__=="__main__":
    try: main()
    except Exception as e:
        print("ERROR:",e,file=sys.stderr)
        sys.exit(1)
