import os
import json
import requests
import feedparser
from bs4 import BeautifulSoup
import google.generativeai as genai
from urllib.parse import quote

# -----------------------------
# 1️⃣ Configuration
# -----------------------------
FB_PAGE_ID = os.environ.get("FB_PAGE_ID")
FB_ACCESS_TOKEN = os.environ.get("FB_ACCESS_TOKEN")
GEN_API_KEY = os.environ.get("GEMINI_API_KEY")
RSS_URL = os.environ.get("RSS_URL")
LOG_FILE = "posted_articles.json"

if not all([FB_PAGE_ID, FB_ACCESS_TOKEN, GEN_API_KEY, RSS_URL]):
    raise ValueError("❌ Missing one or more environment variables!")

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
feed = feedparser.parse(RSS_URL)
if not feed.entries:
    print("❌ RSS feed empty!")
    exit()

latest = feed.entries[0]
title = latest.title
article_url = latest.link

if title in posted_articles:
    print("❌ Already posted. Skipping.")
    exit()

print("📰 Latest Article:", title)
print("🔗 URL:", article_url)

# -----------------------------
# 4️⃣ Get full content
# -----------------------------
try:
    resp = requests.get(article_url, timeout=10)
    soup = BeautifulSoup(resp.content, "html.parser")
    paragraphs = soup.find_all("p")
    full_text = " ".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
except:
    full_text = title  # fallback
if not full_text:
    full_text = title

# -----------------------------
# 5️⃣ Gemini AI summary & hashtags
# -----------------------------
model = genai.GenerativeModel("gemini-2.5-flash")

summary_prompt = f"""
নিচের নিউজ কনটেন্টকে বাংলায় ৩-৪ লাইনের আকর্ষণীয়, সহজবোধ্য, 
ফেসবুক পোস্ট স্টাইলে সাজাও। ইমোজি ব্যবহার করবে। 
Content: {full_text}
"""

summary_resp = model.generate_content(summary_prompt)
summary_text = summary_resp.text.strip()

hashtags_prompt = f"""
এই নিউজের জন্য ৩-৫টি প্রাসঙ্গিক বাংলা hashtag তৈরি করো।
Content: {summary_text}
"""
hashtags_resp = model.generate_content(hashtags_prompt)
hashtags = [tag.strip() for tag in hashtags_resp.text.split() if tag.startswith("#")]
hashtags_text = " ".join(hashtags)

fb_content = f"{summary_text}\n\n{hashtags_text}"
print("✅ Generated FB Content:\n", fb_content)

# -----------------------------
# 6️⃣ Extract images (highest res first)
# -----------------------------
soup = BeautifulSoup(resp.content, "html.parser")
img_tags = soup.find_all("img")
image_urls = []

for img in img_tags:
    srcset = img.get("srcset")
    if srcset:
        candidates = []
        for part in srcset.split(","):
            try:
                url_part, size_part = part.strip().split(" ")
                width = int(size_part.replace("w", ""))
                candidates.append((width, url_part))
            except:
                continue
        if candidates:
            candidates.sort(reverse=True)
            image_urls.append(candidates[0][1])
    else:
        src = img.get("src")
        if src:
            image_urls.append(src)

# Remove duplicates & take max 4 images
image_urls = list(dict.fromkeys(image_urls))[:4]
print("📷 Images found:", image_urls)

# -----------------------------
# 7️⃣ Download images
# -----------------------------
local_images = []
for i, url in enumerate(image_urls):
    filename = f"img_{i}.jpg"
    try:
        r = requests.get(url, stream=True, timeout=10)
        if r.status_code == 200:
            with open(filename, "wb") as f:
                for chunk in r.iter_content(1024):
                    f.write(chunk)
            local_images.append(filename)
    except:
        continue

# -----------------------------
# 8️⃣ Post to FB
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
# 9️⃣ Log article
# -----------------------------
posted_articles.append(title)
with open(LOG_FILE, "w") as f:
    json.dump(posted_articles, f)
