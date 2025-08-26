import os
import json
import requests
import feedparser
from newspaper import Article
import google.generativeai as genai
from utils import check_duplicate, download_image, highlight_keywords, post_fb_comment
from urllib.parse import quote

# -----------------------------
# 1️⃣ Configuration
# -----------------------------
RSS_FEED_URL = os.environ.get("RSS_FEED_URL")
FB_PAGE_ID = os.environ.get("FB_PAGE_ID")
FB_ACCESS_TOKEN = os.environ.get("FB_ACCESS_TOKEN")
GEN_API_KEY = os.environ.get("GEMINI_API_KEY")
LOG_FILE = "posted_articles.json"

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
# 3️⃣ Parse RSS
# -----------------------------
feed = feedparser.parse(RSS_FEED_URL)
if not feed.entries:
    print("❌ RSS feed empty")
    exit()

latest = feed.entries[0]
title = latest.title
article_url = latest.link

print("📰 Latest Article:", title)
print("🔗 URL:", article_url)

# -----------------------------
# 4️⃣ Duplicate check
# -----------------------------
if title in posted_articles or check_duplicate(title):
    print("❌ Already posted or duplicate. Skipping.")
    exit()

# -----------------------------
# 5️⃣ Extract full content
# -----------------------------
try:
    article = Article(article_url, language='bn')
    article.download()
    article.parse()
    content = article.text.strip()
    if not content:
        content = title
except Exception as e:
    print("❌ Full content extraction failed:", e)
    content = title

# -----------------------------
# 6️⃣ Gemini AI summary
# -----------------------------
model = genai.GenerativeModel("gemini-2.5-flash")
summary_prompt = f"""
নিচের নিউজ কনটেন্টকে বাংলায় ৩–৪ লাইনের আকর্ষণীয়,
সহজবোধ্য, ফেসবুক পোস্ট স্টাইলে সাজাও। ইমোজি ব্যবহার করবে।
News Content: {content}
"""
summary_resp = model.generate_text(summary_prompt)
summary_text = summary_resp.text.strip()

# -----------------------------
# 7️⃣ Keyword highlight + hashtags
# -----------------------------
keywords = title.split()[:3]
highlighted_text = highlight_keywords(summary_text, keywords)

hashtag_prompt = f"""
Generate 3-5 relevant Bengali hashtags for this news article.
Title: {title}
Summary: {summary_text}
"""
hashtag_resp = model.generate_text(hashtag_prompt)
hashtags = [tag.strip() for tag in hashtag_resp.text.split() if tag.startswith("#")]
hashtags_text = " ".join(hashtags)

fb_content = f"{highlighted_text}\n\n{hashtags_text}"
print("✅ Generated FB Content:\n", fb_content)

# -----------------------------
# 8️⃣ Download high-res images
# -----------------------------
image_urls = []
try:
    article_html = requests.get(article_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10).text
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(article_html, "html.parser")
    imgs = soup.find_all("img")
    for img in imgs:
        srcset = img.get("srcset")
        if srcset:
            candidates = []
            for part in srcset.split(","):
                url_part, size_part = part.strip().split(" ")
                width = int(size_part.replace("w", ""))
                candidates.append((width, url_part))
            candidates.sort(reverse=True)
            image_urls.append(candidates[0][1])
        else:
            src = img.get("src")
            if src:
                image_urls.append(src)
except Exception as e:
    print("❌ Image extraction failed:", e)

# Remove duplicates
image_urls = list(dict.fromkeys(image_urls))
print("Detected images:", image_urls)

# Download locally
local_images = []
for i, url in enumerate(image_urls):
    filename = f"img_{i}.jpg"
    if download_image(url, filename):
        local_images.append(filename)

# -----------------------------
# 9️⃣ Post to Facebook (Album style)
# -----------------------------
fb_result = []
fb_api_url = f"https://graph.facebook.com/v17.0/{FB_PAGE_ID}/photos"

if local_images:
    for idx, img_file in enumerate(local_images):
        data = {"caption": fb_content if idx == 0 else "", "access_token": FB_ACCESS_TOKEN}
        files = {"source": open(img_file, 'rb')}
        r = requests.post(fb_api_url, data=data, files=files)
        fb_result.append(r.json())
else:
    # No images fallback: simple post
    post_data = {"message": fb_content, "access_token": FB_ACCESS_TOKEN}
    r = requests.post(f"https://graph.facebook.com/v17.0/{FB_PAGE_ID}/feed", data=post_data)
    fb_result.append(r.json())

print("📤 Facebook Response:", fb_result)

# -----------------------------
# 🔟 Auto-comment first photo
# -----------------------------
if local_images and fb_result:
    first_post_id = fb_result[0].get("id")
    if first_post_id:
        comment_prompt = f"""
        Article Title: {title}
        Summary: {summary_text}
        Write a short, friendly, engaging comment in Bengali with emojis.
        """
        comment_resp = model.generate_text(comment_prompt)
        comment_text = comment_resp.text.strip()
        print("💬 Generated Comment:\n", comment_text)
        post_fb_comment(first_post_id, comment_text)

# -----------------------------
# 1️⃣1️⃣ Log posted article
# -----------------------------
posted_articles.append(title)
with open(LOG_FILE, "w") as f:
    json.dump(posted_articles, f)
