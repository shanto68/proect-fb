import os
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import google.generativeai as genai
from utils import check_duplicate, download_image, highlight_keywords, post_fb_comment

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
# 2️⃣ Load posted articles
# -----------------------------
try:
    with open(LOG_FILE, "r") as f:
        posted_articles = json.load(f)
except:
    posted_articles = []

# -----------------------------
# 3️⃣ Scrape page
# -----------------------------
headers = {"User-Agent": "Mozilla/5.0"}
r = requests.get(PAGE_URL, headers=headers, verify=False)
soup = BeautifulSoup(r.text, "html.parser")

# Extract title, link, image
title_tag = soup.select_one("a.gPFEn")
if not title_tag:
    print("❌ Title not found")
    exit()
title = title_tag.get_text(strip=True)
article_url = title_tag.get("href")
article_url = urljoin(PAGE_URL, article_url)

img_tag = soup.select_one("img.Quavad")
if img_tag:
    img_url = img_tag.get("src")
    img_url = urljoin(PAGE_URL, img_url)  # Convert relative to full URL
else:
    img_url = None

print("📰 Latest Article:", title)
print("🔗 URL:", article_url)
print("🖼️ Image URL:", img_url)

# -----------------------------
# 4️⃣ Duplicate check
# -----------------------------
if title in posted_articles or check_duplicate(title):
    print("⚠️ Already posted or duplicate. Skipping.")
    exit()

# -----------------------------
# 5️⃣ Download image
# -----------------------------
local_images = []
if img_url:
    filename = "img_0.jpg"
    if download_image(img_url, filename):
        local_images.append(filename)

print("Local images downloaded:", local_images)

# -----------------------------
# 6️⃣ Generate FB Post Content
# -----------------------------
model = genai.GenerativeModel("gemini-2.5-flash")

summary_prompt = f"""
নিচের নিউজ কনটেন্টকে বাংলায় ৩-৪ লাইনের আকর্ষণীয়, 
human-like ফেসবুক পোস্ট স্টাইলে সাজাও। ইমোজি ব্যবহার করবে। 
News Title: {title}
Article URL: {article_url}
"""

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

fb_content = f"{highlighted_text}\n\n{hashtags_text}"
print("✅ Generated FB Content:\n", fb_content)

# -----------------------------
# 7️⃣ Post to Facebook
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
