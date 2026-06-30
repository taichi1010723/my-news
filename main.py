import os
import requests
import feedparser
import json
import re
import urllib.parse
from datetime import datetime
from google import genai

CATEGORIES = {
    "広告": "広告 マーケティング ブランディング",
    "経済": "経済 景気 金利 為替",
    "世界企業情勢": "グローバル企業 海外ビジネス GAFA 巨大IT",
    "世界情勢": "国際情勢 アメリカ ヨーロッパ 中国 情勢"
}

def fetch_news(query):
    encoded_query = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ja&gl=JP&ceid=JP:ja"
    feed = feedparser.parse(url)
    articles = []
    for entry in feed.entries[:8]:
        articles.append({
            "title": entry.title,
            "link": entry.link
        })
    return articles

def main():
    all_news_text = ""
    for category, query in CATEGORIES.items():
        articles = fetch_news(query)
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

    prompt = f"""
以下のニュース情報から、各カテゴリごとに重要なニュースを最大3つ厳選し、3行の箇条書きで要約してください。
出力は、必ず以下の構造のJSON形式（リスト）のみにしてください。他の解説は一切含めないでください。

[
  {{
    "category": "カテゴリ名",
    "title": "分かりやすく書き直したタイトル",
    "url": "元のURL",
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
                
        history_data = history_data[:150]
        
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(history_data, f, ensure_ascii=False, indent=2)
            
        print(f"新着ニュースを {added_count} 件蓄積しました。ニュースサイトが自動更新されます。")
        
    except Exception as e:
        print("処理中にエラーが発生しました:", e)

if __name__ == "__main__":
    main()
