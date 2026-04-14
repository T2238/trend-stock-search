"""
テーマ → 銘柄マッピング（多テーマ対応版）

各銘柄は複数テーマに紐づき、テーマごとに重みを持つ。

重みの決定ロジック（優先順位順）:
  1. stock_theme_base.py の手動マスター（最優先）
  2. ニュース共起スコア（記事内に銘柄名+テーマKWが同時出現）
  3. セクターコードマッチ（基礎重み 1.0）
  4. 会社名キーワードマッチ（基礎重み 0.8）
"""
import logging
from dataclasses import dataclass, field
from collections import defaultdict

import pandas as pd

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from analyzers.base_analyzer import DetectedTheme
from data.themes import INVESTMENT_THEMES
from data.stock_theme_base import get_all_themes_for_stock
from mappers.name_extractor import build_name_index, extract_mentions
from config import SOURCE_RANK_WEIGHT

logger = logging.getLogger(__name__)


@dataclass
class MappedStock:
    code: str
    name: str
    market_badge: str
    market_name: str
    sector33_name: str
    display: str
    # 多テーマ対応
    theme_weights: dict[str, float] = field(default_factory=dict)
    # 主テーマ（最大重みのテーマ）
    primary_theme: str = ""
    # ニュース直接言及カウント（ソースランク重み付き）
    news_mention_score: float = 0.0
    # 重みの根拠メモ
    weight_sources: dict[str, str] = field(default_factory=dict)
    # 関連する小テーマ
    sub_themes_hit: list[str] = field(default_factory=list)


