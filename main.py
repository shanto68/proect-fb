import os
import json
import feedparser
import requests
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
# 5️⃣ Extract Full Content & Images
# -----------------------------
try:
    article = Article(article_url, language="bn")
    article.download()
    article.parse()
    full_content = article.text
    top_image = article.top_image
except Exception as e:
    print("❌ Full content extraction failed:", e)
    full_content = title
    top_image = None

# Collect candidate images
candidate_images = []
if hasattr(first_entry, "media_content"):
    for media in first_entry.media_content:
        img_url = media.get("url")
        if img_url:
            candidate_images.append(img_url)
if top_image:
    candidate_images.append(top_image)

print("Candidate images found:", candidate_images)

# -----------------------------
# Auto-detect highest resolution images
# -----------------------------
def pick_high_res(images):
    scored = []
    for url in images:
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            r = requests.head(url, timeout=5, headers=headers, verify=False)
            size = int(r.headers.get('Content-Length', 0))
            scored.append((size, url))
        except:
            scored.append((0, url))  # fallback
    if scored:
        scored.sort(reverse=True)
        return [url for size, url in scored]
    return images

high_res_images = pick_high_res(candidate_images)
print("High-res images selected:", high_res_images)

# -----------------------------
# Download images locally
# -----------------------------
local_images = []
for idx, img_url in enumerate(high_res_images):
    filename = f"img_{idx}.jpg"
    if download_image(img_url, filename):
        local_images.append(filename)
    if idx >= 4:  # max 5 images
        break
print("Local images downloaded:", local_images)

# -----------------------------
# 6️⃣ Generate FB Post Content
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
# 7️⃣ Post to Facebook
# -----------------------------
fb_api_url = f"https://graph.facebook.com/v17.0/{FB_PAGE_ID}/photos"
fb_result = []

if local_images:
    for idx, img_file in enumerate(local_images):
        with open(img_file, "rb") as f:
            data = {
                "access_token": FB_ACCESS_TOKEN,
                "published": "true" if idx == 0 else "false",
                "caption": fb_content if idx == 0 else ""
            }
            files = {"source": f}
            r = requests.post(fb_api_url, data=data, files=files)
            fb_result.append(r.json())

    # Publish remaining images as album
    if len(local_images) > 1:
        batch_ids = [res.get("id") for res in fb_result if res.get("id")]
        for photo_id in batch_ids[1:]:
            requests.post(
                f"https://graph.facebook.com/v17.0/{photo_id}",
                data={"published": "true", "access_token": FB_ACCESS_TOKEN}
            )
else:
    post_data = {"message": fb_content, "access_token": FB_ACCESS_TOKEN}
    r = requests.post(f"https://graph.facebook.com/v17.0/{FB_PAGE_ID}/feed", data=post_data)
    fb_result.append(r.json())

print("📤 Facebook Response:", fb_result)

# -----------------------------
# 8️⃣ Auto-comment
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
# 9️⃣ Log successful post
# -----------------------------
posted_articles.append(title)
with open(LOG_FILE, "w") as f:
    json.dump(posted_articles, f)
