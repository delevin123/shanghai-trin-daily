# 上证TRIN每日自动计算

通过通达信盘后日线包计算上海证券交易所A股TRIN（Arms Index）。

- [最新日报（生成成功后出现）](data/trin_latest.md)
- [最新JSON（生成成功后出现）](https://raw.githubusercontent.com/delevin123/shanghai-trin-daily/main/data/trin_latest.json)
- [GitHub Actions运行状态](https://github.com/delevin123/shanghai-trin-daily/actions)

## 执行时间

GitHub Actions 工作日北京时间23:17、次日07:17尝试运行，也可在 Actions 页面手动点击 Run workflow。GitHub定时任务可能延迟，数据发布也可能失败；推送时请核验 trading_date。

## 指标定义

TRIN = (沪市上涨家数/下跌家数)/(上涨股票成交股数/下跌股票成交股数)。统计主板、科创板A股（含ST）；排除非A股、ETF、债券、停牌、零成交；平盘股不计入涨跌比。

## 自检与运行

```bash
python calc_sh_trin.py --self-test
python daily_report.py --date 2026-10-26 --zip 20261026.zip
python daily_report.py
```

验证：2026-10-26真实官方盘后数据 TRIN=0.6351。

## 首次启用事项

在 Settings > Actions > General > Workflow permissions 检查是否允许 Read and write permissions。若未允许，请开启，以便工作流自动提交日报。

若官网行情包暂未发布或无法访问，脚本报错并保留上一次成功数据，**不会编造新数值**。每日早报须检查 JSON 的 trading_date。
