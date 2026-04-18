"""
HTML レポート生成モジュール
大テーマ → 小テーマ → 銘柄（多テーマタグ付き）を表示
トレンド変化・株価リターンセクション追加
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

_THEME_COLORS = ["primary", "success", "danger", "warning text-dark", "info text-dark",
                 "secondary", "dark", "primary", "success", "danger", "warning text-dark", "info text-dark"]

_CHANGE_TYPE_BADGE = {
    "new":         ("success",   "🆕 新規"),
    "rising":      ("danger",    "↑ 急上昇"),
    "stable":      ("secondary", "→ 安定"),
    "falling":     ("warning",   "↓ 急落"),
    "disappeared": ("dark",      "💨 消滅"),
}


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
    tags = []
    for t_name, contrib in sorted(theme_contributions.items(), key=lambda x: x[1], reverse=True):
        color = theme_color_map.get(t_name, "secondary")
        tags.append(f'<span class="badge bg-{color} me-1" title="{contrib:.1f}pt">{t_name}</span>')
    return "".join(tags)


def _rank_breakdown_html(rank_breakdown: dict) -> str:
    """ランク別記事数をミニバーで表示"""
    if not rank_breakdown:
        return ""
    total = sum(rank_breakdown.values())
    rank_colors = {5: "#dc3545", 4: "#ffc107", 3: "#0dcaf0", 2: "#6c757d", 1: "#212529"}
    rank_labels = {5: "R5", 4: "R4", 3: "R3", 2: "R2", 1: "R1"}
    bars = ""
    for rank in sorted(rank_breakdown.keys(), reverse=True):
        cnt = rank_breakdown[rank]
        pct = cnt / total * 100
        color = rank_colors.get(rank, "#aaa")
        label = rank_labels.get(rank, f"R{rank}")
        bars += (f'<span title="ランク{rank}: {cnt}件" style="display:inline-block;'
                 f'width:{pct:.0f}%;background:{color};height:8px;"></span>')
    badges = " ".join(
        '<span style="font-size:0.7em;color:{};">R{}:{}</span>'.format(
            rank_colors.get(r, "#aaa"), r, rank_breakdown[r]
        )
        for r in sorted(rank_breakdown.keys(), reverse=True)
    )
    return f'<div class="mt-1"><div style="display:flex;border-radius:3px;overflow:hidden;height:8px;">{bars}</div><div class="mt-1">{badges}</div></div>'


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


def _fmt_return(v):
    """リターン値をカラー付きHTML文字列に変換"""
    if v is None:
        return '<span class="text-muted">-</span>'
    color = "text-success" if v > 0 else "text-danger"
    return f'<span class="{color}">{v*100:+.1f}%</span>'


def _trend_watch_section(watch_result) -> str:
    """トレンド変化セクションのHTML"""
    if watch_result is None or not watch_result.has_history:
        return ""

    rows = ""
    for tc in watch_result.theme_changes:
        badge_color, badge_label = _CHANGE_TYPE_BADGE.get(tc.change_type, ("secondary", tc.change_type))
        score_delta_html = ""
        if tc.score_delta is not None:
            color = "text-success" if tc.score_delta > 0 else "text-danger"
            score_delta_html = f'<span class="{color}">{tc.score_delta:+.0f}</span>'
        rank_delta_html = ""
        if tc.rank_delta is not None:
            color = "text-success" if tc.rank_delta < 0 else "text-danger"
            rank_delta_html = f'<span class="{color}">{tc.rank_delta:+d}</span>'

        rows += f"""
        <tr>
          <td><span class="badge bg-{badge_color}">{badge_label}</span></td>
          <td><strong>{tc.name}</strong></td>
          <td class="text-center">{tc.current_score:.0f}pt</td>
          <td class="text-center">{score_delta_html}</td>
          <td class="text-center">{tc.current_rank or '-'}</td>
          <td class="text-center">{rank_delta_html}</td>
        </tr>"""

    prev_label = f"前回: {watch_result.prev_date}" if watch_result.prev_date else ""
    return f"""
  <h2 class="h5 mb-3 border-bottom pb-2 mt-4">📊 トレンド変化 <small class="text-muted fw-normal fs-6">{prev_label}</small></h2>
  <div class="table-responsive mb-4">
    <table class="table table-sm table-hover align-middle">
      <thead class="table-dark">
        <tr>
          <th>変化</th><th>テーマ</th>
          <th class="text-center">現スコア</th>
          <th class="text-center">Δスコア</th>
          <th class="text-center">現順位</th>
          <th class="text-center">Δ順位</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
  </div>"""


def _price_return_cells(code: str, price_data: dict) -> str:
    """銘柄コードに対応する株価リターンのTDセルHTML"""
    if not price_data or code not in price_data:
        return '<td class="text-center text-muted">-</td><td class="text-center text-muted">-</td><td class="text-center text-muted">-</td>'
    excess = price_data[code].get("excess", {})
    return (f'<td class="text-center">{_fmt_return(excess.get("1d"))}</td>'
            f'<td class="text-center">{_fmt_return(excess.get("5d"))}</td>'
            f'<td class="text-center">{_fmt_return(excess.get("20d"))}</td>')


def generate_report(
    ranked_stocks: list[RankedStock],
    analysis: AnalysisResult,
    watch_result=None,
    price_data: dict | None = None,
    output_path: str | None = None,
) -> str:
    if output_path is None:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        output_path = os.path.join(OUTPUT_DIR, REPORT_FILENAME)

    now_str    = datetime.now().strftime("%Y年%m月%d日 %H:%M")
    mode_label = "Claude AI 高精度モード" if analysis.mode == "claude" else "ルールベースモード"
    mode_badge = "bg-info" if analysis.mode == "claude" else "bg-secondary"

    theme_color_map = {t.name: _THEME_COLORS[i % len(_THEME_COLORS)]
                       for i, t in enumerate(analysis.themes)}
    # テーマ名 → top_source_rank マップ（銘柄の最高ランク算出用）
    theme_rank_map = {t.name: t.top_source_rank for t in analysis.themes}

    # --- テーマカード ---
    theme_cards_html = ""
    for theme in analysis.themes[:9]:
        kw_badges = "".join(
            f'<span class="badge bg-light text-dark border me-1">{kw}</span>'
            for kw in theme.keywords_found[:6]
        )
        src_color, src_label = SOURCE_RANK_META.get(theme.top_source_rank, ("secondary", "不明"))
        rank_bar = _rank_breakdown_html(getattr(theme, "rank_breakdown", {}))
        theme_cards_html += f"""
        <div class="col-md-6 col-lg-4 mb-3">
          <div class="card h-100 shadow-sm">
            <div class="card-header d-flex justify-content-between align-items-center py-2">
              <strong>{theme.name}</strong>
              <div>
                <span class="badge bg-{src_color} me-1" title="{src_label}">最高R{theme.top_source_rank}</span>
                <span class="badge bg-primary">{theme.score:.0f}pt</span>
              </div>
            </div>
            <div class="card-body py-2">
              {_sentiment_bar(theme.sentiment)}
              <small class="text-muted d-block mb-1">記事数: {theme.article_count}件</small>
              {rank_bar}
              <div class="mt-1">{kw_badges}</div>
              {_sub_themes_html(theme.sub_themes)}
              {f'<p class="card-text mt-2 small text-secondary">{theme.reason}</p>' if theme.reason else ''}
            </div>
          </div>
        </div>"""

    # --- 銘柄テーブル ---
    has_price = bool(price_data)
    price_headers = """
          <th class="text-center" title="TOPIX超過リターン 1日後">1d超過</th>
          <th class="text-center" title="TOPIX超過リターン 5日後">5d超過</th>
          <th class="text-center" title="TOPIX超過リターン 20日後">20d超過</th>""" if has_price else ""

    stock_rows_html = ""
    for pos, rs in enumerate(ranked_stocks, 1):
        ms = rs.stock
        badge_cls = f"badge {MARKET_BADGE_CLASS.get(ms.market_badge, 'bg-secondary')}"
        theme_tags = _theme_tags_html(rs.theme_contributions, theme_color_map)

        # 銘柄の最高ソースランク（関連テーマのうち最大）
        stock_top_rank = max(
            (theme_rank_map.get(t, 1) for t in rs.theme_contributions),
            default=1,
        )
        rank_color = {5: "#dc3545", 4: "#ffc107", 3: "#0dcaf0", 2: "#6c757d", 1: "#212529"}.get(stock_top_rank, "#aaa")
        rank_badge = (f'<span class="badge ms-1" style="background:{rank_color};font-size:0.7em;" '
                      f'title="最高言及ランク">R{stock_top_rank}</span>')

        mention_badge = ""
        if rs.mention_boost > 1.05:
            mention_badge = f'<span class="badge bg-warning text-dark ms-1" title="ニュース直接言及">📰×{rs.mention_boost:.2f}</span>'

        sub_badge = ""
        if ms.sub_themes_hit:
            sub_badge = f'<br><small class="text-muted">{" / ".join(ms.sub_themes_hit[:3])}</small>'

        tooltip = rs.reason.replace('"', "'")
        price_cells = _price_return_cells(ms.code, price_data) if has_price else ""

        stock_rows_html += f"""
        <tr class="stock-row" data-top-rank="{stock_top_rank}">
          <td class="text-center fw-bold">{pos}</td>
          <td>
            <span class="{badge_cls} me-1">{ms.market_badge}</span>
            <strong>{ms.code}</strong> {ms.name}
            {rank_badge}{mention_badge}{sub_badge}
          </td>
          <td><small class="text-muted">{ms.market_name}</small></td>
          <td><small class="text-muted">{ms.sector33_name}</small></td>
          <td>{_stars_html(rs.stars)}</td>
          <td class="text-center" title="{tooltip}">
            <span class="badge bg-dark">{rs.score:.1f}</span>
          </td>
          <td style="max-width:250px;">{theme_tags}</td>
          {price_cells}
        </tr>"""

    # --- トレンド変化セクション ---
    watch_section_html = _trend_watch_section(watch_result)

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

  {watch_section_html}

  <h2 class="h5 mb-3 border-bottom pb-2 mt-4">
    🏆 関連銘柄ランキング（上位{len(ranked_stocks)}社）
    <small class="text-muted fw-normal fs-6"> — 複数テーマタグ付き・スコアにカーソルで根拠表示</small>
  </h2>
  <div class="mb-2 d-flex align-items-center gap-2 flex-wrap">
    <small class="text-muted me-1">情報源ランクでフィルター:</small>
    <button class="btn btn-sm btn-outline-secondary rank-filter active" data-min-rank="1">全て</button>
    <button class="btn btn-sm rank-filter" data-min-rank="4"
      style="border-color:#ffc107;color:#856404;">R4以上（経済誌↑）</button>
    <button class="btn btn-sm rank-filter" data-min-rank="5"
      style="border-color:#dc3545;color:#dc3545;">R5のみ（日経・Reuters・Bloomberg）</button>
    <span id="rank-filter-count" class="text-muted small ms-2"></span>
  </div>
  <div class="table-responsive" style="max-height:75vh;overflow-y:auto;">
    <table class="table table-hover table-sm align-middle" id="stock-table">
      <thead>
        <tr>
          <th style="width:35px">#</th>
          <th>銘柄</th>
          <th>市場</th>
          <th>業種</th>
          <th>評価</th>
          <th style="width:55px">スコア</th>
          <th>テーマ（重み順）</th>
          {price_headers}
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
      {' &nbsp;|&nbsp; <strong>超過リターン:</strong> TOPIX(1306.T)比' if has_price else ''}
    </div>
  </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<script>
(function() {{
  var minRank = 1;
  function applyFilter() {{
    var rows = document.querySelectorAll('#stock-table .stock-row');
    var visible = 0;
    rows.forEach(function(row) {{
      var rank = parseInt(row.getAttribute('data-top-rank') || '1');
      var show = rank >= minRank;
      row.style.display = show ? '' : 'none';
      if (show) visible++;
    }});
    var countEl = document.getElementById('rank-filter-count');
    if (countEl) countEl.textContent = visible + '件表示';
  }}
  document.querySelectorAll('.rank-filter').forEach(function(btn) {{
    btn.addEventListener('click', function() {{
      document.querySelectorAll('.rank-filter').forEach(function(b) {{
        b.classList.remove('active','btn-secondary','btn-warning','btn-danger');
        b.classList.add('btn-outline-secondary');
        b.style.backgroundColor = '';
        b.style.color = b.getAttribute('data-min-rank') == '4' ? '#856404'
                      : b.getAttribute('data-min-rank') == '5' ? '#dc3545' : '';
      }});
      minRank = parseInt(this.getAttribute('data-min-rank'));
      this.classList.remove('btn-outline-secondary');
      this.classList.add('active');
      this.style.backgroundColor = minRank >= 5 ? '#dc3545' : minRank >= 4 ? '#ffc107' : '#6c757d';
      this.style.color = '#fff';
      applyFilter();
    }});
  }});
  applyFilter();
}})();
</script>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info(f"レポート生成完了: {output_path}")
    return output_path
