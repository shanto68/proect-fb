import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import google.generativeai as genai
from utils import download_image, highlight_keywords, post_fb_comment
import json
from datetime import datetime, timedelta

# -----------------------------
# 1️⃣ Configuration
# -----------------------------
PAGE_URL = os.environ.get("PAGE_URL")
FB_PAGE_ID = os.environ.get("FB_PAGE_ID")
FB_ACCESS_TOKEN = os.environ.get("FB_ACCESS_TOKEN")
GEN_API_KEY = os.environ.get("GEMINI_API_KEY")
LOG_FILE = "posted_articles.json"

if not PAGE_URL:
    print("❌ PAGE_URL not provided.")
    exit()

genai.configure(api_key=GEN_API_KEY)

# -----------------------------
# 2️⃣ Load / Create posted_articles.json
# -----------------------------
if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, "w") as f:
        json.dump([], f)

with open(LOG_FILE, "r") as f:
    try:
        posted_articles = json.load(f)
    except:
        posted_articles = []

# -----------------------------
# 3️⃣ Scrape page
# -----------------------------
try:
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(PAGE_URL, headers=headers, verify=False, timeout=10)
    soup = BeautifulSoup(r.text, "html.parser")
except Exception as e:
    print("❌ Page fetch failed:", e)
    exit()

# -----------------------------
# 4️⃣ Extract multiple recent articles (last 1 hour)
# -----------------------------
recent_articles = []
one_hour_ago = datetime.now() - timedelta(hours=1)

article_tags = soup.select("a.gPFEn")  # adjust selector as needed
time_tags = soup.select("time.hvbAAd")

for idx, title_tag in enumerate(article_tags):
    try:
        title = title_tag.text.strip()
        link = urljoin(PAGE_URL, title_tag["href"])
        time_tag = time_tags[idx] if idx < len(time_tags) else None
        time_text = time_tag.text.strip() if time_tag else ""
        # Optional: parse time_text to datetime and filter by last 1 hour
        if link not in posted_articles:
            recent_articles.append({
                "title": title,
                "link": link,
                "time_text": time_text
            })
    except:
        continue

if not recent_articles:
    print("⚠️ No new articles to post.")
    exit()

print(f"📰 {len(recent_articles)} new articles found.")

# -----------------------------
# 5️⃣ AI Priority / Trending Scoring
# -----------------------------
def score_article(article):
    prompt = f"""
    Title: {article['title']}
    Time: {article['time_text']}
    Determine engagement potential on Facebook. 
    Give score 1-10 (10=highest). 
    Respond ONLY with a number.
    """
    model = genai.GenerativeModel("gemini-2.5-flash")
    try:
        resp = model.generate_content(prompt)
        score = int(resp.text.strip())
    except:
        score = 5  # default medium priority
    return score

for article in recent_articles:
    article['score'] = score_article(article)

# Sort by score descending
recent_articles = sorted(recent_articles, key=lambda x: x['score'], reverse=True)

# -----------------------------
# 6️⃣ Process high-priority articles (score >=6)
# -----------------------------
for article in recent_articles:
    if article['score'] < 6:
        print(f"⚠️ Skipping low-priority article: {article['title']}")
        continue

    title = article['title']
    link = article['link']
    time_text = article['time_text']

    # -----------------------------
    # 7️⃣ Extract high-res image
    # -----------------------------
    img_tag = soup.find("img", {"alt": title})
    img_url = None
    if img_tag:
        if img_tag.has_attr("data-src"):
            img_url = img_tag["data-src"]
        elif img_tag.has_attr("srcset"):
            srcset = img_tag["srcset"].split(",")
            img_url = srcset[-1].split()[0]
        elif img_tag.has_attr("src"):
            img_url = img_tag["src"]

    if img_url:
        img_url = urljoin(PAGE_URL, img_url)

    local_images = []
    if img_url:
        if download_image(img_url, "img_0.jpg"):
            local_images.append("img_0.jpg")

    # -----------------------------
    # 8️⃣ AI Content Generation
    # -----------------------------
    summary_prompt = f"""
    নিচের নিউজ কনটেন্টকে বাংলায় **সরাসরি, আকর্ষণীয় এবং বিস্তারিত ফেসবুক পোস্ট স্টাইলে** সাজাও। 
    - যতটা সম্ভব news cover করবে। 
    - ৩-৪ লাইনের সীমাবদ্ধতা নেই। 
    - কখনো intro বা spoiler text যোগ করা হবে না। 
    - Human-like, engaging tone হবে। 
    - Natural emojis ব্যবহার করবে। 
    - পোস্ট শেষে মানুষকে comment করতে উদ্দীপিত করবে, যেমন: 'আপনার মতামত কমেন্টে জানান 👇'

    নিউজ কনটেন্ট:
    ---
    {title}
    {time_text}
    """

    model = genai.GenerativeModel("gemini-2.5-flash")
    summary_resp = model.generate_content(summary_prompt)
    summary_text = summary_resp.text.strip()

    # Highlight keywords
    keywords = title.split()[:3]
    highlighted_text = highlight_keywords(summary_text, keywords)

    # Generate hashtags
    hashtag_prompt = f"""
    Generate 3-5 relevant Bengali hashtags for this news article.
    Title: {title}
    Summary: {summary_text}
    """
    hashtag_resp = model.generate_content(hashtag_prompt)
    hashtags = [tag.strip() for tag in hashtag_resp.text.split() if tag.startswith("#")]
    hashtags_text = " ".join(hashtags)

    # Engagement booster: AI discussion-starter question
    question_prompt = f"""
    Generate a short, friendly discussion-starter question in Bengali 
    for the above post to encourage comments. Include emojis naturally.
    """
    question_resp = model.generate_content(question_prompt)
    discussion_question = question_resp.text.strip()

    fb_content = f"{highlighted_text}\n\n{hashtags_text}\n\n💬 {discussion_question}"
    print("✅ Generated FB Content:\n", fb_content)

    # -----------------------------
    # 9️⃣ Post to Facebook
    # -----------------------------
    fb_api_url = f"https://graph.facebook.com/v17.0/{FB_PAGE_ID}/photos"
    fb_result = []

    if local_images:
        for idx, img_file in enumerate(local_images):
            data = {"caption": fb_content if idx == 0 else "", "access_token": FB_ACCESS_TOKEN}
            with open(img_file, "rb") as f:
                files = {"source": f}
                r = requests.post(fb_api_url, data=data, files=files)
            fb_result.append(r.json())
    else:
        post_data = {"message": fb_content, "access_token": FB_ACCESS_TOKEN}
        r = requests.post(f"https://graph.facebook.com/v17.0/{FB_PAGE_ID}/feed", data=post_data)
        fb_result.append(r.json())

    print("📤 Facebook Response:", fb_result)

    # -----------------------------
    # 🔟 Auto-comment
    # -----------------------------
    if fb_result:
        first_post_id = fb_result[0].get("id")
        if first_post_id:
            comment_prompt = f"""
            Article Title: {title}
            Summary: {summary_text}
            Write a short, friendly, engaging comment in Bengali for this Facebook post.
            Include emojis naturally to encourage user engagement.
            """
            comment_resp = model.generate_content(comment_prompt)
            comment_text = comment_resp.text.strip()
            print("💬 Generated Comment:\n", comment_text)
            post_fb_comment(first_post_id, comment_text)

    # -----------------------------
    # 1️⃣1️⃣ Log successful post
    # -----------------------------
    posted_articles.append(link)
    with open(LOG_FILE, "w") as f:
        json.dump(posted_articles, f, ensure_ascii=False, indent=2)
