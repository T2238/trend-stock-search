"""
トレンド株銘柄サーチ — エントリーポイント

通常モード（毎日実行）:
  python main.py

バックテストモード（過去N日遡り）:
  python main.py --backtest --days 7

オプション:
  --top-themes N    対象テーマ数 (default:8)
  --max-stocks N    最大銘柄数 (default:50)
  --hours N         対象時間範囲 (default:48)
  --days N          バックテスト日数 (default:7)
  --no-sns          SNSトレンド収集をスキップ
  --no-price        株価取得をスキップ
  --no-browser      ブラウザを自動で開かない
  --output FILE     出力ファイルパス
  --verbose         詳細ログ
"""
import argparse
import logging
import os
import sys
import webbrowser

sys.path.insert(0, os.path.dirname(__file__))

from config import USE_CLAUDE_API, GNEWS_API_KEY, PRICE_TOP_N_STOCKS, PRICE_RETURN_DAYS
from collectors.news_collector import collect_news
from collectors.sns_collector import collect_sns_trends
from collectors.gnews_collector import fetch_gnews_by_date, fetch_gnews_range
from data.stock_db import load_stocks
from mappers.stock_mapper import map_stocks
from rankers.ranker import rank_stocks
from reporters.reporter import generate_report
from storage.history_manager import (
    save_snapshot, load_snapshots, update_price_returns,
    Snapshot, SnapshotTheme, SnapshotStock,
)
from analysis.trend_watcher import watch_trends
from analysis.price_correlator import fetch_returns, backtest_snapshot, summarize_by_theme


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")


def _get_analyzer(hours: int):
    if USE_CLAUDE_API:
        logging.getLogger(__name__).info("Claude API モードで起動")
        from analyzers.claude_analyzer import ClaudeAnalyzer
        return ClaudeAnalyzer(hours_lookback=hours)
    else:
        from analyzers.rule_analyzer import RuleAnalyzer
        return RuleAnalyzer(hours_lookback=hours)


def _make_snapshot(analysis, ranked_stocks) -> Snapshot:
    """AnalysisResult + RankedStock → Snapshot に変換"""
    from datetime import datetime
    themes = [
        SnapshotTheme(
            name=t.name, score=t.score, article_count=t.article_count,
            sentiment=t.sentiment, top_source_rank=t.top_source_rank,
            sub_theme_names=[s.name for s in t.sub_themes],
        )
        for t in analysis.themes[:10]
    ]
    stocks = [
        SnapshotStock(
            code=rs.stock.code, name=rs.stock.name,
            market_badge=rs.stock.market_badge,
            score=rs.score, stars=rs.stars,
            primary_theme=rs.stock.primary_theme,
            theme_weights=rs.stock.theme_weights,
        )
        for rs in ranked_stocks[:50]
    ]
    now = datetime.now()
    return Snapshot(
        timestamp=now.strftime("%Y-%m-%dT%H:%M:%S"),
        date=now.strftime("%Y-%m-%d"),
        mode=analysis.mode,
        themes=themes,
        ranked_stocks=stocks,
    )


