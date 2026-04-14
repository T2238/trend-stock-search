"""
HTML レポート生成モジュール
大テーマ → 小テーマ → 銘柄（多テーマタグ付き）を表示
"""
import os
import logging
from datetime import datetime

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from rankers.ranker import RankedStock
from analyzers.base_analyzer import AnalysisResult
from config import OUTPUT_DIR, REPORT_FILENAME

logger = logging.getLogger(__name__)

MARKET_BADGE_CLASS = {"P": "bg-primary", "S": "bg-success", "G": "bg-warning text-dark", "?": "bg-secondary"}
STAR_COLOR = {5: "#ff6b00", 4: "#ff9500", 3: "#ffc107", 2: "#6c757d", 1: "#adb5bd"}
SOURCE_RANK_META = {5: ("danger", "一次金融"), 4: ("warning", "経済誌"), 3: ("info", "株専門"),
                    2: ("secondary", "業界紙"), 1: ("dark", "SNS")}

# テーマごとのバッジ色（循環）
_THEME_COLORS = ["primary", "success", "danger", "warning text-dark", "info text-dark",
                 "secondary", "dark", "primary", "success", "danger", "warning text-dark", "info text-dark"]


def _stars_html(n):
    c = STAR_COLOR.get(n, "#adb5bd")
    return f'<span style="color:{c};font-size:1.1em;">{"★"*n}{"☆"*(5-n)}</span>'


def _sentiment_bar(s):
    pct   = int((s + 1) / 2 * 100)
    color = "bg-success" if s > 0.2 else "bg-danger" if s < -0.2 else "bg-secondary"
    return (f'<div class="progress mb-1" style="height:5px;">'
            f'<div class="progress-bar {color}" style="width:{pct}%"></div></div>'
            f'<small class="text-muted">{s:+.2f}</small>')


def _theme_tags_html(theme_contributions: dict, theme_color_map: dict) -> str:
    """銘柄行に複数テーマタグを表示"""
    tags = []
    for t_name, contrib in sorted(theme_contributions.items(), key=lambda x: x[1], reverse=True):
        color = theme_color_map.get(t_name, "secondary")
        tags.append(f'<span class="badge bg-{color} me-1" title="{contrib:.1f}pt">{t_name}</span>')
    return "".join(tags)


