"""
テーマ → 銘柄マッピング
検知されたテーマに対して、関連する銘柄を業種コード・会社名キーワードで絞り込む
"""
import logging
import pandas as pd
from dataclasses import dataclass, field

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from analyzers.base_analyzer import DetectedTheme
from data.themes import INVESTMENT_THEMES

logger = logging.getLogger(__name__)


@dataclass
class MappedStock:
    code: str
    name: str
    market_badge: str        # P / S / G
    market_name: str         # プライム / スタンダード / グロース
    sector33_name: str
    display: str             # "[P] 7203 トヨタ自動車"
    theme_name: str
    match_reason: str        # マッチした理由 (業種コード / 会社名キーワード)
    base_score: float = 0.0  # ranker でスコアが付与される


def map_stocks(
    themes: list[DetectedTheme],
    stock_df: pd.DataFrame,
    top_themes: int = 5,
    max_stocks_per_theme: int = 20,
) -> list[MappedStock]:
    """
    上位テーマの関連銘柄を抽出する

    Args:
        themes:              DetectedTheme のリスト（スコア降順を想定）
        stock_df:            data.stock_db.load_stocks() で取得した DataFrame
        top_themes:          上位何テーマまで対象にするか
        max_stocks_per_theme: テーマあたりの最大銘柄数

    Returns:
        MappedStock のリスト（重複コードは先に見つかったテーマを優先）
    """
    result: list[MappedStock] = []
    seen_codes: set[str] = set()

    for theme in themes[:top_themes]:
        theme_def = INVESTMENT_THEMES.get(theme.name)
        if theme_def is None:
            # Claude API が新テーマを生成した場合はスキップ（または汎用マッチ）
            logger.debug(f"テーマ定義なし: {theme.name}")
            continue

        # themes.py は数値コード、V2 API は "0007" 形式のどちらにも対応
        raw_codes = theme_def.get("sector33_codes", [])
        sector_codes = []
        for c in raw_codes:
            s = str(c)
            sector_codes.append(s)           # "7"
            sector_codes.append(s.zfill(4))  # "0007"
        company_kws   = theme_def.get("company_keywords", [])

        # 業種コードマッチ
        sector_match = stock_df[stock_df["Sector33Code"].isin(sector_codes)].copy()
        sector_match["match_reason"] = "業種:" + sector_match["Sector33CodeName"].fillna("")

        # 会社名キーワードマッチ（業種マッチ外の銘柄から追加）
        name_mask = pd.Series(False, index=stock_df.index)
        for kw in company_kws:
            name_mask |= stock_df["CompanyName"].str.contains(kw, na=False)
        name_match = stock_df[name_mask & ~stock_df.index.isin(sector_match.index)].copy()
        name_match["match_reason"] = "社名キーワード"

        combined = pd.concat([sector_match, name_match], ignore_index=True)

        added = 0
        for _, row in combined.iterrows():
            code = str(row["Code"]).strip()
            if code in seen_codes:
                continue
            seen_codes.add(code)

            result.append(MappedStock(
                code         = code,
                name         = row["CompanyName"],
                market_badge = row.get("Badge", "?"),
                market_name  = row.get("MarketCodeName", ""),
                sector33_name= row.get("Sector33CodeName", ""),
                display      = row.get("DisplayCode", f"{code} {row['CompanyName']}"),
                theme_name   = theme.name,
                match_reason = row["match_reason"],
            ))
            added += 1
            if added >= max_stocks_per_theme:
                break

    logger.info(f"マッピング完了: {len(result)} 銘柄 / {min(top_themes, len(themes))} テーマ")
    return result
