"""
J-Quants API V2 から東証全銘柄リストを取得して stocks.csv に保存するスクリプト

※ 2025年12月22日以降に登録したユーザーは V2 API（APIキー方式）のみ対応

事前準備:
  1. https://jpx-jquants.com にログイン
  2. ダッシュボード → 「APIキー」を発行
  3. .env に JQUANTS_API_KEY=発行されたキー を設定

実行:
  python data/fetch_stocks.py
"""
import os
import sys
import logging
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

JQUANTS_BASE_V2 = "https://api.jquants.com/v2"
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "stocks.csv")


def fetch_listed_info_v2(api_key: str) -> pd.DataFrame:
    """V2 API: x-api-key ヘッダーで認証して銘柄情報を取得"""
    # V2 エンドポイント: /equities/master（ページネーション対応）
    all_rows = []
    params = {}
    while True:
        resp = requests.get(
            f"{JQUANTS_BASE_V2}/equities/master",
            headers={"x-api-key": api_key},
            params=params,
            timeout=60,
        )
        resp.raise_for_status()
        body = resp.json()

        rows = body.get("data", [])
        all_rows.extend(rows)

        # ページネーション
        next_token = body.get("pagination_key")
        if not next_token:
            break
        params = {"pagination_key": next_token}

    df = pd.DataFrame(all_rows)

    # stock_db.py が期待するカラム名に統一
    df = df.rename(columns={
        "CoName":   "CompanyName",
        "CoNameEn": "CompanyNameEnglish",
        "Mkt":      "MarketCode",
        "MktNm":    "MarketCodeName",
        "S17":      "Sector17Code",
        "S17Nm":    "Sector17CodeName",
        "S33":      "Sector33Code",
        "S33Nm":    "Sector33CodeName",
        "ScaleCat": "ScaleCategory",
    })
    return df


def main():
    api_key = os.getenv("JQUANTS_API_KEY", "")

    if not api_key:
        logger.error(
            ".env に JQUANTS_API_KEY を設定してください。\n"
            "  取得方法: https://jpx-jquants.com にログイン → ダッシュボード → APIキー発行"
        )
        sys.exit(1)

    logger.info("J-Quants API V2 で銘柄リスト取得中...")
    df = fetch_listed_info_v2(api_key)

    if df.empty:
        logger.error("銘柄データを取得できませんでした。APIキーを確認してください。")
        sys.exit(1)

    # 東証3市場のみ抽出（ETF・REIT等を除外）
    # V2 API のコードは "0111" 形式
    if "MarketCode" in df.columns:
        df = df[df["MarketCode"].isin(["0111", "0112", "0113", "0114"])]

    df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
    logger.info(f"保存完了: {OUTPUT_PATH} ({len(df)} 銘柄)")

    # 市場別集計
    if "MarketCodeName" in df.columns:
        for market, count in df["MarketCodeName"].value_counts().items():
            logger.info(f"  {market}: {count} 社")


if __name__ == "__main__":
    main()
