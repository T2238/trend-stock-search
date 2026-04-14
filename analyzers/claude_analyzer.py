"""
Claude API アナライザー（高精度モード）
APIキーが設定されている場合に使用する。
ルールベースアナライザーと同じインターフェースを実装。
"""
import json
import logging
from datetime import datetime, timezone, timedelta

from .base_analyzer import BaseAnalyzer, DetectedTheme, AnalysisResult

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import CLAUDE_API_KEY, CLAUDE_MODEL
from data.themes import INVESTMENT_THEMES

logger = logging.getLogger(__name__)

ANALYSIS_PROMPT = """\
あなたは日本株式市場の専門アナリストです。
以下のニュース記事リストを読み、今後数週間の日本株市場に影響を与えそうな
投資テーマを抽出してください。

## 判定基準
- 複数の記事で繰り返し言及されているテーマを重視
- 個別企業の話題ではなく、業界横断的なテーマを抽出
- 株価へのポジティブ・ネガティブ両方の影響を評価

## ニュース記事
{articles_text}

## 既存テーマカテゴリ（これ以外の新テーマも可）
{theme_names}

## 出力形式（JSON のみ返すこと）
{{
  "themes": [
    {{
      "name": "テーマ名",
      "score": 0〜100の数値,
      "article_count": 関連記事数,
      "sentiment": -1.0〜1.0,
      "keywords_found": ["キーワード1", ...],
      "reason": "根拠の説明文（2〜3文）"
    }}
  ]
}}
"""


class ClaudeAnalyzer(BaseAnalyzer):
    def __init__(self, hours_lookback: int = 48):
        self.hours_lookback = hours_lookback
        try:
            import anthropic
            self._client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        except ImportError:
            raise RuntimeError("anthropic パッケージが必要です: pip install anthropic")

    def analyze(self, articles) -> AnalysisResult:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.hours_lookback)
        recent = [a for a in articles if a.published >= cutoff] or articles

        # 記事テキストを結合（トークン節約のため各記事を短縮）
        articles_text = self._format_articles(recent[:60])
        theme_names = "\n".join(f"- {name}" for name in INVESTMENT_THEMES)

        prompt = ANALYSIS_PROMPT.format(
            articles_text = articles_text,
            theme_names   = theme_names,
        )

        try:
            response = self._client.messages.create(
                model      = CLAUDE_MODEL,
                max_tokens = 2048,
                system     = "You are a Japanese stock market analyst. Always respond in valid JSON.",
                messages   = [{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()
            # JSONブロックの抽出
            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            data = json.loads(raw)
        except Exception as e:
            logger.error(f"Claude API エラー: {e}")
            # フォールバック: ルールベースで再試行
            from .rule_analyzer import RuleAnalyzer
            logger.warning("ルールベースにフォールバックします")
            return RuleAnalyzer(self.hours_lookback).analyze(articles)

        detected = []
        for t in data.get("themes", []):
            detected.append(DetectedTheme(
                name           = t.get("name", ""),
                score          = float(t.get("score", 0)),
                article_count  = int(t.get("article_count", 0)),
                sentiment      = float(t.get("sentiment", 0)),
                keywords_found = t.get("keywords_found", []),
                reason         = t.get("reason", ""),
            ))

        detected.sort(key=lambda d: d.score, reverse=True)

        return AnalysisResult(
            themes      = detected,
            mode        = "claude",
            analyzed_at = datetime.now().strftime("%Y-%m-%d %H:%M"),
        )

    def _format_articles(self, articles) -> str:
        lines = []
        for i, a in enumerate(articles, 1):
            lines.append(f"{i}. [{a.source}] {a.title}")
            if a.summary:
                # サマリーは先頭100文字のみ
                lines.append(f"   {a.summary[:100]}")
        return "\n".join(lines)
