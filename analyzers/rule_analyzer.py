"""
ルールベースアナライザー（Claude API不要）

機能:
  1. 大テーマ × キーワードマッチ
  2. 小テーマ × キーワードマッチ（定義済み）
  3. 動的小テーマ検知（頻出フレーズを自動クラスタリング）
  4. ソースランク重み付き集計
"""
import re
import logging
from collections import Counter
from datetime import datetime, timezone, timedelta

from .base_analyzer import (
    BaseAnalyzer, DetectedTheme, DetectedSubTheme, AnalysisResult
)

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from data.themes import INVESTMENT_THEMES, POSITIVE_WORDS, NEGATIVE_WORDS
from config import SOURCE_RANK_WEIGHT, DYNAMIC_SUBTHEME_MIN_COUNT, DYNAMIC_SUBTHEME_MAX_WORDS

logger = logging.getLogger(__name__)

# 動的小テーマ抽出用: 対象外の汎用語（ストップワード）
_STOP_WORDS = {
    "する", "れる", "ある", "なる", "いる", "こと", "これ", "それ",
    "また", "など", "ため", "もの", "という", "として", "について",
    "において", "による", "から", "まで", "より", "では", "には",
    "日本", "市場", "株式", "投資", "企業", "会社", "業界",
    "昨年", "今年", "来年", "以上", "以下", "前年", "前期",
}

# 動的小テーマ抽出: 候補フレーズの正規表現（2〜8文字の名詞フレーズ）
_PHRASE_RE = re.compile(r"[ぁ-ヶー一-龥Ａ-Ｚａ-ｚA-Za-z0-9]{2,8}")


