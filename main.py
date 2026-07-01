import os
import requests
import feedparser
import json
import re
import urllib.parse
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from google import genai
from PIL import Image, ImageDraw, ImageFont

# 10ジャンルに大幅拡張
CATEGORIES = {
    "AI・テック": "AI 人工知能 ChatGPT LLM 最新テクノロジー",
    "マーケティング": "マーケティング 広告 ブランディング ヒット商品",
    "ビジネス": "ビジネス トレンド 起業 経営",
    "株・経済": "株式市場 日経平均 株価 為替 経済 景気",
    "日本企業": "日本企業 トヨタ ソニー スタートアップ 企業動向",
    "世界企業情勢": "GAFA 巨大IT 海外ビジネス グローバル企業",
    "世界情勢": "国際情勢 アメリカ 中国 ヨーロッパ 情勢",
    "スポーツ": "スポーツニュース サッカー 野球 大谷翔平"
}

def fetch_news(query):
    encoded_query = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ja&gl=JP&ceid=JP:ja"
    feed = feedparser.parse(url)
    return [{"title": entry.title, "link": entry.link} for entry in feed.entries[:15]]

def create_summary_image(stories, output_path):
    """ニュースを1枚のペライチ画像(JPEG)にまとめる関数"""
    img = Image.new('RGB', (800, 1000), color='#1e1e2e')
    draw = ImageDraw.Draw(img)
    
    # エラー回避のため、確実な日本語フォントのURLから自動調達する
    font_url = "https://raw.githubusercontent.com/shogo82148/fonts-noto-sans-jp/master/NotoSansJP-Regular.ttf"
    font_path = "NotoSansJP-Regular.ttf"
    
    font_main = None
    font_title = None
    
    if not os.path.exists(font_path):
        try:
            print("日本語フォントを自動ダウンロード中...")
            r = requests.get(font_url, timeout=15)
            if r.status_code == 200:
                with open(font_path, 'wb') as f:
                    f.write(r.content)
        except Exception as e:
            print(f"フォントダウンロードエラー: {e}")

    if os.path.exists(font_path):
        try:
            font_main = ImageFont.truetype(font_path, 18)
            font_title = ImageFont.truetype(font_path, 28)
        except:
            pass

    if not font_main:
        font_main = ImageFont.load_default()
        font_title = ImageFont.load_default()

    # タイトル描画
    yesterday = (datetime.now() + timedelta(hours=9) - timedelta(days=1)).strftime("%Y-%m-%d")
    draw.text((40, 40), f"DAILY NEWS DIGEST ({yesterday})", fill='#ff79c6', font=font_title)
    draw.line([(40, 90), (760, 90)], fill='#6272a4', width=2)
    
    # S級・A級の重要ニュースをピックアップして描画
    important_stories = [s for s in stories if s.get("importance") in ["S", "A"]][:6]
    y_offset = 120
    
    if not important_stories:
        important_stories = stories[:6]
        
    for idx, story in enumerate(important_stories, 1):
        draw.rectangle([40, y_offset, 760, y_offset + 120], outline='#44475a', width=1)
        imp = story.get("importance", "A")
        badge_color = '#ff5555' if imp == "S" else '#ffb86c'
        draw.rectangle([50, y_offset + 15, 140, y_offset + 40], fill=badge_color)
        draw.text((60, y_offset + 18), f"重要度 {imp}", fill='#1e1e2e', font=font_main)
        draw.text((155, y_offset + 18), f"[{story['category']}]", fill='#8be9fd', font=font_main)
        
        title_text = story['title']
        if len(title_text) > 32: title_text = title_text[:32] + "..."
        draw.text((50, y_offset + 55), f"{idx}. {title_text}", fill='#f8f8f2', font=font_main)
        
        sum_text = story['summary'][0] if story['summary'] else ""
        if len(sum_text) > 38: sum_text = sum_text[:38] + "..."
        draw.text((50, y_offset + 85), f"• {sum_text}", fill='#bd93f9', font=font_main)
        
        y_offset += 140
        
    img.save(output_path, 'JPEG')

