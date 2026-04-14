"""
ニュース収集モジュール
RSS フィードから記事を取得し、統一フォーマットに変換する
"""
import re
import time
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field

import feedparser
import requests
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
    full_text: str = ""

    @property
    def text(self) -> str:
        """タイトル + サマリー + 本文 を結合したテキスト"""
        parts = [self.title]
        if self.summary:
            parts.append(self.summary)
        if self.full_text:
            parts.append(self.full_text)
        return " ".join(parts)


def _parse_date(entry) -> datetime:
    """feedparser エントリから公開日時を取得"""
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def _clean_html(raw: str) -> str:
    """HTML タグを除去してプレーンテキストに変換"""
    soup = BeautifulSoup(raw, "lxml")
    return soup.get_text(separator=" ", strip=True)


def _fetch_feed(url: str, source: str, max_articles: int) -> list[Article]:
    """単一フィードを取得してArticleリストを返す"""
    articles = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:max_articles]:
            title   = getattr(entry, "title",   "") or ""
            summary = getattr(entry, "summary", "") or ""
            link    = getattr(entry, "link",    "") or ""

            title   = _clean_html(title)
            summary = _clean_html(summary)

            art = Article(
                title     = title,
                summary   = summary,
                url       = link,
                published = _parse_date(entry),
                source    = source,
            )
            articles.append(art)
    except Exception as e:
        logger.warning(f"フィード取得失敗 [{source}]: {e}")
    return articles


def collect_news(feeds: list[tuple[str, str]] | None = None,
                 max_per_feed: int = MAX_ARTICLES_PER_FEED) -> list[Article]:
    """
    全フィードからニュースを収集して返す

    Returns:
        Article のリスト（重複URLを除去済み）
    """
    if feeds is None:
        feeds = RSS_FEEDS

    all_articles: list[Article] = []
    seen_urls: set[str] = set()

    for url, source in feeds:
        logger.info(f"収集中: {source}")
        arts = _fetch_feed(url, source, max_per_feed)
        for art in arts:
            if art.url not in seen_urls:
                seen_urls.add(art.url)
                all_articles.append(art)
        time.sleep(0.5)  # サーバー負荷対策

    logger.info(f"収集完了: 計 {len(all_articles)} 記事")
    return all_articles


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    articles = collect_news()
    for a in articles[:5]:
        print(f"[{a.source}] {a.title}")
        print(f"  {a.published.strftime('%Y-%m-%d %H:%M')} | {a.url}")
        print()
