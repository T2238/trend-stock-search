"""
アナライザー基底クラス
Claude API版とルールベース版は共通インターフェースを持つ
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class DetectedSubTheme:
    name: str               # 小テーマ名
    score: float            # 強度 0-100
    article_count: int
    keywords_found: list[str]
    is_dynamic: bool = False  # True = 動的検知（定義外）


@dataclass
class DetectedTheme:
    name: str                         # 大テーマ名
    score: float                      # 強度 0-100（ソースランク重み込み）
    raw_score: float                  # ソースランク重み前の生スコア
    article_count: int
    sentiment: float                  # -1.0 〜 +1.0
    keywords_found: list[str]
    sub_themes: list[DetectedSubTheme] = field(default_factory=list)
    reason: str = ""
    top_source_rank: int = 3          # 最高ソースランク（どのメディアに載ったか）
    rank_breakdown: dict = field(default_factory=dict)  # {5: 3, 4: 7, 3: 12} ランク別記事数


@dataclass
class AnalysisResult:
    themes: list[DetectedTheme] = field(default_factory=list)
    mode: str = "rule"
    analyzed_at: str = ""


class BaseAnalyzer(ABC):
    @abstractmethod
    def analyze(self, articles) -> AnalysisResult:
        """
        ニュース記事リストからトレンドテーマを抽出する

        Args:
            articles: collectors.news_collector.Article のリスト

        Returns:
            AnalysisResult
        """
        ...