# ─────────────────────────────────────────────────────────────
# 通常モード
# ─────────────────────────────────────────────────────────────
def run_normal(args):
    logger = logging.getLogger(__name__)

    # 1. ニュース収集
    logger.info("=" * 50)
    logger.info("STEP 1/5 ニュース収集")
    articles = collect_news()
    if not articles:
        logger.error("記事を取得できませんでした。")
        sys.exit(1)

    if not args.no_sns:
        sns_articles = collect_sns_trends()
        articles.extend(sns_articles)
        logger.info(f"  → SNS: {len(sns_articles)} ワード追加")

    # GNews 当日分も追加
    if GNEWS_API_KEY:
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        gnews_articles = fetch_gnews_by_date(today)
        articles.extend(gnews_articles)
        logger.info(f"  → GNews: {len(gnews_articles)} 件追加")

    logger.info(f"  → 合計 {len(articles)} 記事/ワード")

    # 2. テーマ検知
    logger.info("STEP 2/5 テーマ検知")
    analyzer = _get_analyzer(args.hours)
    analysis = analyzer.analyze(articles)
    logger.info(f"  → {len(analysis.themes)} テーマ (モード: {analysis.mode})")
    for i, t in enumerate(analysis.themes[:args.top_themes], 1):
        logger.info(f"    {i}. {t.name} ({t.score:.0f}pt, {t.article_count}件)")

    # 3. 銘柄マッピング
    logger.info("STEP 3/5 銘柄マッピング")
    stock_df = load_stocks()
    mapped = map_stocks(
        themes=analysis.themes, stock_df=stock_df,
        articles=articles, top_themes=args.top_themes, max_stocks=args.max_stocks,
    )
    logger.info(f"  → {len(mapped)} 銘柄")

    # 4. ランク付け
    logger.info("STEP 4/5 ランク付け")
    ranked = rank_stocks(mapped, analysis, max_results=args.max_stocks)

    # スナップショット保存
    current_snap = _make_snapshot(analysis, ranked)
    snap_path = save_snapshot(analysis, ranked)

    # トレンド変化検知
    watch_result = watch_trends(current_snap)

    # 5. 株価リターン取得（今日分は翌日以降に意味が出るが現在値との乖離確認用）
    price_data: dict = {}
    if not args.no_price:
        logger.info("STEP 5/5 株価取得")
        top_codes = [rs.stock.code for rs in ranked[:PRICE_TOP_N_STOCKS]]
        returns = fetch_returns(top_codes, current_snap.date, PRICE_RETURN_DAYS)
        # 当日は N日後が未来なので None になる（正常）
        for code, sr in returns.items():
            price_data[code] = {"returns": sr.returns, "excess": sr.excess}
        update_price_returns(snap_path, price_data)
        logger.info(f"  → {len(returns)} 銘柄の株価取得完了")
    else:
        logger.info("STEP 5/5 スキップ (--no-price)")

    # コンソールプレビュー
    _print_preview(ranked, analysis, watch_result)

    # HTMLレポート生成
    path = generate_report(ranked, analysis, watch_result, price_data, args.output)
    print(f"\nレポート: {path}")
    if not args.no_browser:
        webbrowser.open(f"file:///{path.replace(os.sep, '/')}")


# ─────────────────────────────────────────────────────────────
# バックテストモード
# ─────────────────────────────────────────────────────────────
def run_backtest(args):
    logger = logging.getLogger(__name__)
    logger.info(f"バックテストモード: 過去{args.days}日分")

    if not GNEWS_API_KEY:
        logger.error("バックテストには GNEWS_API_KEY が必要です")
        sys.exit(1)

    stock_df = load_stocks()
    analyzer = _get_analyzer(args.hours)

    # 日付ごとにニュース取得 → 分析 → スナップショット保存
    logger.info(f"STEP 1 過去ニュース取得（GNews API, {args.days}日分）")
    history_articles = fetch_gnews_range(days=args.days)

    all_snaps = []
    for date_str, day_articles in sorted(history_articles.items()):
        if not day_articles:
            logger.info(f"  [{date_str}] 記事なし、スキップ")
            continue

        logger.info(f"  [{date_str}] {len(day_articles)} 記事 → 分析中...")
        analysis = analyzer.analyze(day_articles)
        if not analysis.themes:
            continue

        mapped = map_stocks(
            themes=analysis.themes, stock_df=stock_df,
            articles=day_articles, top_themes=args.top_themes, max_stocks=args.max_stocks,
        )
        ranked = rank_stocks(mapped, analysis, max_results=args.max_stocks)

        # スナップショット保存（過去日付として）
        snap_path = save_snapshot(analysis, ranked, date_str=date_str)
        snap = _make_snapshot(analysis, ranked)
        snap.date = date_str
        all_snaps.append((date_str, snap, snap_path, ranked))

    logger.info(f"\nSTEP 2 株価リターン計算")
    all_correlation: list = []

    for date_str, snap, snap_path, ranked in all_snaps:
        codes = [rs.stock.code for rs in ranked[:PRICE_TOP_N_STOCKS]]
        returns = fetch_returns(codes, date_str, PRICE_RETURN_DAYS)
        price_data = {c: {"returns": r.returns, "excess": r.excess} for c, r in returns.items()}
        update_price_returns(snap_path, price_data)

        # テーマ別サマリー
        summaries = summarize_by_theme(returns, snap.ranked_stocks, PRICE_RETURN_DAYS)
        all_correlation.append((date_str, summaries))

    # バックテストレポート生成
    path = _generate_backtest_report(all_snaps, all_correlation, args.output)
    print(f"\nバックテストレポート: {path}")
    if not args.no_browser:
        webbrowser.open(f"file:///{path.replace(os.sep, '/')}")


