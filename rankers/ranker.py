"""
スコアリング・ランク付けモジュール（多テーマ対応版）

スコア計算式:
  theme_contribution[i] = theme_score[i] × stock_weight[i]
  weighted_sum           = Σ theme_contribution[i]
  mention_boost          = 1.0 + 0.2 × tanh(news_mention_score)
  raw_score              = weighted_sum × mention_boost

  final_score (0-100)    = normalize(raw_score)

星ランク:
  ★★★★★ 80-100
  ★★★★  60-79
  ★★★   40-59
  ★★    20-39
  ★     0-19
"""
import math
import logging
from dataclasses import dataclass, field

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from analyzers.base_analyzer import DetectedTheme, AnalysisResult
from mappers.stock_mapper import MappedStock
from config import get_star

logger = logging.getLogger(__name__)


@dataclass
class RankedStock:
    stock: MappedStock
    score: float                          # 0-100 最終スコア
    stars: int                            # 1-5
    theme_contributions: dict[str, float] # theme_name → 貢献スコア
    primary_theme_score: float            # 主テーマの寄与
    mention_boost: float                  # ニュース言及ブースト倍率
    reason: str


def rank_stocks(
    mapped_stocks: list[MappedStock],
    analysis: AnalysisResult,
    max_results: int = 50,
) -> list[RankedStock]:
    """
    銘柄を多テーマ重み付きでスコアリングしてランク順に返す
    """
    theme_score_map: dict[str, float] = {t.name: t.score for t in analysis.themes}
    theme_sentiment: dict[str, float] = {t.name: t.sentiment for t in analysis.themes}

    raw_scores: list[tuple[MappedStock, float, dict]] = []

    for ms in mapped_stocks:
        contributions: dict[str, float] = {}

        for theme_name, weight in ms.theme_weights.items():
            t_score = theme_score_map.get(theme_name, 0.0)
            if t_score <= 0:
                continue
            # センチメント補正: -1〜+1 → 0.7〜1.3
            sent    = theme_sentiment.get(theme_name, 0.0)
            sent_mult = 1.0 + sent * 0.3

            contributions[theme_name] = t_score * weight * sent_mult

        if not contributions:
            continue

        # 合計スコア
        weighted_sum = sum(contributions.values())

        # ニュース言及ブースト（tanh で上限を設ける）
        mention_boost = 1.0 + 0.2 * math.tanh(ms.news_mention_score)

        raw = weighted_sum * mention_boost
        raw_scores.append((ms, raw, contributions, mention_boost))

    if not raw_scores:
        return []

    # 0-100 に正規化
    max_raw = max(r[1] for r in raw_scores) or 1.0
    ranked: list[RankedStock] = []

    for ms, raw, contributions, mb in raw_scores:
        score = round(raw / max_raw * 100, 1)
        stars = get_star(score)

        # 主テーマ（最大寄与テーマ）
        primary_contrib = max(contributions.values()) if contributions else 0.0

        ranked.append(RankedStock(
            stock                = ms,
            score                = score,
            stars                = stars,
            theme_contributions  = {k: round(v / max_raw * 100, 1) for k, v in contributions.items()},
            primary_theme_score  = round(primary_contrib / max_raw * 100, 1),
            mention_boost        = round(mb, 3),
            reason               = _build_reason(ms, contributions, theme_score_map, mb),
        ))

    ranked.sort(key=lambda r: r.score, reverse=True)
    return ranked[:max_results]


def _build_reason(
    ms: MappedStock,
    contributions: dict[str, float],
    theme_score_map: dict[str, float],
    mention_boost: float,
) -> str:
    # 寄与上位2テーマを説明
    top = sorted(contributions.items(), key=lambda x: x[1], reverse=True)[:2]
    theme_parts = [f"「{t}」(テーマ強度{theme_score_map.get(t, 0):.0f}pt×重み{ms.theme_weights.get(t, 1):.1f})"
                   for t, _ in top]
    base = "、".join(theme_parts)

    boost_note = ""
    if mention_boost > 1.05:
        boost_note = f" ＋ニュース直接言及ブースト×{mention_boost:.2f}"

    sub_note = ""
    if ms.sub_themes_hit:
        sub_note = f" | 小テーマ: {' / '.join(ms.sub_themes_hit[:3])}"

    return f"{base}{boost_note}{sub_note}"
