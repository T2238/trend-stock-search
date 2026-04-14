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

# --- J-Quants API (銘柄リスト取得用) ---
# 2025年12月22日以降登録ユーザーは V2 API (APIキー方式)
JQUANTS_API_KEY = os.getenv("JQUANTS_API_KEY", "")

# --- ニュース収集 ---
RSS_FEEDS = [
    ("https://news.yahoo.co.jp/rss/topics/business.xml",   "Yahoo Japan ビジネス"),
    ("https://www3.nhk.or.jp/rss/news/cat5.xml",           "NHK 経済"),
    ("https://feeds.reuters.com/reuters/JPBusinessNews",   "Reuters Japan"),
    ("https://news.google.com/rss/search?q=日本株+株式市場&hl=ja&gl=JP&ceid=JP:ja", "Google News 株式"),
    ("https://news.google.com/rss/search?q=東証+上場&hl=ja&gl=JP&ceid=JP:ja",       "Google News 東証"),
]

# 1フィードあたりの最大取得記事数
MAX_ARTICLES_PER_FEED = 30

# --- 銘柄データ ---
STOCKS_CSV_PATH = os.path.join(os.path.dirname(__file__), "data", "stocks.csv")

# --- 出力 ---
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
REPORT_FILENAME = "trend_report.html"

# --- スコアリング ---
# 各シグナルの重み (合計100点満点)
SCORE_WEIGHTS = {
    "theme_relevance": 50,   # テーマとの関連度
    "mention_count":   20,   # ニュース言及数
    "sentiment":       20,   # センチメント（ポジティブ/ネガティブ）
    "theme_momentum":  10,   # テーマのトレンド勢い
}

# 星ランク閾値
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
