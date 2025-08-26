import os
import json
import feedparser
import requests
import google.generativeai as genai
from utils import check_duplicate, download_image, highlight_keywords, post_fb_comment
from newspaper import Article
from bs4 import BeautifulSoup

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
# 5️⃣ Extract Full Content
# -----------------------------
try:
    article = Article(article_url, language="bn")
    article.download()
    article.parse()
    full_content = article.text
except Exception as e:
    print("❌ Full content extraction failed:", e)
    full_content = title

# -----------------------------
# 6️⃣ Fetch candidate images from RSS + Article + HTML
# -----------------------------
candidate_images = []

# 1️⃣ RSS media content
if hasattr(first_entry, "media_content"):
    for media in first_entry.media_content:
        img_url = media.get("url")
        if img_url:
            candidate_images.append(img_url)

# 2️⃣ Newspaper top image
if hasattr(article, "top_image") and article.top_image:
    candidate_images.append(article.top_image)

# 3️⃣ All <img> tags from HTML
try:
    html = requests.get(article_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10).text
    soup = BeautifulSoup(html, "html.parser")
    for img in soup.find_all("img"):
        img_url = img.get("src")
        if img_url and any(img_url.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".webp", ".png"]):
            candidate_images.append(img_url)
except Exception as e:
    print("⚠️ Failed to fetch images from HTML:", e)

# Remove duplicates
candidate_images = list(dict.fromkeys(candidate_images))
print("Candidate images found:", candidate_images)

# -----------------------------
# Pick first valid image
# -----------------------------
featured_image = None
for img_url in candidate_images:
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.head(img_url, timeout=5, headers=headers, verify=False)
        if r.status_code == 200 and 'image' in r.headers.get('Content-Type', ''):
            featured_image = img_url
            break
    except:
        continue

print("Featured image selected:", featured_image)

# -----------------------------
# Download featured image
# -----------------------------
local_image = None
if featured_image:
    filename = "featured.jpg"
    if download_image(featured_image, filename):
        local_image = filename
        print("✅ Image downloaded:", filename)
    else:
        print("❌ Failed to download featured image")
else:
    print("⚠️ No valid image found")

# -----------------------------
# 7️⃣ Generate FB Post Content
# -----------------------------
model = genai.GenerativeModel("gemini-2.5-flash")

# --- Summary ---
summary_prompt = f"""
নিচের নিউজ কনটেন্টকে বাংলায় ৩-৪ লাইনের আকর্ষণীয়, 
human-like ফেসবুক পোস্ট স্টাইলে সাজাও। ইমোজি ব্যবহার করবে।
নিউজ কনটেন্ট:
---
{full_content}
"""
summary_resp = model.generate_content(summary_prompt)
summary_text = summary_resp.text.strip()

# Highlight keywords
keywords = title.split()[:3]
highlighted_text = highlight_keywords(summary_text, keywords)

# --- Hashtags ---
hashtag_prompt = f"""
Generate 3-5 relevant Bengali hashtags for this news article.
Title: {title}
Summary: {summary_text}
"""
hashtag_resp = model.generate_content(hashtag_prompt)
hashtags = [tag.strip() for tag in hashtag_resp.text.split() if tag.startswith("#")]
hashtags_text = " ".join(hashtags)

fb_content = f"{highlighted_text}\n\n{hashtags_text}"
print("✅ Generated FB Content:\n", fb_content)

# -----------------------------
# 8️⃣ Post to Facebook (single image)
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
