"""
ルールベースアナライザー（Claude API不要）
キーワードマッチングによりテーマを検知し、センチメントを判定する
"""
import re
import logging
from datetime import datetime, timezone, timedelta

from .base_analyzer import BaseAnalyzer, DetectedTheme, AnalysisResult

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from data.themes import INVESTMENT_THEMES, POSITIVE_WORDS, NEGATIVE_WORDS

logger = logging.getLogger(__name__)


class RuleAnalyzer(BaseAnalyzer):
    def __init__(self, hours_lookback: int = 48):
        """
        Args:
            hours_lookback: 何時間前までの記事を対象にするか
        """
        self.hours_lookback = hours_lookback

    def analyze(self, articles) -> AnalysisResult:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.hours_lookback)
        recent = [a for a in articles if a.published >= cutoff] or articles

        theme_hits: dict[str, list] = {name: [] for name in INVESTMENT_THEMES}

        for article in recent:
            text = article.text
            for theme_name, theme_def in INVESTMENT_THEMES.items():
                matched_kws = [kw for kw in theme_def["keywords"] if kw in text]
                if matched_kws:
                    theme_hits[theme_name].append((article, matched_kws))

        detected: list[DetectedTheme] = []
        for theme_name, hits in theme_hits.items():
            if not hits:
                continue

            theme_def = INVESTMENT_THEMES[theme_name]
            article_count = len(hits)
            all_kws = []
            for _, kws in hits:
                all_kws.extend(kws)
            unique_kws = list(dict.fromkeys(all_kws))  # 順序を保ちつつ重複除去

            # センチメント計算
            sentiment = self._calc_sentiment([a for a, _ in hits])

            # テーマスコア: 記事数 × ユニークキーワード数 × 重み
            raw_score = article_count * len(unique_kws) * theme_def.get("weight", 1.0)

            detected.append(DetectedTheme(
                name          = theme_name,
                score         = raw_score,
                article_count = article_count,
                sentiment     = sentiment,
                keywords_found = unique_kws[:10],
                reason        = self._build_reason(theme_name, hits, sentiment),
            ))

        # スコアを 0-100 に正規化
        if detected:
            max_score = max(d.score for d in detected)
            if max_score > 0:
                for d in detected:
                    d.score = round(d.score / max_score * 100, 1)

        detected.sort(key=lambda d: d.score, reverse=True)

        return AnalysisResult(
            themes      = detected,
            mode        = "rule",
            analyzed_at = datetime.now().strftime("%Y-%m-%d %H:%M"),
        )

    def _calc_sentiment(self, articles) -> float:
        pos = neg = 0
        for article in articles:
            text = article.text
            pos += sum(1 for w in POSITIVE_WORDS if w in text)
            neg += sum(1 for w in NEGATIVE_WORDS if w in text)
        total = pos + neg
        if total == 0:
            return 0.0
        return round((pos - neg) / total, 2)

    def _build_reason(self, theme_name: str, hits, sentiment: float) -> str:
        article_count = len(hits)
        kw_sample = list(dict.fromkeys(
            kw for _, kws in hits for kw in kws
        ))[:5]
        sent_label = (
            "ポジティブな報道が中心" if sentiment > 0.2
            else "ネガティブな報道が目立つ" if sentiment < -0.2
            else "センチメントは中立的"
        )
        return (
            f"直近 {article_count} 件の記事でキーワード「{'・'.join(kw_sample)}」が検出。"
            f"{sent_label}。"
        )
