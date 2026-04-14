"""
アナライザー基底クラス
Claude API版とルールベース版は共通インターフェースを持つ
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class DetectedTheme:
    name: str                     # テーマ名 (e.g. "AI・生成AI")
    score: float                  # テーマの強度 0-100
    article_count: int            # 関連記事数
    sentiment: float              # -1.0(悲観) 〜 +1.0(楽観)
    keywords_found: list[str]     # ヒットしたキーワード
    reason: str = ""              # 根拠の説明文 (Claude API使用時に詳細化)


@dataclass
class AnalysisResult:
    themes: list[DetectedTheme] = field(default_factory=list)
    mode: str = "rule"            # "rule" or "claude"
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
