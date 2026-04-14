"""
HTML レポート生成モジュール
Bootstrap 5 を CDN から読み込み、見やすいレポートを生成する
"""
import os
import logging
from datetime import datetime
from collections import defaultdict

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from rankers.ranker import RankedStock
from analyzers.base_analyzer import AnalysisResult
from config import OUTPUT_DIR, REPORT_FILENAME

logger = logging.getLogger(__name__)

MARKET_BADGE_CLASS = {
    "P": "badge bg-primary",
    "S": "badge bg-success",
    "G": "badge bg-warning text-dark",
    "?": "badge bg-secondary",
}

STAR_COLOR = {5: "#ff6b00", 4: "#ff9500", 3: "#ffc107", 2: "#6c757d", 1: "#adb5bd"}


def _stars_html(n: int) -> str:
    filled  = "★" * n
    empty   = "☆" * (5 - n)
    color   = STAR_COLOR.get(n, "#adb5bd")
    return f'<span style="color:{color};font-size:1.2em;">{filled}{empty}</span>'


def _sentiment_bar(sentiment: float) -> str:
    """センチメント -1〜+1 をプログレスバーで表示"""
    pct = int((sentiment + 1) / 2 * 100)
    color = "bg-success" if sentiment > 0.2 else "bg-danger" if sentiment < -0.2 else "bg-secondary"
    label = f"{sentiment:+.2f}"
    return (
        f'<div class="progress" style="height:8px;" title="センチメント:{label}">'
        f'<div class="progress-bar {color}" style="width:{pct}%"></div></div>'
        f'<small class="text-muted">{label}</small>'
    )


def generate_report(
    ranked_stocks: list[RankedStock],
    analysis: AnalysisResult,
    output_path: str | None = None,
) -> str:
    """
    HTML レポートを生成してファイルに保存する

    Returns:
        保存先パス
    """
    if output_path is None:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        output_path = os.path.join(OUTPUT_DIR, REPORT_FILENAME)

    now_str = datetime.now().strftime("%Y年%m月%d日 %H:%M")
    mode_label = "Claude AI 高精度モード" if analysis.mode == "claude" else "ルールベースモード"
    mode_badge = "bg-info" if analysis.mode == "claude" else "bg-secondary"

    # テーマ別にグルーピング
    by_theme: dict[str, list[RankedStock]] = defaultdict(list)
    for rs in ranked_stocks:
        by_theme[rs.stock.theme_name].append(rs)

    # --- テーマサマリーセクション ---
    theme_cards_html = ""
    for theme in analysis.themes[:8]:
        kw_badges = " ".join(
            f'<span class="badge bg-light text-dark border">{kw}</span>'
            for kw in theme.keywords_found[:6]
        )
        theme_cards_html += f"""
        <div class="col-md-6 col-lg-4 mb-3">
          <div class="card h-100 shadow-sm">
            <div class="card-body">
              <h6 class="card-title fw-bold">{theme.name}
                <span class="badge bg-primary ms-1">{theme.score:.0f}pt</span>
              </h6>
              <div class="mb-1">{_sentiment_bar(theme.sentiment)}</div>
              <small class="text-muted d-block mb-2">記事数: {theme.article_count}件</small>
              <div>{kw_badges}</div>
              {f'<p class="card-text mt-2 small text-secondary">{theme.reason}</p>' if theme.reason else ''}
            </div>
          </div>
        </div>
        """

    # --- 銘柄ランキングセクション ---
    stock_rows_html = ""
    for rank_pos, rs in enumerate(ranked_stocks, 1):
        ms = rs.stock
        badge_class = MARKET_BADGE_CLASS.get(ms.market_badge, "badge bg-secondary")
        detail = rs.score_detail
        tooltip = (
            f"テーマ関連度:{detail['theme_relevance']}pt / "
            f"記事数:{detail['mention_count']}pt / "
            f"センチメント:{detail['sentiment']}pt / "
            f"勢い:{detail['theme_momentum']}pt"
        )
        stock_rows_html += f"""
        <tr>
          <td class="text-center fw-bold">{rank_pos}</td>
          <td>
            <span class="{badge_class} me-1">{ms.market_badge}</span>
            <strong>{ms.code}</strong> {ms.name}
          </td>
          <td><small class="text-muted">{ms.market_name}</small></td>
          <td><small class="text-muted">{ms.sector33_name}</small></td>
          <td>{_stars_html(rs.stars)}</td>
          <td class="text-center" title="{tooltip}">
            <span class="badge bg-dark">{rs.score:.1f}</span>
          </td>
          <td><small class="text-secondary">{ms.theme_name}</small></td>
        </tr>
        """

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>トレンド株銘柄レポート {now_str}</title>
  <link rel="stylesheet"
    href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
  <style>
    body {{ font-family: 'Meiryo', 'Yu Gothic', sans-serif; background:#f8f9fa; }}
    .hero {{ background: linear-gradient(135deg,#1a1a2e,#16213e); color:#fff; padding:2rem; }}
    th {{ background:#343a40; color:#fff; }}
    tr:hover {{ background:#f0f4ff; }}
  </style>
</head>
<body>

<div class="hero mb-4">
  <div class="container">
    <h1 class="h3 mb-1">📈 トレンド株銘柄レポート</h1>
    <p class="mb-0 opacity-75">
      生成日時: {now_str} &nbsp;|&nbsp;
      <span class="badge {mode_badge}">{mode_label}</span>
    </p>
  </div>
</div>

<div class="container">

  <!-- テーマサマリー -->
  <h2 class="h5 mb-3 border-bottom pb-2">🔍 検知されたトレンドテーマ</h2>
  <div class="row">{theme_cards_html}</div>

  <!-- 銘柄ランキング -->
  <h2 class="h5 mb-3 border-bottom pb-2 mt-4">🏆 関連銘柄ランキング（上位{len(ranked_stocks)}社）</h2>
  <div class="table-responsive">
    <table class="table table-hover table-sm align-middle">
      <thead>
        <tr>
          <th style="width:40px">#</th>
          <th>銘柄</th>
          <th>市場</th>
          <th>業種</th>
          <th>評価</th>
          <th style="width:60px">スコア</th>
          <th>テーマ</th>
        </tr>
      </thead>
      <tbody>
        {stock_rows_html}
      </tbody>
    </table>
  </div>

  <!-- 凡例 -->
  <div class="card mt-4 mb-5 border-0 bg-light">
    <div class="card-body small text-muted">
      <strong>市場区分:</strong>
      <span class="badge bg-primary">P</span> プライム &nbsp;
      <span class="badge bg-success">S</span> スタンダード &nbsp;
      <span class="badge bg-warning text-dark">G</span> グロース &nbsp;|&nbsp;
      <strong>スコア:</strong> スコアにカーソルを合わせると内訳を表示
    </div>
  </div>

</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info(f"レポート生成完了: {output_path}")
    return output_path
