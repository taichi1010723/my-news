import os
import requests
import feedparser
import json
import re
import urllib.parse  # 修正ポイント：URLの変換用に追加
from google import genai

# 1. ニュースを集めたい4つのカテゴリと検索キーワード
CATEGORIES = {
    "広告": "広告 マーケティング ブランディング",
    "経済": "経済 景気 金利 為替",
    "世界企業情勢": "グローバル企業 海外ビジネス GAFA 巨大IT",
    "世界情勢": "国際情勢 アメリカ ヨーロッパ 中国 情勢"
}

def fetch_news(query):
    # 修正ポイント：キーワードの間のスペースをURLで使える形に安全に変換します
    encoded_query = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ja&gl=JP&ceid=JP:ja"
    feed = feedparser.parse(url)
    articles = []
    # 各カテゴリ最新10件を取得してAIに渡す
    for entry in feed.entries[:10]:
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

    if not all_news_text:
        print("ニュースデータを取得できませんでした。")
        return

    # 2. Gemini APIの準備
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Gemini APIキーが設定されていません。")
        return
        
    client = genai.Client(api_key=api_key)

    # 3. Geminiへの指示（プロンプト）の作成
    prompt = f"""
以下のニュース情報を元に、情報収集のための厳選ニュースまとめを作成してください。

ターゲットカテゴリ：
- 広告
- 経済
- 世界企業情勢
- 世界情勢

【条件】
1. 上記の4つのカテゴリごとに、特に重要だと思われるニュースを最大3つずつ厳選してください。
2. 厳選した各ニュースについて、「元のタイトルを分かりやすく補正したタイトル」「ニュースの重要なポイント3行（箇条書き）」「元のURL」を整理してください。
3. 出力は必ず以下のJSONフォーマットのみにしてください。それ以外の挨拶や解説のテキストは一切含めないでください。出力は ```json と ``` で囲んでください。

{{
  "slack": "Slackに投稿する用のテキスト。Markdown形式を使い、見出し（*や_など）や絵文字なども適度に入れて読みやすくスタイリッシュに装飾してください。",
  "html": "GitHub Pagesとして公開する用の、完全なHTMLコード。<!DOCTYPE html>から始めてください。Bootstrap5のCDNリンクを読み込み、ダークモード風（背景が暗め）の非常に見やすくオシャレなダッシュボード風デザインにしてください。ニュースのタイトルは元のURLへのリンク（<a>タグ、target='_blank'付き）にしてください。"
}}

【ニュース元データ】
{all_news_text}
"""

    # 4. Geminiに要約とHTMLの生成を依頼
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt
    )
    
    response_text = response.text

    # 5. 生成されたJSONデータを解析
    match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
    json_str = match.group(1) if match else response_text
    
    try:
        data = json.loads(json_str)
        slack_text = data.get("slack", "")
        html_text = data.get("html", "")
        
        # Slackへ通知
        slack_webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
        if slack_webhook_url and slack_text:
            payload = {"text": slack_text}
            requests.post(slack_webhook_url, json=payload)
            print("Slackへの通知が完了しました。")
            
        # HTMLファイルとして保存
        if html_text:
            with open("index.html", "w", encoding="utf-8") as f:
                f.write(html_text)
            print("index.htmlの保存が完了しました。")
            
    except Exception as e:
        print("JSONの解析、または処理中にエラーが発生しました:", e)
        print("Geminiの生応答:", response_text)

if __name__ == "__main__":
    main()