class RuleAnalyzer(BaseAnalyzer):
    def __init__(self, hours_lookback: int = 48):
        self.hours_lookback = hours_lookback

    def analyze(self, articles) -> AnalysisResult:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.hours_lookback)
        recent = [a for a in articles if a.published >= cutoff] or articles

        # 大テーマ別にヒット記事を収集
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

            # ユニークキーワード
            all_kws: list[str] = []
            for _, kws in hits:
                all_kws.extend(kws)
            unique_kws = list(dict.fromkeys(all_kws))

            # センチメント
            sentiment = self._calc_sentiment([a for a, _ in hits])

            # ソースランク重み付きスコア
            weighted_score = sum(
                SOURCE_RANK_WEIGHT.get(a.source_rank, 1.0) * len(kws)
                for a, kws in hits
            )
            top_rank = max(a.source_rank for a, _ in hits)

            # 小テーマ検知（定義済み）
            sub_themes = self._detect_sub_themes(
                theme_name, theme_def, [a for a, _ in hits]
            )

            # 動的小テーマ検知（定義外の頻出フレーズ）
            dynamic_subs = self._detect_dynamic_sub_themes(
                theme_name, [a for a, _ in hits], sub_themes
            )
            sub_themes.extend(dynamic_subs)

            detected.append(DetectedTheme(
                name           = theme_name,
                score          = weighted_score,
                raw_score      = float(article_count * len(unique_kws)),
                article_count  = article_count,
                sentiment      = sentiment,
                keywords_found = unique_kws[:10],
                sub_themes     = sorted(sub_themes, key=lambda s: s.score, reverse=True),
                top_source_rank= top_rank,
                reason         = self._build_reason(theme_name, hits, sentiment, top_rank),
            ))

        # スコアを 0-100 に正規化
        if detected:
            max_score = max(d.score for d in detected) or 1
            for d in detected:
                d.score = round(d.score / max_score * 100, 1)

        detected.sort(key=lambda d: d.score, reverse=True)

        return AnalysisResult(
            themes      = detected,
            mode        = "rule",
            analyzed_at = datetime.now().strftime("%Y-%m-%d %H:%M"),
        )

    def _detect_sub_themes(
        self,
        theme_name: str,
        theme_def: dict,
        articles,
    ) -> list[DetectedSubTheme]:
        """定義済み小テーマのキーワードマッチ"""
        sub_defs = theme_def.get("sub_themes", {})
        result = []
        for sub_name, sub_def in sub_defs.items():
            sub_kws = sub_def.get("keywords", [])
            matched_arts = []
            matched_kws_all = []
            for art in articles:
                kws = [kw for kw in sub_kws if kw in art.text]
                if kws:
                    matched_arts.append(art)
                    matched_kws_all.extend(kws)
            if not matched_arts:
                continue
            weighted = sum(
                SOURCE_RANK_WEIGHT.get(a.source_rank, 1.0)
                for a in matched_arts
            )
            result.append(DetectedSubTheme(
                name          = sub_name,
                score         = round(weighted * 10, 1),
                article_count = len(matched_arts),
                keywords_found= list(dict.fromkeys(matched_kws_all))[:5],
                is_dynamic    = False,
            ))
        return result

    def _detect_dynamic_sub_themes(
        self,
        theme_name: str,
        articles,
        existing_subs: list[DetectedSubTheme],
    ) -> list[DetectedSubTheme]:
        """
        定義されていないフレーズを頻度分析で小テーマ候補として検知する
        テーマキーワードと共起する固有フレーズを抽出
        """
        existing_kws = {kw for s in existing_subs for kw in s.keywords_found}
        theme_kws = set(INVESTMENT_THEMES[theme_name]["keywords"])

        # 全記事のフレーズカウント
        phrase_counter: Counter = Counter()
        phrase_to_arts: dict[str, list] = {}

        for art in articles:
            phrases = set(_PHRASE_RE.findall(art.text))
            # ストップワード・テーマキーワード・既知KW を除外
            phrases -= _STOP_WORDS
            phrases -= theme_kws
            phrases -= existing_kws
            # 1〜2文字の短すぎるものを除外
            phrases = {p for p in phrases if len(p) >= 3}
            for p in list(phrases)[:DYNAMIC_SUBTHEME_MAX_WORDS]:
                phrase_counter[p] += 1
                phrase_to_arts.setdefault(p, []).append(art)

        # 閾値以上の頻出フレーズを動的小テーマとして採用
        result = []
        for phrase, count in phrase_counter.most_common(5):
            if count < DYNAMIC_SUBTHEME_MIN_COUNT:
                break
            arts = phrase_to_arts[phrase]
            weighted = sum(SOURCE_RANK_WEIGHT.get(a.source_rank, 1.0) for a in arts)
            result.append(DetectedSubTheme(
                name          = f"★{phrase}（急上昇）",
                score         = round(weighted * 8, 1),
                article_count = count,
                keywords_found= [phrase],
                is_dynamic    = True,
            ))

        return result

    def _calc_sentiment(self, articles) -> float:
        pos = neg = 0
        for article in articles:
            text = article.text
            # ソースランクで重み付け
            w = SOURCE_RANK_WEIGHT.get(article.source_rank, 1.0)
            pos += sum(w for word in POSITIVE_WORDS if word in text)
            neg += sum(w for word in NEGATIVE_WORDS if word in text)
        total = pos + neg
        if total == 0:
            return 0.0
        return round((pos - neg) / total, 2)

    def _build_reason(
        self, theme_name: str, hits, sentiment: float, top_rank: int
    ) -> str:
        article_count = len(hits)
        kw_sample = list(dict.fromkeys(kw for _, kws in hits for kw in kws))[:5]
        sent_label = (
            "ポジティブな報道が中心" if sentiment > 0.2
            else "ネガティブな報道が目立つ" if sentiment < -0.2
            else "センチメントは中立的"
        )
        rank_label = {5: "日経・Reuters等", 4: "NHK・経済誌", 3: "株専門サイト等",
                      2: "業界紙等", 1: "SNSトレンド"}.get(top_rank, "各種メディア")
        return (
            f"{article_count}件の記事でキーワード「{'・'.join(kw_sample)}」を検出。"
            f"{sent_label}。最高ランク情報源: {rank_label}(ランク{top_rank})。"
        )
