"""
スコアリング・ランク付けモジュール

スコア内訳（100点満点）:
  theme_relevance (50pt) : テーマスコア × 重みで按分
  mention_count   (20pt) : テーマ内の関連記事数
  sentiment       (20pt) : ポジティブ報道の割合
  theme_momentum  (10pt) : テーマが上位に来るほど加算

星ランク:
  ★★★★★ 80-100
  ★★★★  60-79
  ★★★   40-59
  ★★    20-39
  ★     0-19
"""
import math
import logging
from dataclasses import dataclass
from typing import Optional

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from analyzers.base_analyzer import DetectedTheme, AnalysisResult
from mappers.stock_mapper import MappedStock
from config import SCORE_WEIGHTS, get_star

logger = logging.getLogger(__name__)


@dataclass
class RankedStock:
    stock: MappedStock
    score: float        # 0-100
    stars: int          # 1-5
    score_detail: dict  # 各スコア内訳
    reason: str         # 表示用の根拠テキスト


def rank_stocks(
    mapped_stocks: list[MappedStock],
    analysis: AnalysisResult,
    max_results: int = 50,
) -> list[RankedStock]:
    """
    銘柄にスコアを付け、ランク順に並べて返す

    Args:
        mapped_stocks: mappers.stock_mapper.map_stocks() の結果
        analysis:      analyzers が生成した AnalysisResult
        max_results:   上位何件を返すか
    """
    # テーマ名 → DetectedTheme の辞書
    theme_map: dict[str, DetectedTheme] = {t.name: t for t in analysis.themes}

    # テーマ順位（1位スタート）
    theme_rank: dict[str, int] = {t.name: i+1 for i, t in enumerate(analysis.themes)}
    total_themes = max(len(analysis.themes), 1)

    ranked: list[RankedStock] = []

    for ms in mapped_stocks:
        theme = theme_map.get(ms.theme_name)
        if theme is None:
            continue

        rank = theme_rank.get(ms.theme_name, total_themes)

        # --- 各シグナルのスコア計算 ---
        # テーマ関連度 (0-50)
        relevance = theme.score / 100 * SCORE_WEIGHTS["theme_relevance"]

        # 言及数 (0-20): 記事5件以上で満点
        mention_raw = min(theme.article_count / 5, 1.0)
        mention = mention_raw * SCORE_WEIGHTS["mention_count"]

        # センチメント (0-20): -1〜+1 → 0〜1 にスケール
        sent_norm = (theme.sentiment + 1) / 2
        sentiment = sent_norm * SCORE_WEIGHTS["sentiment"]

        # テーマ勢い (0-10): 上位テーマほど高得点
        momentum_norm = 1 - (rank - 1) / total_themes
        momentum = momentum_norm * SCORE_WEIGHTS["theme_momentum"]

        total = round(relevance + mention + sentiment + momentum, 1)
        stars = get_star(total)

        detail = {
            "theme_relevance": round(relevance, 1),
            "mention_count":   round(mention, 1),
            "sentiment":       round(sentiment, 1),
            "theme_momentum":  round(momentum, 1),
        }

        reason = _build_reason(ms, theme, stars)

        ranked.append(RankedStock(
            stock        = ms,
            score        = total,
            stars        = stars,
            score_detail = detail,
            reason       = reason,
        ))

    ranked.sort(key=lambda r: r.score, reverse=True)
    return ranked[:max_results]


def _build_reason(ms: MappedStock, theme: DetectedTheme, stars: int) -> str:
    sent_label = (
        "ポジティブ" if theme.sentiment > 0.2
        else "ネガティブ" if theme.sentiment < -0.2
        else "中立"
    )
    kw_str = "・".join(theme.keywords_found[:3])
    base = (
        f"テーマ「{theme.name}」({theme.article_count}件の記事) — "
        f"センチメント:{sent_label} — キーワード:{kw_str}"
    )
    if theme.reason:
        base += f"\n{theme.reason}"
    return base
