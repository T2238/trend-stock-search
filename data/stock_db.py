"""
銘柄データベース管理
stocks.csv を読み込み、市場区分・業種コード付きの銘柄リストを提供する

CSVフォーマット（J-Quants API /listed/info から生成）:
  Code, CompanyName, CompanyNameEnglish, MarketCode, MarketCodeName,
  Sector17Code, Sector17CodeName, Sector33Code, Sector33CodeName,
  ScaleCategory

市場区分バッジ:
  [P] プライム市場
  [S] スタンダード市場
  [G] グロース市場
"""
import os
import logging
import pandas as pd

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import STOCKS_CSV_PATH

logger = logging.getLogger(__name__)

# 市場コード → バッジ・表示名
# V2 API は "0111" 形式、サンプルデータは "111" 形式の両方に対応
MARKET_BADGE = {
    "0111": ("P", "プライム"),
    "0112": ("S", "スタンダード"),
    "0113": ("G", "グロース"),
    "0114": ("S", "スタンダード"),
    "111":  ("P", "プライム"),
    "112":  ("S", "スタンダード"),
    "113":  ("G", "グロース"),
    "114":  ("S", "スタンダード"),
    "999":  ("?", "その他"),
}


def _badge(market_code: str) -> str:
    code = str(market_code).strip()
    badge, _ = MARKET_BADGE.get(code, ("?", "その他"))
    return badge


def load_stocks() -> pd.DataFrame:
    """
    stocks.csv を読み込んで DataFrame を返す。
    ファイルがなければ fetch_stocks.py の実行を促すメッセージを表示する。
    """
    if not os.path.exists(STOCKS_CSV_PATH):
        logger.warning(
            f"銘柄リストが見つかりません: {STOCKS_CSV_PATH}\n"
            "  → python data/fetch_stocks.py を実行して銘柄リストを取得してください。\n"
            "  → サンプルデータで代替します。"
        )
        return _sample_stocks()

    df = pd.read_csv(STOCKS_CSV_PATH, dtype={"Code": str, "MarketCode": str,
                                              "Sector33Code": str, "Sector17Code": str})
    df["Badge"]      = df["MarketCode"].apply(_badge)
    df["DisplayCode"] = df.apply(
        lambda r: f"[{r['Badge']}] {r['Code']} {r['CompanyName']}", axis=1
    )
    logger.info(f"銘柄数: {len(df)} 社読み込み完了")
    return df


def get_stocks_by_sector33(df: pd.DataFrame, codes: list[int]) -> pd.DataFrame:
    """業種コード(33分類)で銘柄をフィルタリング"""
    str_codes = [str(c) for c in codes]
    return df[df["Sector33Code"].isin(str_codes)]


def _sample_stocks() -> pd.DataFrame:
    """
    J-Quants未設定時のサンプル銘柄（主要プライム銘柄）
    実運用では fetch_stocks.py で全銘柄を取得すること
    """
    rows = [
        # Code, CompanyName, MarketCode, MarketCodeName, Sector33Code, Sector33CodeName
        ("7203", "トヨタ自動車",         "111", "プライム市場", "17", "輸送用機器"),
        ("6758", "ソニーグループ",        "111", "プライム市場", "16", "電気機器"),
        ("9984", "ソフトバンクグループ",  "111", "プライム市場", "25", "情報・通信業"),
        ("6367", "ダイキン工業",          "111", "プライム市場", "15", "機械"),
        ("4519", "中外製薬",              "111", "プライム市場", "8",  "医薬品"),
        ("6594", "日本電産",              "111", "プライム市場", "16", "電気機器"),
        ("8035", "東京エレクトロン",      "111", "プライム市場", "16", "電気機器"),
        ("4063", "信越化学工業",          "111", "プライム市場", "7",  "化学"),
        ("6861", "キーエンス",            "111", "プライム市場", "16", "電気機器"),
        ("9432", "日本電信電話(NTT)",     "111", "プライム市場", "25", "情報・通信業"),
        ("9433", "KDDI",                 "111", "プライム市場", "25", "情報・通信業"),
        ("4307", "野村総合研究所",        "111", "プライム市場", "25", "情報・通信業"),
        ("3659", "ネクソン",              "111", "プライム市場", "25", "情報・通信業"),
        ("4385", "メルカリ",              "113", "グロース市場", "25", "情報・通信業"),
        ("4565", "そーせいグループ",      "113", "グロース市場", "8",  "医薬品"),
        ("7011", "三菱重工業",            "111", "プライム市場", "15", "機械"),
        ("7012", "川崎重工業",            "111", "プライム市場", "15", "機械"),
        ("6113", "アマダ",               "111", "プライム市場", "15", "機械"),
        ("5401", "日本製鉄",              "111", "プライム市場", "12", "鉄鋼"),
        ("5713", "住友金属鉱山",          "111", "プライム市場", "13", "非鉄金属"),
        ("8316", "三井住友フィナンシャル", "111", "プライム市場", "28", "銀行業"),
        ("8411", "みずほフィナンシャル",  "111", "プライム市場", "28", "銀行業"),
        ("3382", "セブン&アイHD",        "111", "プライム市場", "27", "小売業"),
        ("9020", "東日本旅客鉄道(JR東)",  "111", "プライム市場", "21", "陸運業"),
        ("9202", "ANAホールディングス",  "111", "プライム市場", "23", "空運業"),
        ("9201", "日本航空(JAL)",        "111", "プライム市場", "23", "空運業"),
        ("8001", "伊藤忠商事",            "111", "プライム市場", "26", "卸売業"),
        ("1925", "大和ハウス工業",        "111", "プライム市場", "3",  "建設業"),
        ("8802", "三菱地所",              "111", "プライム市場", "32", "不動産業"),
        ("2802", "味の素",               "111", "プライム市場", "4",  "食料品"),
        ("2914", "日本たばこ産業(JT)",   "111", "プライム市場", "4",  "食料品"),
        ("9531", "東京ガス",              "111", "プライム市場", "20", "電気・ガス業"),
        ("9503", "関西電力",              "111", "プライム市場", "20", "電気・ガス業"),
        ("4901", "富士フイルムHD",       "111", "プライム市場", "7",  "化学"),
        ("7751", "キヤノン",              "111", "プライム市場", "18", "精密機器"),
        # スタンダード
        ("3197", "すかいらーくHD",        "112", "スタンダード市場", "27", "小売業"),
        ("9962", "ミスミグループ本社",    "112", "スタンダード市場", "26", "卸売業"),
        # グロース
        ("4478", "フリー",               "113", "グロース市場", "25", "情報・通信業"),
        ("4166", "カオナビ",              "113", "グロース市場", "25", "情報・通信業"),
        ("7095", "Macbee Planet",        "113", "グロース市場", "25", "情報・通信業"),
    ]
    df = pd.DataFrame(rows, columns=[
        "Code", "CompanyName", "MarketCode", "MarketCodeName",
        "Sector33Code", "Sector33CodeName"
    ])
    df["CompanyNameEnglish"] = ""
    df["Sector17Code"]       = ""
    df["Sector17CodeName"]   = ""
    df["ScaleCategory"]      = ""
    df["Badge"]      = df["MarketCode"].apply(_badge)
    df["DisplayCode"] = df.apply(
        lambda r: f"[{r['Badge']}] {r['Code']} {r['CompanyName']}", axis=1
    )
    logger.info(f"サンプル銘柄: {len(df)} 社")
    return df
