"""讯息面 shadow 因子（X 情绪）。

设计立场：讯息面数据没有可靠的历史回放（X 情绪无法事后重建），
所以不做回测、不给权重，只做影子记录（shadow）：
  每天给每个标的情绪分 score ∈ [-1, 1]，落 state/sentiment-shadow.csv。
攒 1-2 个月前向数据后，用「情绪分对次日/次周收益的预测力」决定是否
晋升为正式倾斜（±0.1 权重级别）。晋升前它对仓位零影响——这是讯息面
与技术面结合的诚实姿势：技术面负责下单，讯息面负责攒证据。

用法: python -m bnbot.sentiment --once [--proxy http://127.0.0.1:7890]
幂等：当天已有记录则跳过。
"""

import argparse
import csv
import datetime
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERMES_HOME = os.environ.get(
    "HERMES_HOME", r"D:\Hermes Agent CN Desktop\data\hermes-home"
)
CSV_PATH = os.path.join(HERE, "state", "sentiment-shadow.csv")

PROMPT_TMPL = (
    "过去 24 小时 X 上关于以下资产的讨论情绪如何。"
    "对每个资产给一个情绪分 score（-1 到 1 的数字，非常悲观=-1，中性=0，非常乐观=1）、"
    "采样帖数 posts（整数）、一句 20 字以内的理由 note。"
    "资产列表：{symbols}。"
    "只输出纯 JSON，格式 {{\"BTCUSDT\": {{\"score\": 0.2, \"posts\": 40, \"note\": \"...\"}}, ...}}，"
    "不要输出 JSON 以外的任何字符。"
)


def _load_key():
    env_path = os.path.join(HERMES_HOME, ".env")
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("XAI_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("XAI_API_KEY not found in HERMES_HOME/.env")


def fetch_scores(symbols, proxy=None):
    body = {
        "model": "grok-4.20-0309-non-reasoning",
        "input": [{"role": "user", "content": PROMPT_TMPL.format(symbols=", ".join(symbols))}],
        "tools": [{"type": "x_search"}],
        "store": False,
    }
    handlers = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(
        "https://api.x.ai/v1/responses",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + _load_key(),
            "Content-Type": "application/json",
        },
    )
    data = None
    last_err = None
    for attempt in range(4):
        try:
            with opener.open(req, timeout=180) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except Exception as e:  # x.ai 经代理偶发 TLS EOF，退避重试
            last_err = e
            import time
            time.sleep(5 * (attempt + 1))
    if data is None:
        raise RuntimeError(f"xAI request failed after retries: {last_err}")
    text = ""
    for item in data.get("output", []):
        if item.get("type") == "message":
            for c in item.get("content", []):
                if c.get("text"):
                    text += c["text"]
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise RuntimeError("no JSON in model output: " + text[:200])
    return json.loads(m.group(0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="run once and exit")
    ap.add_argument("--proxy", default=None)
    args = ap.parse_args()

    with open(os.path.join(HERE, "config.json"), encoding="utf-8") as f:
        symbols = json.load(f)["symbols"]
    today = datetime.date.today().isoformat()

    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    if os.path.exists(CSV_PATH):
        with open(CSV_PATH, encoding="utf-8") as f:
            if any(row.get("date") == today for row in csv.DictReader(f)):
                print(f"[sentiment] {today} already recorded, skip")
                return 0

    scores = fetch_scores(symbols, proxy=args.proxy)
    new = not os.path.exists(CSV_PATH)
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "symbol", "score", "posts", "note"])
        for sym in symbols:
            s = scores.get(sym) or {}
            w.writerow([
                today, sym,
                float(s.get("score", 0.0)),
                int(s.get("posts", 0)),
                str(s.get("note", ""))[:40],
            ])
    print(f"[sentiment] {today} recorded {len(symbols)} symbols -> {CSV_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
