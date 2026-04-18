"""
GNews API コレクター（過去記事取得）

GNews 無料プラン:
  - 100リクエスト / 日
  - 過去30日分の記事
  - 最大10件 / リクエスト

使い方:
  articles = fetch_gnews_by_date("2026-04-10", "2026-04-11")
  articles = fetch_gnews_range(days=7)   # 過去7日分
"""
import time
import logging
from datetime import datetime, timezone, timedelta

import requests

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from collectors.news_collector import Article
from config import GNEWS_API_KEY

logger = logging.getLogger(__name__)

GNEWS_BASE = "https://gnews.io/api/v4/search"

# 投資テーマに関連する検索クエリ（英語メインでGNews日付フィルタと相性が良い）
GNEWS_QUERIES = [
    "Nikkei OR TSE OR Japan stock market",
    "AI semiconductor Japan OR EV electric vehicle Japan",
    "Japan defense OR inbound tourism Japan OR renewable energy Japan",
    "crude oil Japan OR financial Japan OR fintech Japan",
]


def _fetch_gnews(
    query: str,
    from_dt: datetime,
    to_dt: datetime,
    max_results: int = 10,
) -> list[Article]:
    """GNews API から1クエリ分の記事を取得"""
    if not GNEWS_API_KEY:
        logger.warning("GNEWS_API_KEY が未設定です")
        return []

    params = {
        "q":    query,
        "max":  max_results,
        "from": from_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "to":   to_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "token": GNEWS_API_KEY,
    }

    try:
        resp = requests.get(GNEWS_BASE, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning(f"GNews API エラー [{query[:20]}]: {e}")
        return []

    articles = []
    for item in data.get("articles", []):
        published_str = item.get("publishedAt", "")
        try:
            pub_dt = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
        except Exception:
            pub_dt = datetime.now(timezone.utc)

        articles.append(Article(
            title       = item.get("title", ""),
            summary     = item.get("description", ""),
            url         = item.get("url", ""),
            published   = pub_dt,
            source      = item.get("source", {}).get("name", "GNews"),
            source_rank = 3,  # GNews は中程度の信頼度
        ))

    return articles


def fetch_gnews_by_date(
    date_str: str,
    queries: list[str] | None = None,
) -> list[Article]:
    """
    指定日付（YYYY-MM-DD）のニュースを取得する

    Args:
        date_str: "2026-04-10" 形式
        queries:  検索クエリリスト（省略時はデフォルト）

    Returns:
        Article リスト
    """
    from_dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    to_dt   = from_dt + timedelta(days=1)

    if queries is None:
        queries = GNEWS_QUERIES

    all_articles: list[Article] = []
    seen_urls: set[str] = set()

    for q in queries:
        arts = _fetch_gnews(q, from_dt, to_dt)
        for a in arts:
            if a.url not in seen_urls:
                seen_urls.add(a.url)
                all_articles.append(a)
        time.sleep(0.3)   # レート制限対策

    logger.info(f"GNews [{date_str}]: {len(all_articles)} 記事取得")
    return all_articles


def fetch_gnews_range(
    days: int = 7,
    queries: list[str] | None = None,
) -> dict[str, list[Article]]:
    """
    過去 N 日分のニュースを日付ごとに取得する

    Returns:
        {"2026-04-10": [Article, ...], ...}
    """
    if queries is None:
        queries = GNEWS_QUERIES

    result: dict[str, list[Article]] = {}
    today = datetime.now(timezone.utc).date()

    for i in range(1, days + 1):
        date = today - timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")
        result[date_str] = fetch_gnews_by_date(date_str, queries)
        time.sleep(0.5)

    return result