def _sub_themes_html(sub_themes, is_dynamic_set=None):
    if not sub_themes:
        return ""
    items = []
    for s in sub_themes[:6]:
        dyn = '<span class="badge bg-danger ms-1" style="font-size:0.6em;">急上昇</span>' if s.is_dynamic else ""
        items.append(
            f'<span class="badge bg-light text-dark border me-1 mb-1" style="font-size:0.75em;">'
            f'{s.name}{dyn}'
            f'<small class="text-muted ms-1">({s.article_count}件)</small></span>'
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

    # テーマ → 色マップ
    theme_color_map = {t.name: _THEME_COLORS[i % len(_THEME_COLORS)]
                       for i, t in enumerate(analysis.themes)}

    # --- テーマカード ---
    theme_cards_html = ""
    for theme in analysis.themes[:9]:
        kw_badges = "".join(
            f'<span class="badge bg-light text-dark border me-1">{kw}</span>'
            for kw in theme.keywords_found[:6]
        )
        src_color, src_label = SOURCE_RANK_META.get(theme.top_source_rank, ("secondary", "不明"))
        theme_cards_html += f"""
        <div class="col-md-6 col-lg-4 mb-3">
          <div class="card h-100 shadow-sm">
            <div class="card-header d-flex justify-content-between align-items-center py-2">
              <strong>{theme.name}</strong>
              <div>
                <span class="badge bg-{src_color} me-1" title="{src_label}">情報源ランク{theme.top_source_rank}</span>
                <span class="badge bg-primary">{theme.score:.0f}pt</span>
              </div>
            </div>
            <div class="card-body py-2">
              {_sentiment_bar(theme.sentiment)}
              <small class="text-muted d-block mb-1">記事数: {theme.article_count}件</small>
              <div>{kw_badges}</div>
              {_sub_themes_html(theme.sub_themes)}
              {f'<p class="card-text mt-2 small text-secondary">{theme.reason}</p>' if theme.reason else ''}
            </div>
          </div>
        </div>"""

    # --- 銘柄テーブル ---
    stock_rows_html = ""
    for pos, rs in enumerate(ranked_stocks, 1):
        ms = rs.stock
        badge_cls = f"badge {MARKET_BADGE_CLASS.get(ms.market_badge, 'bg-secondary')}"
        theme_tags = _theme_tags_html(rs.theme_contributions, theme_color_map)

        # ニュース言及バッジ
        mention_badge = ""
        if rs.mention_boost > 1.05:
            mention_badge = f'<span class="badge bg-warning text-dark ms-1" title="ニュース直接言及">📰×{rs.mention_boost:.2f}</span>'

        # 小テーマバッジ
        sub_badge = ""
        if ms.sub_themes_hit:
            sub_badge = f'<br><small class="text-muted">{" / ".join(ms.sub_themes_hit[:3])}</small>'

        tooltip = rs.reason.replace('"', "'")
        stock_rows_html += f"""
        <tr>
          <td class="text-center fw-bold">{pos}</td>
          <td>
            <span class="{badge_cls} me-1">{ms.market_badge}</span>
            <strong>{ms.code}</strong> {ms.name}
            {mention_badge}{sub_badge}
          </td>
          <td><small class="text-muted">{ms.market_name}</small></td>
          <td><small class="text-muted">{ms.sector33_name}</small></td>
          <td>{_stars_html(rs.stars)}</td>
          <td class="text-center" title="{tooltip}">
            <span class="badge bg-dark">{rs.score:.1f}</span>
          </td>
          <td style="max-width:250px;">{theme_tags}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>トレンド株銘柄レポート {now_str}</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
  <style>
    body  {{font-family:'Meiryo','Yu Gothic',sans-serif;background:#f8f9fa;}}
    .hero {{background:linear-gradient(135deg,#1a1a2e,#16213e);color:#fff;padding:2rem;}}
    thead th {{background:#343a40;color:#fff;position:sticky;top:0;z-index:1;}}
    tr:hover {{background:#f0f4ff;}}
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

  <div class="alert alert-light border small mb-3 py-2">
    <strong>情報源ランク:</strong>
    <span class="badge bg-danger">5</span>日経・Reuters &nbsp;
    <span class="badge bg-warning text-dark">4</span>NHK・経済誌 &nbsp;
    <span class="badge bg-info text-dark">3</span>株専門 &nbsp;
    <span class="badge bg-secondary">2</span>業界紙 &nbsp;
    <span class="badge bg-dark">1</span>SNS &nbsp;|&nbsp;
    <span class="badge bg-warning text-dark">📰</span>ニュースに社名が直接登場したブースト &nbsp;|&nbsp;
    <span class="badge bg-danger" style="font-size:0.7em;">急上昇</span>動的検知テーマ
  </div>

  <h2 class="h5 mb-3 border-bottom pb-2">🔍 検知されたトレンドテーマ</h2>
  <div class="row">{theme_cards_html}</div>

  <h2 class="h5 mb-3 border-bottom pb-2 mt-4">
    🏆 関連銘柄ランキング（上位{len(ranked_stocks)}社）
    <small class="text-muted fw-normal fs-6"> — 複数テーマタグ付き・スコアにカーソルで根拠表示</small>
  </h2>
  <div class="table-responsive" style="max-height:75vh;overflow-y:auto;">
    <table class="table table-hover table-sm align-middle">
      <thead>
        <tr>
          <th style="width:35px">#</th>
          <th>銘柄</th>
          <th>市場</th>
          <th>業種</th>
          <th>評価</th>
          <th style="width:55px">スコア</th>
          <th>テーマ（重み順）</th>
        </tr>
      </thead>
      <tbody>{stock_rows_html}</tbody>
    </table>
  </div>

  <div class="card mt-4 mb-5 border-0 bg-light">
    <div class="card-body small text-muted">
      <strong>市場:</strong>
      <span class="badge bg-primary">P</span>プライム &nbsp;
      <span class="badge bg-success">S</span>スタンダード &nbsp;
      <span class="badge bg-warning text-dark">G</span>グロース
    </div>
  </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info(f"レポート生成完了: {output_path}")
    return output_path
