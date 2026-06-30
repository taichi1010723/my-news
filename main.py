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

        # 既存の蓄積データを読み込み
        history_file = "news_data.json"
        if os.path.exists(history_file):
            with open(history_file, "r", encoding="utf-8") as f:
                try:
                    history_data = json.load(f)
                except:
                    history_data = []
        else:
            history_data = []
            
        # 重複排除しながら先頭（最新）に追加
        existing_urls = {story["url"] for story in history_data}
        added_count = 0
        newly_added_stories = []
        for story in new_stories:
            if story["url"] not in existing_urls:
                history_data.insert(0, story)
                newly_added_stories.append(story)
                added_count += 1
                
        # 溜まりすぎ防止（最新150件まで保持）
        history_data = history_data[:150]
        
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(history_data, f, ensure_ascii=False, indent=2)
            
        print(f"新着ニュースを {added_count} 件蓄積しました。")
        
        # 【復活！】新着ニュースがある場合のみ、綺麗に装飾してSlackに送信
        if added_count > 0:
            slack_webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
            if slack_webhook_url:
                slack_text = "📢 *【本日の厳選ニュースサマリー】* 📢\n━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                
                # カテゴリごとに分類
                cat_stories = {}
                for story in newly_added_stories:
                    cat = story["category"]
                    if cat not in cat_stories:
                        cat_stories[cat] = []
                    cat_stories[cat].append(story)
                
                emojis = {"広告": "🎨", "経済": "📈", "世界企業情勢": "🌐", "世界情勢": "🌍"}
                
                for cat, stories in cat_stories.items():
                    emoji = emojis.get(cat, "📄")
                    slack_text += f"\n{emoji} *{cat}*\n"
                    for idx, story in enumerate(stories, 1):
                        slack_text += f"{idx}. *{story['title']}*\n"
                        for s in story["summary"]:
                            slack_text += f"   • {s}\n"
                        slack_text += f"   🔗 <{story['url']}|記事を詳しく読む>\n"
                
                slack_text += "\n━━━━━━━━━━━━━━━━━━━━━━━━━\n💡 *マイニュースルームWebサイト（お気に入り・既読機能付き）も更新されました！*"
                
                payload = {"text": slack_text}
                response_slack = requests.post(slack_webhook_url, json=payload)
                if response_slack.status_code == 200:
                    print("Slackへの通知が完了しました。")
                else:
                    print(f"Slack送信エラー: {response_slack.status_code} - {response_slack.text}")
            else:
                print("SLACK_WEBHOOK_URL が設定されていません。")
        else:
            print("新着ニュースがなかったため、Slack通知はスキップされました。")
        
    except Exception as e:
        print("処理中にエラーが発生しました:", e)
        print("生応答:", response_text)

if __name__ == "__main__":
    main()
