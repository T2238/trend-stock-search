"""
トレンド株銘柄サーチ — エントリーポイント

使い方:
  python main.py                     # 通常実行
  python main.py --top-themes 3      # 上位3テーマのみ
  python main.py --max-stocks 30     # 最大30銘柄
  python main.py --hours 24          # 過去24時間のニュースのみ対象
  python main.py --output report.html

Claude API が .env に設定されていれば自動的に高精度モードで動作する。
"""
import argparse
import logging
import os
import sys
import webbrowser

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(__file__))

from config import USE_CLAUDE_API, CLAUDE_API_KEY
from collectors.news_collector import collect_news
from collectors.sns_collector import collect_sns_trends
from data.stock_db import load_stocks
from mappers.stock_mapper import map_stocks
from rankers.ranker import rank_stocks
from reporters.reporter import generate_report


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level  = level,
        format = "%(asctime)s %(levelname)s %(message)s",
        datefmt= "%H:%M:%S",
    )


def _get_analyzer(hours: int):
    if USE_CLAUDE_API:
        logging.getLogger(__name__).info("Claude API モードで起動")
        from analyzers.claude_analyzer import ClaudeAnalyzer
        return ClaudeAnalyzer(hours_lookback=hours)
    else:
        logging.getLogger(__name__).info("ルールベースモードで起動 (CLAUDE_API_KEY 未設定)")
        from analyzers.rule_analyzer import RuleAnalyzer
        return RuleAnalyzer(hours_lookback=hours)


def main():
    parser = argparse.ArgumentParser(description="トレンド株銘柄サーチ")
    parser.add_argument("--top-themes",  type=int, default=5,    help="対象テーマ数 (default:5)")
    parser.add_argument("--max-stocks",  type=int, default=50,   help="最大銘柄数 (default:50)")
    parser.add_argument("--hours",       type=int, default=48,   help="対象時間範囲(時間) (default:48)")
    parser.add_argument("--output",      type=str, default=None, help="出力ファイルパス")
    parser.add_argument("--no-browser",  action="store_true",    help="ブラウザを自動で開かない")
    parser.add_argument("--no-sns",      action="store_true",    help="SNSトレンド収集をスキップ")
    parser.add_argument("--verbose",     action="store_true",    help="詳細ログ")
    args = parser.parse_args()

    _setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    # 1. ニュース収集
    logger.info("=" * 50)
    logger.info("STEP 1/4 ニュース収集")
    articles = collect_news()
    if not articles:
        logger.error("記事を取得できませんでした。ネット接続を確認してください。")
        sys.exit(1)

    # SNS トレンド（X・Googleトレンド）を追加
    if not args.no_sns:
        sns_articles = collect_sns_trends()
        articles.extend(sns_articles)
        logger.info(f"  → SNS: {len(sns_articles)} ワード追加")

    logger.info(f"  → 合計 {len(articles)} 記事/ワード")

    # 2. テーマ検知
    logger.info("STEP 2/4 テーマ検知")
    analyzer = _get_analyzer(args.hours)
    analysis = analyzer.analyze(articles)
    logger.info(f"  → {len(analysis.themes)} テーマ検知 (モード: {analysis.mode})")
    for i, t in enumerate(analysis.themes[:args.top_themes], 1):
        logger.info(f"    {i}. {t.name} ({t.score:.0f}pt, {t.article_count}件)")

    # 3. 銘柄マッピング
    logger.info("STEP 3/4 銘柄マッピング")
    stock_df = load_stocks()
    mapped = map_stocks(
        themes          = analysis.themes,
        stock_df        = stock_df,
        top_themes      = args.top_themes,
        max_stocks_per_theme = args.max_stocks // max(args.top_themes, 1) + 10,
    )
    logger.info(f"  → {len(mapped)} 銘柄マッピング完了")

    # 4. ランク付け
    logger.info("STEP 4/4 ランク付け")
    ranked = rank_stocks(mapped, analysis, max_results=args.max_stocks)
    logger.info(f"  → 上位 {len(ranked)} 銘柄")

    # コンソールプレビュー（上位10件）
    logger.info("=" * 50)
    print(f"\n【トレンド銘柄 TOP10】({analysis.analyzed_at} / {analysis.mode}モード)")
    print("-" * 60)
    for i, rs in enumerate(ranked[:10], 1):
        ms = rs.stock
        stars = "★" * rs.stars + "☆" * (5 - rs.stars)
        print(f"{i:2}. {stars} [{ms.market_badge}] {ms.code} {ms.name:<20} "
              f"{rs.score:5.1f}pt  {ms.theme_name}")

    # HTMLレポート生成
    path = generate_report(ranked, analysis, output_path=args.output)
    print(f"\nレポート: {path}")

    if not args.no_browser:
        webbrowser.open(f"file:///{path.replace(os.sep, '/')}")


if __name__ == "__main__":
    main()
