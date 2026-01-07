# Binance UT Bot Alert (Python)

这是一个基于 Python 的币安合约实时行情监控机器人，策略逻辑完全复刻 TradingView 上的 "UT Bot Alerts" 策略。

## 功能特点
- **完全一致性**：与 TradingView 的 UT Bot 策略逻辑、参数和信号触发时间完全同步。
- **实时推送**：基于 WebSocket 毫秒级监控，信号触发立即推送到钉钉群。
- **防抖动**：包含状态锁定机制，避免同向信号重复报警。
- **北京时间**：强制将日志和消息时间转换为 UTC+8。

## 策略参数 (默认)
- **Key Value (Sensitivity)**: 1.0
- **ATR Period**: 10
- **Heikin Ashi**: False (使用真实 K 线)

## 如何运行
1. 安装依赖:
   ```bash
   pip install -r requirements.txt
   ```   
2.配置钉钉 Token: 打开 utbot.py，将 DINGTALK_WEBHOOK 替换为你自己的机器人链接。

3.启动:
 ```bash
python utbot.py
