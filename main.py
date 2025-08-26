import os
import json
import feedparser
import requests
import google.generativeai as genai
from utils import check_duplicate, download_image, post_fb_comment
from newspaper import Article

# -----------------------------
# 1️⃣ Configuration
# -----------------------------
RSS_FEED = os.environ.get("RSS_FEED_URL")
FB_PAGE_ID = os.environ.get("FB_PAGE_ID")
FB_ACCESS_TOKEN = os.environ.get("FB_ACCESS_TOKEN")
GEN_API_KEY = os.environ.get("GEMINI_API_KEY")
LOG_FILE = "posted_articles.json"

if not RSS_FEED:
    print("❌ RSS_FEED_URL not provided.")
    exit()

genai.configure(api_key=GEN_API_KEY)

# -----------------------------
# 2️⃣ Load posted articles
# -----------------------------
try:
    with open(LOG_FILE, "r") as f:
        posted_articles = json.load(f)
except:
    posted_articles = []

# -----------------------------
# 3️⃣ Fetch latest RSS entry
# -----------------------------
feed = feedparser.parse(RSS_FEED)
if not feed.entries:
    print("❌ No RSS entries found.")
    exit()

first_entry = feed.entries[0]
title = first_entry.title
article_url = first_entry.link

print("📰 Latest Article:", title)
print("🔗 URL:", article_url)

# -----------------------------
# 4️⃣ Duplicate check
# -----------------------------
if title in posted_articles or check_duplicate(title):
    print("⚠️ Already posted or duplicate. Skipping.")
    exit()

# -----------------------------
# 5️⃣ Extract full content
# -----------------------------
try:
    article = Article(article_url, language="bn")
    article.download()
    article.parse()
    full_content = article.text  # পুরো article content
except Exception as e:
    print("❌ Full content extraction failed:", e)
    full_content = title

# -----------------------------
# 6️⃣ Optional: Featured image
# -----------------------------
featured_image = None
try:
    if article.top_image:
        featured_image = article.top_image
except:
    featured_image = None

local_image = None
if featured_image:
    filename = "featured.jpg"
    if download_image(featured_image, filename):
        local_image = filename
        print("✅ Featured image downloaded:", filename)
    else:
        print("❌ Failed to download featured image")
else:
    print("⚠️ No featured image found")

# -----------------------------
# 7️⃣ Generate hashtags only
# -----------------------------
model = genai.GenerativeModel("gemini-2.5-flash")

hashtag_prompt = f"""
Generate 3-5 relevant Bengali hashtags for this news article.
Title: {title}
Full Content: {full_content}
"""
hashtag_resp = model.generate_content(hashtag_prompt)
hashtags = [tag.strip() for tag in hashtag_resp.text.split() if tag.startswith("#")]
hashtags_text = " ".join(hashtags)

# -----------------------------
# 8️⃣ Prepare FB post content
# -----------------------------
fb_content = f"📰 Original News: {title}\n\n{full_content}\n\n🔗 Source: {article_url}\n\n{hashtags_text}"
print("✅ FB Post Content Ready")

# -----------------------------
# 9️⃣ Post to Facebook
# -----------------------------
fb_result = []

if local_image:
    with open(local_image, "rb") as f:
        data = {
            "caption": fb_content,
            "access_token": FB_ACCESS_TOKEN
        }
        files = {"source": f}
        r = requests.post(f"https://graph.facebook.com/v17.0/{FB_PAGE_ID}/photos", data=data, files=files)
        fb_result.append(r.json())
        print("📤 Facebook Response:", r.json())
else:
    post_data = {"message": fb_content, "access_token": FB_ACCESS_TOKEN}
    r = requests.post(f"https://graph.facebook.com/v17.0/{FB_PAGE_ID}/feed", data=post_data)
    fb_result.append(r.json())
    print("📤 Facebook Response:", r.json())

# -----------------------------
# 🔟 Log successful post
# -----------------------------
posted_articles.append(title)
with open(LOG_FILE, "w") as f:
    json.dump(posted_articles, f)
