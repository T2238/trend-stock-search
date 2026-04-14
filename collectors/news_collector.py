"""
ニュース収集モジュール
RSS フィードから記事を取得し、統一フォーマットに変換する
source_rank (1〜5) をスコアリングの重みに使用
"""
import time
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field

import feedparser
from bs4 import BeautifulSoup

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import RSS_FEEDS, MAX_ARTICLES_PER_FEED

logger = logging.getLogger(__name__)


@dataclass
class Article:
    title: str
    summary: str
    url: str
    published: datetime
    source: str
    source_rank: int = 3      # 1〜5（情報源の信頼度・重要度）
    full_text: str = ""

    @property
    def text(self) -> str:
        parts = [self.title]
        if self.summary:
            parts.append(self.summary)
        if self.full_text:
            parts.append(self.full_text)
        return " ".join(parts)


def _parse_date(entry) -> datetime:
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def _clean_html(raw: str) -> str:
    soup = BeautifulSoup(raw, "lxml")
    return soup.get_text(separator=" ", strip=True)


def _fetch_feed(url: str, source: str, rank: int, max_articles: int) -> list[Article]:
    articles = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:max_articles]:
            title   = _clean_html(getattr(entry, "title",   "") or "")
            summary = _clean_html(getattr(entry, "summary", "") or "")
            link    = getattr(entry, "link", "") or ""

            articles.append(Article(
                title       = title,
                summary     = summary,
                url         = link,
                published   = _parse_date(entry),
                source      = source,
                source_rank = rank,
            ))
    except Exception as e:
        logger.warning(f"フィード取得失敗 [{source}]: {e}")
    return articles


def collect_news(
    feeds: list[tuple[str, str, int]] | None = None,
    max_per_feed: int = MAX_ARTICLES_PER_FEED,
) -> list[Article]:
    """
    全フィードからニュースを収集して返す

    Returns:
        Article のリスト（重複URL除去済み）
    """
    if feeds is None:
        feeds = RSS_FEEDS

    all_articles: list[Article] = []
    seen_urls: set[str] = set()

    for url, source, rank in feeds:
        logger.info(f"収集中 [ランク{rank}]: {source}")
        arts = _fetch_feed(url, source, rank, max_per_feed)
        for art in arts:
            if art.url not in seen_urls:
                seen_urls.add(art.url)
                all_articles.append(art)
        time.sleep(0.5)

    # ランク降順でソート（高信頼度記事を先頭に）
    all_articles.sort(key=lambda a: a.source_rank, reverse=True)
    logger.info(f"収集完了: 計 {len(all_articles)} 記事")
    return all_articles


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    articles = collect_news()
    for a in articles[:5]:
        print(f"[ランク{a.source_rank}][{a.source}] {a.title}")
