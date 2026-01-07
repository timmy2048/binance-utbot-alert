import time
import json
from datetime import datetime, timedelta, timezone  # 引入时区处理库
import pandas as pd
import numpy as np
import requests
import websocket

# ==================== 配置部分 ====================
DINGTALK_WEBHOOK = "https://oapi.dingtalk.com/robot/send?access_token=YOURTOKEN"

SENSITIVITY = 1.0       # TV Key Value = 1
ATR_PERIOD = 10         # TV ATR Period = 10
USE_HEIKIN_ASHI = False # TV HA = False
RR_RATIO = 2.0

TICKER_LOWER = "solusdc"
TICKER_UPPER = "SOLUSDC"
INTERVAL = "15m"

WS_URL = f"wss://fstream.binance.com/ws/{TICKER_LOWER}@kline_{INTERVAL}"

# ==================== 全局变量 ====================
df_klines = pd.DataFrame()
current_signal_key = None 

# ==================== 时间处理函数（强制北京时间） ====================
def get_beijing_time_str():
    """
    获取当前的北京时间字符串 (HH:MM:SS)
    无论服务器在哪个时区，都强制转换为 UTC+8
    """
    utc_now = datetime.now(timezone.utc)
    beijing_now = utc_now + timedelta(hours=8)
    return beijing_now.strftime("%H:%M:%S")

# ==================== 钉钉发送函数 ====================
def send_dingtalk_message(message):
    headers = {'Content-Type': 'application/json'}
    payload = {"msgtype": "text", "text": {"content": message}}
    try:
        r = requests.post(DINGTALK_WEBHOOK, json=payload, headers=headers, timeout=5)
        resp = r.json()
        if resp.get("errcode") == 0:
            # 日志也显示北京时间
            print(f"✅ [{get_beijing_time_str()}] 钉钉消息发送成功")
        else:
            print(f"❌ 钉钉发送失败: {resp}")
    except Exception as e:
        print(f"❌ 网络发送异常: {e}")

# ==================== UT Bot 计算逻辑 ====================
def calculate_atr(df, period):
    tr = pd.concat([
        df['high'] - df['low'],
        (df['high'] - df['close'].shift()).abs(),
        (df['low'] - df['close'].shift()).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()

def compute_ut_bot_signals(df, sensitivity, atr_period):
    src = df['close']
    work_df = df.copy()
    work_df['atr'] = calculate_atr(work_df, atr_period)
    work_df['nLoss'] = sensitivity * work_df['atr']

    ts = np.full(len(work_df), np.nan)
    ts[0] = src.iloc[0]
    
    src_values = src.values
    nloss_values = work_df['nLoss'].values
    
    for i in range(1, len(work_df)):
        prev_ts = ts[i-1]
        curr_src = src_values[i]
        prev_src = src_values[i-1]
        
        if curr_src > prev_ts and prev_src > prev_ts:
            ts[i] = max(prev_ts, curr_src - nloss_values[i])
        elif curr_src < prev_ts and prev_src < prev_ts:
            ts[i] = min(prev_ts, curr_src + nloss_values[i])
        elif curr_src > prev_ts:
            ts[i] = curr_src - nloss_values[i]
        else:
            ts[i] = curr_src + nloss_values[i]

    work_df['trailing_stop'] = ts
    
    current_price = src.iloc[-1]
    current_ts = work_df['trailing_stop'].iloc[-1]
    prev_price = src.iloc[-2]
    prev_ts = work_df['trailing_stop'].iloc[-2]

    buy_condition = (prev_price <= prev_ts) and (current_price > current_ts)
    sell_condition = (prev_price >= prev_ts) and (current_price < current_ts)

    return buy_condition, sell_condition, current_ts

# ==================== 初始化与实时监控 ====================
def init_klines():
    global df_klines
    url = "https://fapi.binance.com/fapi/v1/klines"
    params = {'symbol': TICKER_UPPER, 'interval': INTERVAL, 'limit': 300}
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        df = pd.DataFrame(data, columns=[
            'open_time', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'number_of_trades',
            'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
        ])
        df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
        df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
        df.set_index('open_time', inplace=True)
        df_klines = df
        print(f"✅ 历史K线加载完毕，当前最新价: {df['close'].iloc[-1]}")
    except Exception as e:
        print(f"❌ 初始化K线失败: {e}")
        time.sleep(2)
        init_klines()

def on_message(ws, message):
    global current_signal_key, df_klines
    try:
        msg = json.loads(message)
        k = msg['k']
        current_time = pd.to_datetime(k['t'], unit='ms')
        
        new_row = pd.DataFrame([{
            'open': float(k['o']), 'high': float(k['h']),
            'low': float(k['l']), 'close': float(k['c']), 'volume': float(k['v'])
        }], index=[current_time])

        if current_time in df_klines.index:
            df_klines.update(new_row)
        else:
            df_klines = pd.concat([df_klines, new_row])
            if len(df_klines) > 400: df_klines = df_klines.iloc[-400:]

        buy_sig, sell_sig, trailing_stop = compute_ut_bot_signals(df_klines, SENSITIVITY, ATR_PERIOD)
        price = float(k['c'])
        
        # 使用强制北京时间
        bj_time_str = get_beijing_time_str()

        if buy_sig:
            if current_signal_key != "buy":
                risk = price - trailing_stop
                tp = price + (risk * RR_RATIO)
                msg = (f"报警 🟢 【UT Bot 买入信号】\n"
                       f"标的: {TICKER_UPPER}\n价格: {price:.2f}\n"
                       f"时间: {bj_time_str} (北京时间)\n"
                       f"止损: {trailing_stop:.2f}\n目标: {tp:.2f}")
                send_dingtalk_message(msg)
                current_signal_key = "buy"
                print(f"🚀 [BUY] 信号推送 @ {price} 时间: {bj_time_str}")
        
        elif sell_sig:
            if current_signal_key != "sell":
                risk = trailing_stop - price
                tp = price - (risk * RR_RATIO)
                msg = (f"报警 🔴 【UT Bot 卖出信号】\n"
                       f"标的: {TICKER_UPPER}\n价格: {price:.2f}\n"
                       f"时间: {bj_time_str} (北京时间)\n"
                       f"止损: {trailing_stop:.2f}\n目标: {tp:.2f}")
                send_dingtalk_message(msg)
                current_signal_key = "sell"
                print(f"🔻 [SELL] 信号推送 @ {price} 时间: {bj_time_str}")

    except Exception as e:
        # 生产环境通常不打印过于频繁的错误，除非调试
        pass

def on_error(ws, error):
    print(f"WebSocket Error: {error}")

def on_close(ws, *args):
    print("连接断开，正在重连...")
    time.sleep(3)
    start_ws()

def on_open(ws):
    print("✅ WebSocket 连接成功，实时监控中...")

def start_ws():
    ws = websocket.WebSocketApp(WS_URL, on_open=on_open, on_message=on_message, on_error=on_error, on_close=on_close)
    ws.run_forever()

def main():
    print("---------- 程序启动 ----------")
    # 使用强制北京时间
    bj_time_str = get_beijing_time_str()
    start_msg = f"报警 🟢 监控程序已启动！\n标的: {TICKER_UPPER}\n时间: {bj_time_str} (北京时间)\n\n收到此消息说明推送正常。"
    print("正在发送钉钉测试消息...")
    send_dingtalk_message(start_msg)
    
    init_klines()
    start_ws()

if __name__ == "__main__":
    main()