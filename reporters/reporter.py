"""
HTML レポート生成モジュール
大テーマ → 小テーマ（定義済み＋動的）→ 銘柄ランキング を階層表示
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

SOURCE_RANK_LABEL = {
    5: ("★★★★★", "danger",   "一次金融メディア"),
    4: ("★★★★",  "warning",  "大手・経済誌"),
    3: ("★★★",   "info",     "株専門サイト"),
    2: ("★★",    "secondary","業界・一般紙"),
    1: ("★",     "dark",     "SNSトレンド"),
}


def _stars_html(n: int) -> str:
    color = STAR_COLOR.get(n, "#adb5bd")
    return f'<span style="color:{color};font-size:1.1em;">{"★"*n}{"☆"*(5-n)}</span>'


def _sentiment_bar(sentiment: float) -> str:
    pct   = int((sentiment + 1) / 2 * 100)
    color = "bg-success" if sentiment > 0.2 else "bg-danger" if sentiment < -0.2 else "bg-secondary"
    return (
        f'<div class="progress mb-1" style="height:6px;">'
        f'<div class="progress-bar {color}" style="width:{pct}%"></div></div>'
        f'<small class="text-muted">{sentiment:+.2f}</small>'
    )


def _source_rank_badge(rank: int) -> str:
    stars, color, label = SOURCE_RANK_LABEL.get(rank, ("?", "secondary", "不明"))
    return f'<span class="badge bg-{color}" title="{label}">情報源ランク{rank}</span>'


def _sub_themes_html(sub_themes) -> str:
    if not sub_themes:
        return ""
    items = []
    for s in sub_themes[:6]:
        kw_str = "・".join(s.keywords_found[:3])
        dynamic_badge = '<span class="badge bg-danger ms-1">急上昇</span>' if s.is_dynamic else ""
        items.append(
            f'<span class="badge bg-light text-dark border me-1 mb-1">'
            f'{s.name}{dynamic_badge}'
            f'<small class="text-muted ms-1">({s.article_count}件)</small>'
            f'</span>'
        )
    return '<div class="mt-1">' + "".join(items) + "</div>"


def generate_report(
    ranked_stocks: list[RankedStock],
    analysis: AnalysisResult,
    output_path: str | None = None,
) -> str:
    if output_path is None:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        output_path = os.path.join(OUTPUT_DIR, REPORT_FILENAME)

    now_str    = datetime.now().strftime("%Y年%m月%d日 %H:%M")
    mode_label = "Claude AI 高精度モード" if analysis.mode == "claude" else "ルールベースモード"
    mode_badge = "bg-info" if analysis.mode == "claude" else "bg-secondary"

    # --- テーマカード ---
    theme_cards_html = ""
    for theme in analysis.themes[:9]:
        kw_badges = "".join(
            f'<span class="badge bg-light text-dark border me-1">{kw}</span>'
            for kw in theme.keywords_found[:6]
        )
        sub_html = _sub_themes_html(theme.sub_themes)
        rank_badge = _source_rank_badge(theme.top_source_rank)
        theme_cards_html += f"""
        <div class="col-md-6 col-lg-4 mb-3">
          <div class="card h-100 shadow-sm">
            <div class="card-header d-flex justify-content-between align-items-center py-2">
              <strong>{theme.name}</strong>
              <span class="badge bg-primary">{theme.score:.0f}pt</span>
            </div>
            <div class="card-body py-2">
              <div class="d-flex align-items-center gap-2 mb-1">
                {rank_badge}
                <small class="text-muted">{theme.article_count}件</small>
              </div>
              {_sentiment_bar(theme.sentiment)}
              <div class="mt-1">{kw_badges}</div>
              {sub_html}
              {f'<p class="card-text mt-2 small text-secondary">{theme.reason}</p>' if theme.reason else ''}
            </div>
          </div>
        </div>
        """

    # --- 銘柄テーブル ---
    stock_rows_html = ""
    for rank_pos, rs in enumerate(ranked_stocks, 1):
        ms     = rs.stock
        detail = rs.score_detail
        badge_class = MARKET_BADGE_CLASS.get(ms.market_badge, "badge bg-secondary")
        tooltip = (
            f"関連度:{detail['theme_relevance']}pt / "
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
          <td>
            <small class="text-secondary">{ms.theme_name}</small>
          </td>
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
    body  {{ font-family:'Meiryo','Yu Gothic',sans-serif; background:#f8f9fa; }}
    .hero {{ background:linear-gradient(135deg,#1a1a2e,#16213e); color:#fff; padding:2rem; }}
    th    {{ background:#343a40; color:#fff; position:sticky; top:0; }}
    tr:hover {{ background:#f0f4ff; }}
    .source-legend span {{ display:inline-block; margin-right:1rem; }}
  </style>
</head>
<body>

<div class="hero mb-4">
  <div class="container">
    <h1 class="h3 mb-1">📈 トレンド株銘柄レポート</h1>
    <p class="mb-0 opacity-75">
      生成: {now_str} &nbsp;|&nbsp;
      <span class="badge {mode_badge}">{mode_label}</span>
    </p>
  </div>
</div>

<div class="container">

  <!-- 情報源ランク凡例 -->
  <div class="alert alert-light border small source-legend mb-3 py-2">
    <strong>情報源ランク:</strong>
    <span><span class="badge bg-danger">ランク5</span> 日経・Reuters</span>
    <span><span class="badge bg-warning text-dark">ランク4</span> NHK・経済誌</span>
    <span><span class="badge bg-info">ランク3</span> 株専門・Google News</span>
    <span><span class="badge bg-secondary">ランク2</span> 業界・一般紙</span>
    <span><span class="badge bg-dark">ランク1</span> SNSトレンド</span>
    &nbsp;|&nbsp; <span class="badge bg-danger">急上昇</span> = 動的検知（定義外の新テーマ）
  </div>

  <!-- テーマサマリー -->
  <h2 class="h5 mb-3 border-bottom pb-2">🔍 検知されたトレンドテーマ（大テーマ・小テーマ）</h2>
  <div class="row">{theme_cards_html}</div>

  <!-- 銘柄ランキング -->
  <h2 class="h5 mb-3 border-bottom pb-2 mt-4">🏆 関連銘柄ランキング（上位{len(ranked_stocks)}社）</h2>
  <div class="table-responsive" style="max-height:70vh; overflow-y:auto;">
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
      <tbody>{stock_rows_html}</tbody>
    </table>
  </div>

  <!-- 凡例 -->
  <div class="card mt-4 mb-5 border-0 bg-light">
    <div class="card-body small text-muted">
      <strong>市場:</strong>
      <span class="badge bg-primary">P</span> プライム &nbsp;
      <span class="badge bg-success">S</span> スタンダード &nbsp;
      <span class="badge bg-warning text-dark">G</span> グロース
      &nbsp;|&nbsp; スコア列にカーソルで内訳表示
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
