#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compute the standard Arms Index (TRIN) for Shanghai Stock Exchange A-shares.

Data source: TDX (Tongdaxin) daily end-of-day market package.
Method and binary field layout adapted from the public a-stock-data Skill:
https://github.com/simonlin1212/a-stock-data (Apache-2.0)

Usage:
    python3 calc_sh_trin.py --date 2026-10-26
    python3 calc_sh_trin.py --date 2026-10-26 --zip 20261026.zip
    python3 calc_sh_trin.py --date 2026-10-26 --csv sh_trin_details.csv
    python3 calc_sh_trin.py --self-test

Python standard library only.  No financial API key required.
"""
import argparse
import csv
import io
import math
import re
import struct
import sys
import urllib.error
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

SOURCE_URL = "https://www.tdx.com.cn/products/data/data/g4day/{ymd}.zip"
SH_A_PREFIXES = ("600", "601", "603", "605", "688", "689")


def get_data(trade_day, local_zip=None):
    ymd = trade_day.replace("-", "")
    if local_zip:
        data = Path(local_zip).read_bytes()
        origin = str(Path(local_zip).resolve())
    else:
        origin = SOURCE_URL.format(ymd=ymd)
        req = urllib.request.Request(
            origin, headers={"User-Agent": "Mozilla/5.0 AShareTRIN/1.0"}
        )
        try:
            with urllib.request.urlopen(req, timeout=70) as response:
                data = response.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(
                f"无法下载 {origin}: {exc}\n"
                "你也可以用浏览器下载该URL到本地，然后使用 --zip 文件名。"
            ) from exc
    if not data.startswith(b"PK"):
        raise ValueError(f"下载内容不是ZIP压缩包：{origin}")
    return data, origin


def parse_sh_stock_rows(data, trade_day, minimum_priced=10_000):
    """Read .cod and .md1 according to the a-stock-data Skill (TDX format)."""
    ymd = trade_day.replace("-", "")
    cod_file = f"sh{ymd[2:]}.cod"
    md1_file = f"sh{ymd[2:]}.md1"
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        if cod_file not in names or md1_file not in names:
            raise ValueError(f"数据包缺少 {cod_file} / {md1_file}。文件: {names[:12]}")
        cod = archive.read(cod_file)
        md1 = archive.read(md1_file)

    if len(cod) % 150 != 0 or len(md1) % 512 != 0:
        raise ValueError(".cod 或 .md1 的块长度不是150 / 512的整数倍，数据可能损坏")
    if len(cod) // 150 != len(md1) // 512:
        raise ValueError("代码表与行情块条数不匹配，数据可能损坏")

    stocks = []
    seen_codes, seen_seqs = set(), set()
    priced = 0
    for offset in range(0, len(cod), 150):
        record = cod[offset:offset + 150]
        code = record[:6].rstrip(b"\x00 ").decode("ascii", "strict")
        if not re.fullmatch(r"\d{6}", code):
            raise ValueError(f"非标准证券代码: {code}")
        seq = struct.unpack_from("<H", record, 32)[0]
        if code in seen_codes or seq in seen_seqs:
            raise ValueError(f"重复股票代码或行情块序号: {code} / {seq}")
        seen_codes.add(code)
        seen_seqs.add(seq)
        block = md1[seq * 512 : (seq + 1) * 512]
        if len(block) != 512:
            raise ValueError(f"行情块越界: {code} / {seq}")
        prev_close = struct.unpack_from("<d", block, 4)[0]
        close = struct.unpack_from("<d", block, 36)[0]
        volume = struct.unpack_from("<Q", block, 56)[0]  # shares, NOT lots
        amount = struct.unpack_from("<d", block, 72)[0]
        if not all(math.isfinite(v) for v in (prev_close, close, amount)):
            raise ValueError(f"数值异常: {code}")
        if close <= 0:
            continue
        priced += 1
        if not code.startswith(SH_A_PREFIXES):
            continue  # remove indices (000), B shares (900), ETFs (5xx), bonds etc.
        raw_name = record[40:72].split(b"\x00", 1)[0]
        name = raw_name.decode("gbk", "strict").strip()
        if not name:
            raise ValueError(f"无证券名称: {code}")
        if prev_close <= 0:
            raise ValueError(f"个股缺失昨收价: {code}")
        # Some suspended shares can have a close but zero volume, not valid in TRIN.
        if volume <= 0:
            continue
        stocks.append(
            {"code": code, "name": name, "prev_close": prev_close,
             "close": close, "volume_shares": volume, "amount_cny": amount,
             "change_pct": (close / prev_close - 1) * 100}
        )
    if priced < minimum_priced:
        raise ValueError(f"沪市只有 {priced} 条有价格证券记录，低于Skill实测完整包下限 {minimum_priced}")
    if minimum_priced and not (1500 <= len(stocks) <= 4000):
        raise ValueError(f"沪市A股筛选出 {len(stocks)} 只，超出合理数量范围，需检查数据与代码规则")
    return stocks, priced


def calc_trin(stocks):
    # Floating comparison with price tick tolerance (stocks quote 2 decimal places).
    adv = [r for r in stocks if r["close"] > r["prev_close"] + 1e-6]
    dec = [r for r in stocks if r["close"] < r["prev_close"] - 1e-6]
    flat = len(stocks) - len(adv) - len(dec)
    av = sum(r["volume_shares"] for r in adv)
    dv = sum(r["volume_shares"] for r in dec)
    if not adv or not dec or not av or not dv:
        raise ValueError("涨跌家数或成交量为零，无法计算TRIN")
    result = (len(adv) / len(dec)) / (av / dv)
    return {"trin": result, "adv_count": len(adv), "dec_count": len(dec),
            "flat_count": flat, "total_count": len(stocks),
            "adv_volume": av, "dec_volume": dv,
            "adv_decl_ratio": len(adv) / len(dec),
            "vol_ratio": av / dv}


def self_test():
    # Test binary format and formula without any internet access.
    codes = [("600001", "甲A", 10., 11., 100),
             ("688001", "乙A", 10., 12., 100),
             ("601001", "丙A", 10., 9., 100),
             ("605001", "丁A", 10., 8., 300),
             ("510050", "ETF", 10., 11., 99),
             ("900001", "B股", 10., 9., 99)]
    cod_bytes, md1_bytes = bytearray(), bytearray()
    for i, (code, name, previous, close, volume) in enumerate(codes):
        cr = bytearray(150)
        cr[0:6] = code.encode("ascii")
        struct.pack_into("<H", cr, 32, i)
        nm = name.encode("gbk")
        cr[40:40 + len(nm)] = nm
        cod_bytes.extend(cr)
        mr = bytearray(512)
        struct.pack_into("<d", mr, 4, previous)
        struct.pack_into("<4d", mr, 12, close, close, close, close)
        struct.pack_into("<Q", mr, 56, volume)
        struct.pack_into("<d", mr, 72, close * volume)
        md1_bytes.extend(mr)
    zipped = io.BytesIO()
    with zipfile.ZipFile(zipped, "w") as f:
        f.writestr("sh261026.cod", cod_bytes)
        f.writestr("sh261026.md1", md1_bytes)
    rows, priced = parse_sh_stock_rows(zipped.getvalue(), "2026-10-26", minimum_priced=0)
    summary = calc_trin(rows)
    assert len(rows) == 4 and priced == 6
    assert summary["adv_count"] == 2 and summary["dec_count"] == 2
    assert summary["adv_volume"] == 200 and summary["dec_volume"] == 400
    assert abs(summary["trin"] - 2.0) < 1e-10
    print("自检通过：二进制解析、A股过滤、TRIN=2.000000 (模拟数据)")


def main():
    parser = argparse.ArgumentParser(description="从通达信盘后包计算上证A股 TRIN")
    parser.add_argument("--date", default="2026-10-26", help="交易日YYYY-MM-DD，默认2026-10-26")
    parser.add_argument("--zip", dest="zipfile", help="本地盘后zip，用于无法访问网络的情况")
    parser.add_argument("--csv", help="可选：导出逐股核对CSV")
    parser.add_argument("--self-test", action="store_true", help="离线模拟数据校验解析与计算公式")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    try:
        date.fromisoformat(args.date)
    except ValueError as e:
        parser.error(f"交易日格式错误: {e}")
    print(f"日期：{args.date}\n数据：通达信官方每日盘后ZIP，解析参考GitHub a-stock-data Skill")
    raw, source = get_data(args.date, args.zipfile)
    rows, priced = parse_sh_stock_rows(raw, args.date)
    v = calc_trin(rows)
    print(f"来源：{source}")
    print(f"通达信沪市有价记录：{priced:,}（包含指数/基金/债券等，已排除）")
    print(f"有效沪市A股数（含ST、剔除停牌/零成交）：{v['total_count']:,}")
    print(f"上涨：{v['adv_count']:,}只；成交量：{v['adv_volume']:,}股（{v['adv_volume']/1e8:,.4f}亿股）")
    print(f"下跌：{v['dec_count']:,}只；成交量：{v['dec_volume']:,}股（{v['dec_volume']/1e8:,.4f}亿股）")
    print(f"平盘：{v['flat_count']:,}只（不计入TRIN分子/分母）")
    print(f"涨跌家数比：{v['adv_decl_ratio']:.6f}")
    print(f"涨跌成交量比：{v['vol_ratio']:.6f}")
    print(f"上证A股TRIN：{v['trin']:.6f}")
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) + ["direction"])
            w.writeheader()
            for r in rows:
                direction = "上涨" if r["close"] > r["prev_close"] + 1e-6 else (
                    "下跌" if r["close"] < r["prev_close"] - 1e-6 else "平盘")
                w.writerow({**r, "direction": direction})
        print(f"逐股核对表：{args.csv}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        raise SystemExit(1)