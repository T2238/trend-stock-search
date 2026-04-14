"""
ニュース記事から会社名を抽出するユーティリティ

アルゴリズム:
  1. stocks.csv から会社名を正規化してインデックスを構築
  2. 各記事テキストを走査し、会社名が含まれているか確認
  3. ヒットした銘柄コードを返す（共起抽出に使用）
"""
import re
import logging
import pandas as pd

logger = logging.getLogger(__name__)

# 正規化時に除去するサフィックス
_SUFFIXES = re.compile(
    r"(株式会社|ホールディングス|ホールディング|グループ|HD|G$|"
    r"フィナンシャルグループ|銀行グループ|証券グループ|"
    r"インターナショナル|コーポレーション|テクノロジーズ|テクノロジー)"
)
# 3文字以下の短い略称だと誤検知しやすい最低文字数
_MIN_NAME_LEN = 4


def build_name_index(stock_df: pd.DataFrame) -> dict[str, str]:
    """
    会社名 → 証券コード のインデックスを構築する

    Returns:
        {正規化会社名: code} の辞書（長い名前を先に登録）
    """
    index: dict[str, str] = {}
    rows = []

    for _, row in stock_df.iterrows():
        code = str(row["Code"]).strip()
        name = str(row.get("CompanyName", "")).strip()
        if not name:
            continue

        # 正規化: サフィックス除去・空白除去
        normalized = _SUFFIXES.sub("", name).strip()

        # 登録候補を収集
        candidates = []
        if len(name) >= _MIN_NAME_LEN:
            candidates.append(name)
        if normalized != name and len(normalized) >= _MIN_NAME_LEN:
            candidates.append(normalized)

        for c in candidates:
            rows.append((len(c), c, code))

    # 長い名前を優先（短い名前が長い名前の部分一致で誤検知しないよう）
    rows.sort(key=lambda x: x[0], reverse=True)
    for _, c, code in rows:
        if c not in index:
            index[c] = code

    logger.debug(f"会社名インデックス構築: {len(index)} エントリ")
    return index


def extract_mentions(
    text: str,
    name_index: dict[str, str],
    max_per_article: int = 10,
) -> list[str]:
    """
    テキストから会社名を探し、証券コードのリストを返す

    Args:
        text:            記事テキスト
        name_index:      build_name_index() の結果
        max_per_article: 1記事あたり最大抽出数

    Returns:
        証券コードのリスト（重複なし）
    """
    found: list[str] = []
    seen_codes: set[str] = set()

    for name, code in name_index.items():
        if code in seen_codes:
            continue
        if name in text:
            found.append(code)
            seen_codes.add(code)
            if len(found) >= max_per_article:
                break

    return found
