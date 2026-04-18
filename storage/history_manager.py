"""
分析結果のスナップショット管理

保存形式: storage/history/YYYY-MM-DD_HHMMSS.json
  {
    "timestamp":   "2026-04-18T10:30:00",
    "date":        "2026-04-18",
    "mode":        "rule",
    "themes":      [{name, score, article_count, sentiment, sub_themes, top_source_rank}],
    "ranked_stocks": [{code, name, market_badge, score, stars, theme_weights, primary_theme}],
    "price_returns": {code: {1: 0.012, 5: 0.034, 20: null}}  ← 後から埋める
  }
"""
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import STORAGE_DIR, HISTORY_KEEP_DAYS

logger = logging.getLogger(__name__)


@dataclass
class SnapshotTheme:
    name: str
    score: float
    article_count: int
    sentiment: float
    top_source_rank: int
    sub_theme_names: list[str] = field(default_factory=list)


@dataclass
class SnapshotStock:
    code: str
    name: str
    market_badge: str
    score: float
    stars: int
    primary_theme: str
    theme_weights: dict[str, float] = field(default_factory=dict)
    price_returns: dict[str, Optional[float]] = field(default_factory=dict)
    # {"1d": 0.012, "5d": 0.034, "20d": None}
    excess_returns: dict[str, Optional[float]] = field(default_factory=dict)
    # vs TOPIX: {"1d": 0.003, "5d": 0.010, "20d": None}


@dataclass
class Snapshot:
    timestamp: str
    date: str
    mode: str
    themes: list[SnapshotTheme] = field(default_factory=list)
    ranked_stocks: list[SnapshotStock] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "timestamp":      self.timestamp,
            "date":           self.date,
            "mode":           self.mode,
            "themes":         [asdict(t) for t in self.themes],
            "ranked_stocks":  [asdict(s) for s in self.ranked_stocks],
        }

    @staticmethod
    def from_dict(d: dict) -> "Snapshot":
        snap = Snapshot(
            timestamp = d["timestamp"],
            date      = d["date"],
            mode      = d.get("mode", "rule"),
        )
        snap.themes = [SnapshotTheme(**t) for t in d.get("themes", [])]
        snap.ranked_stocks = [SnapshotStock(**s) for s in d.get("ranked_stocks", [])]
        return snap


def save_snapshot(
    analysis,          # AnalysisResult
    ranked_stocks,     # list[RankedStock]
    date_str: str | None = None,
) -> str:
    """
    分析結果をスナップショットとして保存する

    Returns:
        保存したファイルパス
    """
    os.makedirs(STORAGE_DIR, exist_ok=True)
    now = datetime.now()
    date_str = date_str or now.strftime("%Y-%m-%d")
    ts_str   = now.strftime("%Y-%m-%dT%H:%M:%S")
    filename = now.strftime("%Y-%m-%d_%H%M%S") + ".json"
    filepath = os.path.join(STORAGE_DIR, filename)

    themes = [
        SnapshotTheme(
            name            = t.name,
            score           = t.score,
            article_count   = t.article_count,
            sentiment       = t.sentiment,
            top_source_rank = t.top_source_rank,
            sub_theme_names = [s.name for s in t.sub_themes],
        )
        for t in analysis.themes[:10]
    ]

    stocks = [
        SnapshotStock(
            code          = rs.stock.code,
            name          = rs.stock.name,
            market_badge  = rs.stock.market_badge,
            score         = rs.score,
            stars         = rs.stars,
            primary_theme = rs.stock.primary_theme,
            theme_weights = rs.stock.theme_weights,
            price_returns = {},
            excess_returns= {},
        )
        for rs in ranked_stocks[:50]
    ]

    snap = Snapshot(
        timestamp     = ts_str,
        date          = date_str,
        mode          = analysis.mode,
        themes        = themes,
        ranked_stocks = stocks,
    )

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(snap.to_dict(), f, ensure_ascii=False, indent=2)

    logger.info(f"スナップショット保存: {filepath}")
    _cleanup_old_snapshots()
    return filepath


def load_snapshots(last_n: int = 10) -> list[Snapshot]:
    """最新 N 件のスナップショットを読み込む（新しい順）"""
    if not os.path.isdir(STORAGE_DIR):
        return []
    files = sorted(Path(STORAGE_DIR).glob("*.json"), reverse=True)[:last_n]
    snaps = []
    for f in files:
        try:
            with open(f, encoding="utf-8") as fp:
                snaps.append(Snapshot.from_dict(json.load(fp)))
        except Exception as e:
            logger.warning(f"スナップショット読込失敗 {f}: {e}")
    return snaps


def update_price_returns(filepath: str, price_data: dict) -> None:
    """
    保存済みスナップショットに株価リターンを追記する

    Args:
        filepath:   スナップショットファイルパス
        price_data: {code: {"1d": 0.012, "5d": 0.034, "20d": None, ...},
                           "excess": {"1d": 0.003, ...}}
    """
    try:
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
        for stock in data.get("ranked_stocks", []):
            code = stock["code"]
            if code in price_data:
                stock["price_returns"]  = price_data[code].get("returns", {})
                stock["excess_returns"] = price_data[code].get("excess", {})
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"株価リターンを更新: {filepath}")
    except Exception as e:
        logger.error(f"株価リターン更新失敗: {e}")


def _cleanup_old_snapshots() -> None:
    """古いスナップショットを削除"""
    cutoff = datetime.now() - timedelta(days=HISTORY_KEEP_DAYS)
    for f in Path(STORAGE_DIR).glob("*.json"):
        try:
            file_dt = datetime.strptime(f.stem[:10], "%Y-%m-%d")
            if file_dt < cutoff:
                f.unlink()
                logger.debug(f"古いスナップショットを削除: {f.name}")
        except Exception:
            pass
