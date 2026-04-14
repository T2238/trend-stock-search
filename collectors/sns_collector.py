"""
SNS トレンドワード収集モジュール（ランク1）

X (Twitter) の日本トレンドを trends24.in から取得する。
APIキー不要・無料でアクセス可能な公開データを使用。

Instagram はAPI制限が厳しいため、代わりに
Google Trends の急上昇ワードも取得する。
"""
import re
import time
import logging
from datetime import datetime, timezone
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from collectors.news_collector import Article

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def fetch_x_trends_japan() -> list[Article]:
    """
    trends24.in/japan/ から X (Twitter) 日本トレンドを取得する
    各トレンドワードを Article として返す（source_rank=1）
    """
    url = "https://trends24.in/japan/"
    articles = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        # trends24 のトレンドリスト: ol.trend-card__list > li > a
        trend_items = soup.select("ol.trend-card__list li a")
        if not trend_items:
            # フォールバック: 別セレクター
            trend_items = soup.select(".trend-card li a")

        now = datetime.now(timezone.utc)
        seen = set()
        for item in trend_items[:30]:
            word = item.get_text(strip=True)
            if not word or word in seen:
                continue
            seen.add(word)
            # ハッシュタグ・数字のみは除外
            if re.match(r"^[#＃]?\d+$", word):
                continue

            articles.append(Article(
                title       = f"【Xトレンド】{word}",
                summary     = f"X(Twitter)日本トレンドワード: {word}",
                url         = f"https://twitter.com/search?q={requests.utils.quote(word)}",
                published   = now,
                source      = "X (Twitter) トレンド",
                source_rank = 1,
            ))

        logger.info(f"X トレンド取得: {len(articles)} ワード")
    except Exception as e:
        logger.warning(f"X トレンド取得失敗: {e}")
    return articles


def fetch_google_trends_japan() -> list[Article]:
    """
    Google Trends の日本急上昇ワードを RSS で取得する（source_rank=1）
    """
    url = "https://trends.google.com/trends/trendingsearches/daily/rss?geo=JP"
    articles = []
    try:
        import feedparser
        feed = feedparser.parse(url)
        now = datetime.now(timezone.utc)

        for entry in feed.entries[:20]:
            title = getattr(entry, "title", "") or ""
            if not title:
                continue
            # approx_traffic があれば付加
            traffic = ""
            if hasattr(entry, "ht_approx_traffic"):
                traffic = f"（検索数: {entry.ht_approx_traffic}）"

            articles.append(Article(
                title       = f"【Googleトレンド】{title}{traffic}",
                summary     = f"Google急上昇ワード(日本): {title}",
                url         = getattr(entry, "link", ""),
                published   = now,
                source      = "Google トレンド",
                source_rank = 1,
            ))

        logger.info(f"Google トレンド取得: {len(articles)} ワード")
    except Exception as e:
        logger.warning(f"Google トレンド取得失敗: {e}")
    return articles


def collect_sns_trends() -> list[Article]:
    """X トレンドと Google トレンドをまとめて返す"""
    articles = []
    articles.extend(fetch_x_trends_japan())
    time.sleep(1)
    articles.extend(fetch_google_trends_japan())
    return articles


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    arts = collect_sns_trends()
    for a in arts[:10]:
        print(f"[{a.source}] {a.title}")
