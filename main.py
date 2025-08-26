import os
import json
import requests       # << এইটা নতুন যোগ
import feedparser
import google.generativeai as genai
from utils import check_duplicate, download_image, highlight_keywords, post_fb_comment
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
# 3️⃣ Fetch RSS feed
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
# 5️⃣ Extract Full Content (newspaper3k)
# -----------------------------
try:
    article = Article(article_url, language="bn")
    article.download()
    article.parse()
    # article.nlp()  # NLP skip to avoid stopwords_bn.txt error
    full_content = article.text
    main_image = article.top_image
except Exception as e:
    print("❌ Full content extraction failed:", e)
    full_content = title
    main_image = None

# -----------------------------
# 6️⃣ Generate content with Gemini
# -----------------------------
model = genai.GenerativeModel("gemini-2.5-flash")

summary_prompt = f"""
নিচের নিউজ কনটেন্টকে বাংলায় এমনভাবে সাজাও,
যেন এটা ফেসবুক পোস্ট হিসেবে ব্যবহার করা যায়। 
ভাষা হবে সহজবোধ্য, আকর্ষণীয়, human-like, engaging।
ইমোজি ব্যবহার করবে। শেষে পাঠককে মন্তব্য করার মতো ছোট প্রশ্নও যোগ করবে।

নিউজ কনটেন্ট:
---
{full_content}
"""

summary_resp = model.generate_content(summary_prompt)
summary_text = summary_resp.text.strip()

# Keyword highlighting
keywords = title.split()[:3]
highlighted_text = highlight_keywords(summary_text, keywords)

# Hashtags
hashtag_prompt = f"""
Generate 3-5 relevant Bengali hashtags for this news article.
Title: {title}
Summary: {summary_text}
"""
hashtag_resp = model.generate_content(hashtag_prompt)
hashtags = [tag.strip() for tag in hashtag_resp.text.split() if tag.startswith("#")]
hashtags_text = " ".join(hashtags)

# Final FB post content
fb_content = f"{highlighted_text}\n\n{hashtags_text}"
print("✅ Generated FB Content:\n", fb_content)

# -----------------------------
# 7️⃣ Prepare Images
# -----------------------------
local_images = []
if main_image:
    if download_image(main_image, "img_0.jpg"):
        local_images.append("img_0.jpg")

if "media_content" in first_entry:
    for i, media in enumerate(first_entry.media_content):
        img_url = media.get("url")
        if img_url and download_image(img_url, f"img_{i+1}.jpg"):
            local_images.append(f"img_{i+1}.jpg")

# -----------------------------
# 8️⃣ Post to Facebook
# -----------------------------
fb_api_url = f"https://graph.facebook.com/v17.0/{FB_PAGE_ID}/photos"
fb_result = []

if local_images:
    for idx, img_file in enumerate(local_images):
        data = {"caption": fb_content if idx == 0 else "", "access_token": FB_ACCESS_TOKEN}
        files = {"source": open(img_file, "rb")}
        r = requests.post(fb_api_url, data=data, files=files)
        fb_result.append(r.json())
else:
    post_data = {"message": fb_content, "access_token": FB_ACCESS_TOKEN}
    r = requests.post(f"https://graph.facebook.com/v17.0/{FB_PAGE_ID}/feed", data=post_data)
    fb_result.append(r.json())

print("📤 Facebook Response:", fb_result)

# -----------------------------
# 9️⃣ Auto-comment
# -----------------------------
if fb_result:
    first_post_id = fb_result[0].get("id")
    if first_post_id:
        comment_prompt = f"""
        Article Title: {title}
        Summary: {summary_text}
        Write a short, friendly, engaging comment in Bengali for this Facebook post.
        Include emojis naturally.
        """
        comment_resp = model.generate_content(comment_prompt)
        comment_text = comment_resp.text.strip()
        print("💬 Generated Comment:\n", comment_text)
        post_fb_comment(first_post_id, comment_text)

# -----------------------------
# 🔟 Log successful post
# -----------------------------
posted_articles.append(title)
with open(LOG_FILE, "w") as f:
    json.dump(posted_articles, f)
