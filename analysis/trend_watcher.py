"""
トレンド変化検知モジュール

スナップショット履歴を比較して以下を検知する:
  - 新規出現テーマ (new)
  - 消滅テーマ (disappeared)
  - スコア急上昇 (rising: 前回比+20以上)
  - スコア急落 (falling: 前回比-20以下)
  - 安定テーマ (stable)
  - 銘柄ランク変動（急上昇・急落）
"""
from dataclasses import dataclass, field
from typing import Optional
import logging

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from storage.history_manager import Snapshot, load_snapshots

logger = logging.getLogger(__name__)

RISING_THRESHOLD  =  15.0   # スコア変化でRisingとみなす閾値
FALLING_THRESHOLD = -15.0


@dataclass
class ThemeChange:
    name: str
    change_type: str        # "new" | "disappeared" | "rising" | "falling" | "stable"
    current_score: float
    prev_score: Optional[float]
    score_delta: Optional[float]
    current_rank: Optional[int]
    prev_rank: Optional[int]
    rank_delta: Optional[int]   # 順位変化（マイナスが改善）
    sentiment_delta: Optional[float]
    arrow: str = ""             # "↑↑" | "↑" | "→" | "↓" | "↓↓"

    def __post_init__(self):
        if self.change_type == "new":
            self.arrow = "🆕"
        elif self.change_type == "disappeared":
            self.arrow = "💨"
        elif self.score_delta is not None:
            if self.score_delta >= 30:
                self.arrow = "↑↑"
            elif self.score_delta >= RISING_THRESHOLD:
                self.arrow = "↑"
            elif self.score_delta <= -30:
                self.arrow = "↓↓"
            elif self.score_delta <= FALLING_THRESHOLD:
                self.arrow = "↓"
            else:
                self.arrow = "→"


@dataclass
class StockChange:
    code: str
    name: str
    market_badge: str
    current_rank: int
    prev_rank: Optional[int]
    rank_delta: Optional[int]
    current_score: float
    score_delta: Optional[float]
    arrow: str = ""

    def __post_init__(self):
        if self.prev_rank is None:
            self.arrow = "🆕"
        elif self.rank_delta is not None:
            if self.rank_delta <= -10:
                self.arrow = "↑↑"
            elif self.rank_delta <= -3:
                self.arrow = "↑"
            elif self.rank_delta >= 10:
                self.arrow = "↓↓"
            elif self.rank_delta >= 3:
                self.arrow = "↓"
            else:
                self.arrow = "→"


@dataclass
class WatchResult:
    current_date: str
    prev_date: Optional[str]
    theme_changes: list[ThemeChange] = field(default_factory=list)
    stock_changes: list[StockChange] = field(default_factory=list)
    new_themes: list[str] = field(default_factory=list)
    disappeared_themes: list[str] = field(default_factory=list)
    has_history: bool = False


def watch_trends(current_snap: Snapshot, last_n: int = 5) -> WatchResult:
    """
    現在のスナップショットと過去履歴を比較してトレンド変化を返す

    Args:
        current_snap: 今回の分析結果を Snapshot 化したもの
        last_n:       比較に使う過去スナップショット数

    Returns:
        WatchResult
    """
    history = load_snapshots(last_n + 1)

    # 最新は自分自身と被る可能性があるので1つずらす
    prev_snaps = [s for s in history if s.timestamp != current_snap.timestamp]
    if not prev_snaps:
        logger.info("比較対象の履歴がありません（初回実行）")
        return WatchResult(
            current_date = current_snap.date,
            prev_date    = None,
            has_history  = False,
            theme_changes= [
                ThemeChange(
                    name=t.name, change_type="new",
                    current_score=t.score, prev_score=None,
                    score_delta=None, current_rank=i+1, prev_rank=None,
                    rank_delta=None, sentiment_delta=None,
                )
                for i, t in enumerate(current_snap.themes)
            ],
        )

    prev = prev_snaps[0]   # 直前スナップショット

    # --- テーマ変化 ---
    curr_theme_map = {t.name: (i, t) for i, t in enumerate(current_snap.themes)}
    prev_theme_map = {t.name: (i, t) for i, t in enumerate(prev.themes)}

    theme_changes: list[ThemeChange] = []
    for name, (curr_rank, curr_t) in curr_theme_map.items():
        if name in prev_theme_map:
            prev_rank, prev_t = prev_theme_map[name]
            delta = curr_t.score - prev_t.score
            change_type = (
                "rising"  if delta >= RISING_THRESHOLD
                else "falling" if delta <= FALLING_THRESHOLD
                else "stable"
            )
            theme_changes.append(ThemeChange(
                name=name, change_type=change_type,
                current_score=curr_t.score, prev_score=prev_t.score,
                score_delta=round(delta, 1),
                current_rank=curr_rank+1, prev_rank=prev_rank+1,
                rank_delta=(curr_rank - prev_rank),
                sentiment_delta=round(curr_t.sentiment - prev_t.sentiment, 2),
            ))
        else:
            theme_changes.append(ThemeChange(
                name=name, change_type="new",
                current_score=curr_t.score, prev_score=None,
                score_delta=None, current_rank=curr_rank+1,
                prev_rank=None, rank_delta=None, sentiment_delta=None,
            ))

    for name, (prev_rank, prev_t) in prev_theme_map.items():
        if name not in curr_theme_map:
            theme_changes.append(ThemeChange(
                name=name, change_type="disappeared",
                current_score=0.0, prev_score=prev_t.score,
                score_delta=None, current_rank=None,
                prev_rank=prev_rank+1, rank_delta=None, sentiment_delta=None,
            ))

    theme_changes.sort(key=lambda c: (
        0 if c.change_type == "new"
        else 1 if c.change_type == "rising"
        else 2 if c.change_type == "stable"
        else 3 if c.change_type == "falling"
        else 4
    ))

    # --- 銘柄ランク変化（上位30のみ） ---
    curr_stock_map = {s.code: (i+1, s) for i, s in enumerate(current_snap.ranked_stocks[:30])}
    prev_stock_map = {s.code: (i+1, s) for i, s in enumerate(prev.ranked_stocks[:30])}

    stock_changes: list[StockChange] = []
    for code, (curr_rank, curr_s) in curr_stock_map.items():
        prev_rank = prev_stock_map.get(code, (None, None))[0]
        prev_score = prev_stock_map.get(code, (None, None))[1]
        stock_changes.append(StockChange(
            code=code, name=curr_s.name, market_badge=curr_s.market_badge,
            current_rank=curr_rank, prev_rank=prev_rank,
            rank_delta=(curr_rank - prev_rank) if prev_rank else None,
            current_score=curr_s.score,
            score_delta=round(curr_s.score - prev_score.score, 1) if prev_score else None,
        ))

    stock_changes.sort(key=lambda s: s.current_rank)

    return WatchResult(
        current_date       = current_snap.date,
        prev_date          = prev.date,
        theme_changes      = theme_changes,
        stock_changes      = stock_changes,
        new_themes         = [c.name for c in theme_changes if c.change_type == "new"],
        disappeared_themes = [c.name for c in theme_changes if c.change_type == "disappeared"],
        has_history        = True,
    )