def map_stocks(
    themes: list[DetectedTheme],
    stock_df: pd.DataFrame,
    articles=None,
    top_themes: int = 8,
    max_stocks: int = 100,
) -> list[MappedStock]:
    """
    検知テーマから関連銘柄を多テーマ対応でマッピングする

    Args:
        themes:     DetectedTheme リスト（スコア降順）
        stock_df:   load_stocks() の DataFrame
        articles:   ニュース記事リスト（共起スコア計算に使用、省略可）
        top_themes: 対象テーマ数
        max_stocks: 最大銘柄数

    Returns:
        MappedStock のリスト
    """
    active_themes = themes[:top_themes]
    theme_names = {t.name for t in active_themes}

    # --- Step 1: セクター・キーワードベースのマッピング ---
    # code → {theme: weight} を積み上げる
    code_to_weights: dict[str, dict[str, float]] = defaultdict(dict)
    code_to_row: dict[str, pd.Series] = {}
    code_to_sub_themes: dict[str, set[str]] = defaultdict(set)

    for theme in active_themes:
        theme_def = INVESTMENT_THEMES.get(theme.name)
        if theme_def is None:
            continue

        sector_codes  = [str(c) for c in theme_def.get("sector33_codes", [])]
        sector_codes += [c.zfill(4) for c in sector_codes]
        company_kws   = theme_def.get("company_keywords", [])

        # セクターマッチ（重み 1.0）
        sector_rows = stock_df[stock_df["Sector33Code"].isin(sector_codes)]
        for _, row in sector_rows.iterrows():
            code = str(row["Code"]).strip()
            code_to_weights[code][theme.name] = max(
                code_to_weights[code].get(theme.name, 0.0), 1.0
            )
            code_to_row[code] = row

        # 会社名キーワードマッチ（重み 0.8）
        mask = pd.Series(False, index=stock_df.index)
        for kw in company_kws:
            mask |= stock_df["CompanyName"].str.contains(kw, na=False)
        for _, row in stock_df[mask].iterrows():
            code = str(row["Code"]).strip()
            if theme.name not in code_to_weights[code]:
                code_to_weights[code][theme.name] = 0.8
                code_to_row[code] = row

        # 小テーマKWマッチ → sub_themes_hit に記録
        sub_defs = theme_def.get("sub_themes", {})
        for sub_name, sub_def in sub_defs.items():
            for kw in sub_def.get("keywords", []):
                sub_mask = stock_df["CompanyName"].str.contains(kw, na=False)
                for _, row in stock_df[sub_mask].iterrows():
                    code = str(row["Code"]).strip()
                    code_to_sub_themes[code].add(sub_name)

    # --- Step 2: 手動マスターで上書き ---
    for code in list(code_to_weights.keys()):
        manual = get_all_themes_for_stock(code)
        for theme_name, manual_weight in manual.items():
            if theme_name in theme_names:
                code_to_weights[code][theme_name] = manual_weight
            elif theme_name not in code_to_weights[code]:
                # マスターに定義されてるがアクティブテーマ外 → 銘柄自体を追加
                pass

    # マスター銘柄で stock_df にない場合も追加
    for code, manual_weights in {
        c: w for c, w in [(c, get_all_themes_for_stock(c)) for c in _all_master_codes()]
        if any(t in theme_names for t in w)
    }.items():
        if code not in code_to_weights:
            row = stock_df[stock_df["Code"] == code]
            if not row.empty:
                code_to_row[code] = row.iloc[0]
                for t, w in manual_weights.items():
                    if t in theme_names:
                        code_to_weights[code][t] = w

    # --- Step 3: ニュース共起スコア ---
    news_mention_scores: dict[str, float] = defaultdict(float)
    if articles:
        name_index = build_name_index(stock_df)
        # テーマキーワードセット
        theme_kw_map: dict[str, set[str]] = {
            t.name: set(t.keywords_found) for t in active_themes
        }

        for article in articles:
            text = article.text
            rank_weight = SOURCE_RANK_WEIGHT.get(article.source_rank, 1.0)
            mentioned_codes = extract_mentions(text, name_index)

            # 記事に含まれるテーマを特定
            article_themes = [
                t.name for t in active_themes
                if any(kw in text for kw in theme_kw_map[t.name])
            ]

            for code in mentioned_codes:
                for t_name in article_themes:
                    # 共起ボーナス: テーマと銘柄が同一記事に出現
                    news_mention_scores[code] += rank_weight * 0.5
                    # 既存重みをブースト（最大 2.0 まで）
                    current = code_to_weights[code].get(t_name, 0.0)
                    code_to_weights[code][t_name] = min(current + rank_weight * 0.3, 2.0)
                    if code not in code_to_row:
                        row = stock_df[stock_df["Code"] == code]
                        if not row.empty:
                            code_to_row[code] = row.iloc[0]

    # --- Step 4: MappedStock を組み立て ---
    result: list[MappedStock] = []

    for code, weights in code_to_weights.items():
        if not weights:
            continue
        row = code_to_row.get(code)
        if row is None:
            continue

        # 主テーマ = 最大重みのテーマ
        primary = max(weights, key=lambda t: weights[t])

        # 根拠メモ
        weight_src: dict[str, str] = {}
        manual = get_all_themes_for_stock(code)
        for t_name, w in weights.items():
            if t_name in manual:
                weight_src[t_name] = f"マスター重み{w:.1f}"
            elif news_mention_scores.get(code, 0) > 0:
                weight_src[t_name] = f"共起+セクター重み{w:.1f}"
            else:
                weight_src[t_name] = f"セクター/KW重み{w:.1f}"

        result.append(MappedStock(
            code              = code,
            name              = str(row.get("CompanyName", "")),
            market_badge      = str(row.get("Badge", "?")),
            market_name       = str(row.get("MarketCodeName", "")),
            sector33_name     = str(row.get("Sector33CodeName", "")),
            display           = str(row.get("DisplayCode", f"{code}")),
            theme_weights     = weights,
            primary_theme     = primary,
            news_mention_score= news_mention_scores.get(code, 0.0),
            weight_sources    = weight_src,
            sub_themes_hit    = sorted(code_to_sub_themes.get(code, set())),
        ))

    # テーマ数の多い銘柄・ニュース言及スコアが高い銘柄を優先してソート
    result.sort(
        key=lambda ms: (len(ms.theme_weights), ms.news_mention_score),
        reverse=True,
    )

    logger.info(
        f"マッピング完了: {len(result)} 銘柄 / {len(active_themes)} テーマ "
        f"(うちニュース共起: {sum(1 for ms in result if ms.news_mention_score > 0)} 銘柄)"
    )
    return result[:max_stocks]


def _all_master_codes() -> list[str]:
    from data.stock_theme_base import STOCK_THEME_WEIGHTS
    return list(STOCK_THEME_WEIGHTS.keys())
