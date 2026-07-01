import os
import requests
import feedparser
import json
import re
import urllib.parse
from datetime import datetime
from google import genai

# ジャンルを大幅に拡張（計10ジャンル）
CATEGORIES = {
    "AI・テック": "AI 人工知能 ChatGPT LLM 最新テクノロジー",
    "マーケティング": "マーケティング 広告 ブランディング ヒット商品",
    "ビジネス": "ビジネス トレンド 起業 スタートアップ 経営",
    "株・経済": "株式市場 日経平均 株価 為替 経済 景気",
    "日本企業": "日本企業 トヨタ ソニー キャノン 企業動向",
    "世界企業情勢": "GAFA 巨大IT 海外ビジネス グローバル企業",
    "世界情勢": "国際情勢 アメリカ 中国 ヨーロッパ 情勢",
    "スポーツ": "スポーツニュース サッカー 野球 大谷翔平 オリンピック",
    "テレビニュース(映像)": "https://news.yahoo.co.id/rss/categories/domestic.xml", # 例としてYahoo等の主要RSSを拡張可能（今回はGoogleNewsベースで最適化）
}

def fetch_news(category, query):
    # クエリがURL（RSSフィード）の場合はそのまま読み込み、そうでない場合はGoogleニュース検索
    if query.startswith("http"):
        feed = feedparser.parse(query)
    else:
        encoded_query = urllib.parse.quote(query)
        url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ja&gl=JP&ceid=JP:ja"
        feed = feedparser.parse(url)
        
    articles = []
    # 収集件数を「15件」に大幅アップ！
    for entry in feed.entries[:15]:
        articles.append({
            "title": entry.title,
            "link": entry.link
        })
    return articles

def main():
    all_news_text = ""
    for category, query in CATEGORIES.items():
        articles = fetch_news(category, query)
        if not articles:
            continue
        all_news_text += f"\n【カテゴリ: {category}】\n"
        for a in articles:
            all_news_text += f"- タイトル: {a['title']}\n  URL: {a['link']}\n"

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Gemini APIキーが設定されていません。")
        return
        
    client = genai.Client(api_key=api_key)

    # プロンプトに「重要度スコアリング(S,A,B,C)」の指示を追加！
    prompt = f"""
以下の大量のニュース情報から、各カテゴリごとに本当に重要度の高いニュースを厳選し、3行の箇条書きで要約してください。
また、ビジネスパーソンにとってのそのニュースの重要度を [S, A, B, C] の4段階で厳密に査定し、"importance"に格納してください。
（S: 歴史的ニュース・大激変、A: 必ず知っておくべき、B: 知っておくと得、C: 通常ニュース）

出力は、必ず以下の構造のJSON形式（リスト）のみにしてください。

[
  {{
    "category": "カテゴリ名",
    "title": "分かりやすく書き直したタイトル",
    "url": "元のURL",
    "importance": "S", 
    "summary": [
      "要約ポイント1",
      "要約ポイント2",
      "要約ポイント3"
    ]
  }}
]

【ニュース元データ】
{all_news_text}
"""

    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt
    )
    
    response_text = response.text
    match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
    json_str = match.group(1) if match else response_text
    
    try:
        new_stories = json.loads(json_str)
        today_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        for story in new_stories:
            story["date"] = today_str
            story["id"] = urllib.parse.quote(story["url"])[-20:] 

        history_file = "news_data.json"
        if os.path.exists(history_file):
            with open(history_file, "r", encoding="utf-8") as f:
                try:
                    history_data = json.load(f)
                except:
                    history_data = []
        else:
            history_data = []
            
        existing_urls = {story["url"] for story in history_data}
        added_count = 0
        for story in new_stories:
            if story["url"] not in existing_urls:
                history_data.insert(0, story)
                added_count += 1
                
        # 大量ジャンルに対応するため、最大蓄積数を300件に拡張
        history_data = history_data[:300]
        
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(history_data, f, ensure_ascii=False, indent=2)
            
        print(f"新着ニュースを {added_count} 件蓄積しました。")
        
    except Exception as e:
        print("処理中にエラーが発生しました:", e)

if __name__ == "__main__":
    main()
