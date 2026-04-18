"""
株価リターン計算・テーマ相関評価モジュール

機能:
  1. yfinance で東証銘柄の株価を取得
  2. 指定日からのN日後リターンを計算
  3. TOPIX ETF(1306.T)との超過リターンを計算
  4. 過去スナップショットにリターンを書き戻す（バックテスト）
"""
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, date
from typing import Optional

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import PRICE_BENCHMARK_TICKER, PRICE_RETURN_DAYS, PRICE_TOP_N_STOCKS

logger = logging.getLogger(__name__)


@dataclass
class StockReturn:
    code: str
    name: str
    ticker: str                          # "7203.T"
    returns: dict[str, Optional[float]]  # {"1d": 0.012, "5d": 0.034, "20d": None}
    excess:  dict[str, Optional[float]]  # vs TOPIX


@dataclass
class CorrelationSummary:
    """テーマごとのリターン集計"""
    theme_name: str
    avg_return: dict[str, Optional[float]]   # 日数 → 平均リターン
    win_rate:   dict[str, Optional[float]]   # 日数 → 勝率(プラスの割合)
    stock_count: int


def _ticker(code: str) -> str:
    return f"{code}.T"


def fetch_returns(
    codes: list[str],
    base_date: str,                      # "2026-04-18"
    return_days: list[int] | None = None,
) -> dict[str, StockReturn]:
    """
    指定日を基準に各銘柄のN日後リターンを取得する

    Args:
        codes:       証券コードリスト
        base_date:   起点日 (YYYY-MM-DD)
        return_days: [1, 5, 20] など

    Returns:
        {code: StockReturn}
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance が必要です: pip install yfinance")
        return {}

    if return_days is None:
        return_days = PRICE_RETURN_DAYS

    base_dt  = datetime.strptime(base_date, "%Y-%m-%d").date()
    max_days = max(return_days)
    # 祝日考慮: 取得期間を多めに設定
    fetch_start = base_dt - timedelta(days=5)
    fetch_end   = base_dt + timedelta(days=max_days + 10)
    today = datetime.now().date()
    fetch_end = min(fetch_end, today)

    all_codes = list(set(codes + [PRICE_BENCHMARK_TICKER.replace(".T", "")]))
    tickers   = [_ticker(c) for c in all_codes]

    logger.info(f"株価取得: {len(tickers)} 銘柄 ({base_date} 基準)")

    try:
        import yfinance as yf
        data = yf.download(
            tickers,
            start = fetch_start.strftime("%Y-%m-%d"),
            end   = fetch_end.strftime("%Y-%m-%d"),
            auto_adjust= True,
            progress   = False,
            threads    = True,
        )
    except Exception as e:
        logger.error(f"yfinance エラー: {e}")
        return {}

    if data.empty:
        logger.warning("株価データを取得できませんでした")
        return {}

    # Close 価格の DataFrame を取得
    close = data["Close"] if "Close" in data else data.xs("Close", axis=1, level=0)

    def get_price(ticker: str, target_date: date) -> Optional[float]:
        """指定日以降の最初の有効な終値を取得"""
        if ticker not in close.columns:
            return None
        series = close[ticker].dropna()
        future = series[series.index.date >= target_date]
        if future.empty:
            return None
        return float(future.iloc[0])

    # ベンチマーク価格
    bench_ticker = PRICE_BENCHMARK_TICKER
    bench_base   = get_price(bench_ticker, base_dt)

    def bench_return(n_days: int) -> Optional[float]:
        if bench_base is None or bench_base == 0:
            return None
        target = base_dt + timedelta(days=n_days)
        p = get_price(bench_ticker, target)
        if p is None:
            return None
        return round((p - bench_base) / bench_base, 4)

    bench_returns = {str(n): bench_return(n) for n in return_days}

    # 各銘柄のリターン計算
    results: dict[str, StockReturn] = {}
    for code in codes:
        t = _ticker(code)
        base_price = get_price(t, base_dt)
        if base_price is None:
            continue

        returns: dict[str, Optional[float]] = {}
        excess:  dict[str, Optional[float]] = {}

        for n in return_days:
            target = base_dt + timedelta(days=n)
            p = get_price(t, target)
            if p is None or base_price == 0:
                returns[f"{n}d"] = None
                excess[f"{n}d"]  = None
            else:
                ret = round((p - base_price) / base_price, 4)
                returns[f"{n}d"] = ret
                bench_r = bench_returns.get(str(n))
                excess[f"{n}d"]  = round(ret - bench_r, 4) if bench_r is not None else None

        results[code] = StockReturn(
            code    = code,
            name    = "",   # 呼び出し元で補完
            ticker  = t,
            returns = returns,
            excess  = excess,
        )

    logger.info(f"リターン計算完了: {len(results)} 銘柄 / {return_days} 日後")
    return results


def summarize_by_theme(
    stock_returns: dict[str, StockReturn],
    snapshot_stocks,           # list[SnapshotStock]
    return_days: list[int] | None = None,
) -> list[CorrelationSummary]:
    """テーマ別にリターンを集計してサマリーを返す"""
    if return_days is None:
        return_days = PRICE_RETURN_DAYS

    theme_stocks: dict[str, list[StockReturn]] = {}
    for ss in snapshot_stocks:
        sr = stock_returns.get(ss.code)
        if sr is None:
            continue
        theme = ss.primary_theme
        theme_stocks.setdefault(theme, []).append(sr)

    summaries = []
    for theme, stock_list in theme_stocks.items():
        avg_ret: dict[str, Optional[float]] = {}
        win_rate: dict[str, Optional[float]] = {}
        for n in return_days:
            key = f"{n}d"
            vals = [sr.excess.get(key) for sr in stock_list
                    if sr.excess.get(key) is not None]
            if vals:
                avg_ret[key]  = round(sum(vals) / len(vals), 4)
                win_rate[key] = round(sum(1 for v in vals if v > 0) / len(vals), 2)
            else:
                avg_ret[key]  = None
                win_rate[key] = None

        summaries.append(CorrelationSummary(
            theme_name  = theme,
            avg_return  = avg_ret,
            win_rate    = win_rate,
            stock_count = len(stock_list),
        ))

    summaries.sort(key=lambda s: s.avg_return.get("5d") or -99, reverse=True)
    return summaries


def backtest_snapshot(snapshot, return_days: list[int] | None = None) -> dict[str, StockReturn]:
    """
    過去スナップショットの銘柄リストに対してリターンを計算する

    Args:
        snapshot: Snapshot オブジェクト
        return_days: [1, 5, 20]

    Returns:
        {code: StockReturn}
    """
    if return_days is None:
        return_days = PRICE_RETURN_DAYS

    codes = [s.code for s in snapshot.ranked_stocks[:PRICE_TOP_N_STOCKS]]
    results = fetch_returns(codes, snapshot.date, return_days)

    # name を補完
    name_map = {s.code: s.name for s in snapshot.ranked_stocks}
    for code, sr in results.items():
        sr.name = name_map.get(code, "")

    return results
