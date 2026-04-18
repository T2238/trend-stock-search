"""
設定モジュール
Claude API キーがあれば高精度モード、なければルールベースモードで動作する
"""
import os
from dotenv import load_dotenv

load_dotenv()

# --- Claude API ---
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "")
USE_CLAUDE_API = bool(CLAUDE_API_KEY)
CLAUDE_MODEL = "claude-sonnet-4-6"

# --- J-Quants API V2 (銘柄リスト取得用) ---
JQUANTS_API_KEY = os.getenv("JQUANTS_API_KEY", "")

# --- GNews API (過去記事取得用) ---
# https://gnews.io で無料登録（100リクエスト/日）
GNEWS_API_KEY = os.getenv("GNEWS_API_KEY", "")

# --- 履歴保存 ---
STORAGE_DIR = os.path.join(os.path.dirname(__file__), "storage", "history")
HISTORY_KEEP_DAYS = 90  # 何日分保持するか

# --- 株価取得 ---
# yfinance: 東証銘柄は "7203.T" 形式
PRICE_BENCHMARK_TICKER = "1306.T"   # TOPIX ETF（ベンチマーク）
PRICE_RETURN_DAYS = [1, 5, 20]      # リターン計算日数
PRICE_TOP_N_STOCKS = 30             # 上位何銘柄の株価を取得するか

# --- ニュース収集（情報源ランク付き）---
# ランク 5: 一次金融メディア（スコア重み 2.0倍）
# ランク 4: 大手メディア・経済誌（1.5倍）
# ランク 3: 株式専門・ニュース集約（1.0倍）
# ランク 2: 一般ニュース・業界紙（0.7倍）
# ランク 1: SNSトレンド（0.5倍、早期シグナル）

RSS_FEEDS: list[tuple[str, str, int]] = [
    # --- ランク5: 一次金融メディア (rss.wor.jp 経由) ---
    ("https://assets.wor.jp/rss/rdf/nikkei/economy.rdf",
     "日経 経済", 5),
    ("https://assets.wor.jp/rss/rdf/nikkei/news.rdf",
     "日経 総合", 5),
    ("https://assets.wor.jp/rss/rdf/reuters/top.rdf",
     "Reuters Japan", 5),
    ("https://assets.wor.jp/rss/rdf/bloomberg/markets.rdf",
     "Bloomberg マーケット", 5),
    ("https://assets.wor.jp/rss/rdf/bloomberg/finance.rdf",
     "Bloomberg 金融", 5),

    # --- ランク4: 大手メディア・経済誌 ---
    ("https://assets.wor.jp/rss/rdf/nikkei/business.rdf",
     "日経 ビジネス", 4),
    ("https://business.nikkei.com/rss/sns/nb.rdf",
     "日経ビジネス電子版", 4),
    ("https://www3.nhk.or.jp/rss/news/cat5.xml",
     "NHK 経済", 4),
    ("https://toyokeizai.net/list/feed/rss",
     "東洋経済オンライン", 4),
    ("https://diamond.jp/list/feed/rss",
     "ダイヤモンド・オンライン", 4),

    # --- ランク3: 株式専門・ニュース集約 ---
    ("https://news.yahoo.co.jp/rss/topics/business.xml",
     "Yahoo Japan ビジネス", 3),
    ("https://news.google.com/rss/search?q=日本株+株式市場&hl=ja&gl=JP&ceid=JP:ja",
     "Google News 株式", 3),
    ("https://news.google.com/rss/search?q=東証+銘柄+相場&hl=ja&gl=JP&ceid=JP:ja",
     "Google News 東証", 3),
    ("https://news.google.com/rss/search?q=決算+業績+上方修正&hl=ja&gl=JP&ceid=JP:ja",
     "Google News 決算", 3),

    # --- ランク2: 業界・専門メディア ---
    ("https://news.google.com/rss/search?q=半導体+AI+エネルギー&hl=ja&gl=JP&ceid=JP:ja",
     "Google News テック", 2),
    ("https://news.google.com/rss/search?q=防衛+インバウンド+再エネ&hl=ja&gl=JP&ceid=JP:ja",
     "Google News テーマ株", 2),
]

# ソースランク → スコア重み
SOURCE_RANK_WEIGHT: dict[int, float] = {
    5: 2.0,
    4: 1.5,
    3: 1.0,
    2: 0.7,
    1: 0.5,
}

# 1フィードあたりの最大取得記事数
MAX_ARTICLES_PER_FEED = 30

# --- 小テーマ動的検知 ---
# ニュース内で頻出する名詞フレーズを小テーマ候補として自動抽出
DYNAMIC_SUBTHEME_MIN_COUNT = 3    # 何記事以上で小テーマとみなすか
DYNAMIC_SUBTHEME_MAX_WORDS = 10   # 1記事から抽出するフレーズ最大数

# --- 銘柄データ ---
STOCKS_CSV_PATH = os.path.join(os.path.dirname(__file__), "data", "stocks.csv")

# --- 出力 ---
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
REPORT_FILENAME = "trend_report.html"

# --- スコアリング ---
SCORE_WEIGHTS = {
    "theme_relevance": 50,
    "mention_count":   20,
    "sentiment":       20,
    "theme_momentum":  10,
}

STAR_THRESHOLDS = [
    (80, 5),
    (60, 4),
    (40, 3),
    (20, 2),
    (0,  1),
]

def get_star(score: float) -> int:
    for threshold, stars in STAR_THRESHOLDS:
        if score >= threshold:
            return stars
    return 1