def _print_preview(ranked, analysis, watch_result):
    print(f"\n【トレンド銘柄 TOP10】({analysis.analyzed_at} / {analysis.mode}モード)")
    if watch_result.has_history:
        print(f"  前回比較: {watch_result.prev_date}")
    print("-" * 65)
    for i, rs in enumerate(ranked[:10], 1):
        ms = rs.stock
        stars = "★" * rs.stars + "☆" * (5 - rs.stars)
        theme_str = "/".join(list(rs.theme_contributions.keys())[:2])
        print(f"{i:2}. {stars} [{ms.market_badge}] {ms.code} {ms.name:<18} "
              f"{rs.score:5.1f}pt  {theme_str}")

    if watch_result.has_history and watch_result.new_themes:
        print(f"\n🆕 新規テーマ: {', '.join(watch_result.new_themes)}")
    if watch_result.has_history and watch_result.disappeared_themes:
        print(f"💨 消滅テーマ: {', '.join(watch_result.disappeared_themes)}")


def _generate_backtest_report(all_snaps, all_correlation, output_path=None) -> str:
    """バックテスト専用HTMLレポートを生成"""
    import os
    from config import OUTPUT_DIR
    if output_path is None:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        output_path = os.path.join(OUTPUT_DIR, "backtest_report.html")

    from datetime import datetime
    now_str = datetime.now().strftime("%Y年%m月%d日 %H:%M")

    rows = ""
    for date_str, summaries in sorted(all_correlation, reverse=True):
        for s in summaries[:5]:
            def fmt(v):
                if v is None:
                    return '<span class="text-muted">-</span>'
                color = "text-success" if v > 0 else "text-danger"
                return f'<span class="{color}">{v*100:+.1f}%</span>'
            wr = lambda v: f"{v*100:.0f}%" if v is not None else "-"
            rows += f"""
            <tr>
              <td>{date_str}</td>
              <td>{s.theme_name}</td>
              <td class="text-center">{s.stock_count}</td>
              <td class="text-center">{fmt(s.avg_return.get("1d"))} / {wr(s.win_rate.get("1d"))}</td>
              <td class="text-center">{fmt(s.avg_return.get("5d"))} / {wr(s.win_rate.get("5d"))}</td>
              <td class="text-center">{fmt(s.avg_return.get("20d"))} / {wr(s.win_rate.get("20d"))}</td>
            </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <title>バックテストレポート {now_str}</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
  <style>body{{font-family:'Meiryo',sans-serif;}}</style>
</head>
<body>
<div class="container mt-4">
  <h1 class="h4 mb-1">📊 バックテストレポート</h1>
  <p class="text-muted">{now_str} — テーマ検知日からのTOPIX超過リターン(平均) / 勝率</p>
  <table class="table table-hover table-sm">
    <thead class="table-dark">
      <tr>
        <th>検知日</th><th>テーマ</th><th>銘柄数</th>
        <th class="text-center">1日後 超過/勝率</th>
        <th class="text-center">5日後 超過/勝率</th>
        <th class="text-center">20日後 超過/勝率</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
</div>
</body></html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    return output_path


# ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="トレンド株銘柄サーチ")
    parser.add_argument("--backtest",    action="store_true", help="バックテストモード")
    parser.add_argument("--days",        type=int, default=7,  help="バックテスト日数 (default:7)")
    parser.add_argument("--top-themes",  type=int, default=8,  help="対象テーマ数 (default:8)")
    parser.add_argument("--max-stocks",  type=int, default=50, help="最大銘柄数 (default:50)")
    parser.add_argument("--hours",       type=int, default=48, help="対象時間範囲h (default:48)")
    parser.add_argument("--no-sns",      action="store_true",  help="SNS収集をスキップ")
    parser.add_argument("--no-price",    action="store_true",  help="株価取得をスキップ")
    parser.add_argument("--no-browser",  action="store_true",  help="ブラウザを開かない")
    parser.add_argument("--output",      type=str, default=None, help="出力ファイルパス")
    parser.add_argument("--verbose",     action="store_true",  help="詳細ログ")
    args = parser.parse_args()

    _setup_logging(args.verbose)

    if args.backtest:
        run_backtest(args)
    else:
        run_normal(args)


if __name__ == "__main__":
    main()