def send_gmail(subject, body_text, image_path=None):
    """Gmailを送信する関数"""
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
    if not gmail_user or not gmail_password:
        print("Gmailの認証情報が設定されていないため、メール送信をスキップします。")
        return

    msg = MIMEMultipart()
    msg['From'] = gmail_user
    msg['To'] = gmail_user
    msg['Subject'] = subject
    msg.attach(MIMEText(body_text, 'html'))

    if image_path and os.path.exists(image_path):
        with open(image_path, 'rb') as f:
            img_data = f.read()
        image = MIMEImage(img_data, name=os.path.basename(image_path))
        msg.attach(image)

    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(gmail_user, gmail_password)
        server.send_message(msg)
        server.close()
        print("Gmailの送信に成功しました！")
    except Exception as e:
        print("Gmail送信エラー:", e)

def main():
    all_news_text = ""
    for category, query in CATEGORIES.items():
        articles = fetch_news(query)
        if not articles: continue
        all_news_text += f"\n【カテゴリ: {category}】\n"
        for a in articles:
            all_news_text += f"- タイトル: {a['title']}\n  URL: {a['link']}\n"

    api_key = os.environ.get("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)

    prompt = f"""
以下の大量のニュースから、各カテゴリごとに重要なニュースを厳選し、3行の箇条書きで要約してください。
ビジネス視点での重要度を [S, A, B, C] の4段階で厳密に査定し、"importance"に格納してください。

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

    response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
    
    try:
        json_str = re.search(r'```json\s*(.*?)\s*```', response.text, re.DOTALL).group(1)
        new_stories = json.loads(json_str)
        
        jst_now = datetime.now() + timedelta(hours=9)
        today_str = jst_now.strftime("%Y-%m-%d %H:%M")
        for story in new_stories:
            story["date"] = today_str
            story["id"] = urllib.parse.quote(story["url"])[-20:] 

        # サイト用データの蓄積
        history_file = "news_data.json"
        if os.path.exists(history_file):
            with open(history_file, "r", encoding="utf-8") as f: history_data = json.load(f)
        else: history_data = []
            
        existing_urls = {story["url"] for story in history_data}
        added_stories = [s for s in new_stories if s["url"] not in existing_urls]
        
        for story in added_stories: history_data.insert(0, story)
        with open(history_file, "w", encoding="utf-8") as f: json.dump(history_data[:300], f, ensure_ascii=False, indent=2)
        
        print(f"新着ニュースを {len(added_stories)} 件蓄積しました。")

        # --- メール送信 ＆ 画像生成の処理 ---
        current_hour = jst_now.hour
        if 5 <= current_hour <= 9:
            time_tag, subject_title = "朝刊", "🌅【朝刊】前日ダイジェスト＆最重要ニュースサマリー"
            image_path = "daily_digest.jpg"
            create_summary_image(new_stories, image_path)
        elif 11 <= current_hour <= 14:
            time_tag, subject_title, image_path = "昼刊", "☀️【昼刊】ビジネス・テック最新ニュース速報", None
        else:
            time_tag, subject_title, image_path = "夜刊", "🌙【夜刊】今日の重要ニュースまとめ＆明日の展望", None

        # メール本文のHTML組み立て
        email_body = f"{subject_title}配信時刻: {today_str}"
        for story in new_stories:
            if story.get("importance") in ["S", "A", "B"]:
                imp_emoji = "🔥 [S級]" if story['importance'] == "S" else "⭐ [A級]" if story['importance'] == "A" else "📌 [B級]"
                email_body += f"{imp_emoji} [{story['category']}] {story['title']}"
                email_body += "" + "".join([f"{s}" for s in story['summary']]) + ""
                email_body += f"👉 記事を読む"
        
        email_body += "💡 全ジャンルの閲覧・お気に入り管理はこちらから：マイニュースルーム公式サイト"

        send_gmail(f"{subject_title} ({today_str})", email_body, image_path)
            
    except Exception as e:
        print("エラー発生:", e)

if __name__ == "__main__":
    main()
