import os
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
    import json
    with open(LOG_FILE, "r") as f:
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
# 4️⃣ Extract latest article
# -----------------------------
title_tag = soup.select_one("a.gPFEn")
if not title_tag:
    print("❌ No article found")
    exit()

title = title_tag.text.strip()
link = urljoin(PAGE_URL, title_tag["href"])

source_tag = soup.select_one("div.vr1PYe")
source = source_tag.text.strip() if source_tag else ""

time_tag = soup.select_one("time.hvbAAd")
time_text = time_tag.text.strip() if time_tag else ""

print("📰 Latest Article:", title)
print("🔗 URL:", link)
print("📌 Source:", source)
print("⏰ Time:", time_text)

# -----------------------------
# 5️⃣ Duplicate check
# -----------------------------
if title in posted_articles or check_duplicate(title):
    print("⚠️ Already posted or duplicate. Skipping.")
    exit()

# -----------------------------
# 6️⃣ Extract high-res image
# -----------------------------
def upgrade_attachment_url(url):
    if "-w" in url and "-h" in url:
        url = url.split("-w")[0] + "-w1080-h720"  # বড় resolution
    return url

img_tag = soup.select_one("img.Quavad")
img_url = None
if img_tag:
    if img_tag.has_attr("data-src"):
        img_url = img_tag["data-src"]
    elif img_tag.has_attr("srcset"):
        srcset = img_tag["srcset"].split(",")
        img_url = srcset[-1].split()[0]  # সর্বোচ্চ resolution
    elif img_tag.has_attr("src"):
        img_url = img_tag["src"]

if img_url:
    img_url = urljoin(PAGE_URL, img_url)
    img_url = upgrade_attachment_url(img_url)

# Fallback: og:image
if not img_url:
    meta_img = soup.find("meta", property="og:image")
    if meta_img:
        img_url = meta_img.get("content")
        img_url = upgrade_attachment_url(img_url)

print("🖼️ Image URL:", img_url)

# Download image locally
local_images = []
if img_url:
    if download_image(img_url, "img_0.jpg"):
        local_images.append("img_0.jpg")

# -----------------------------
# 7️⃣ Generate FB Content
# -----------------------------
model = genai.GenerativeModel("gemini-2.5-flash")

summary_prompt = f"""
নিচের নিউজ কনটেন্টকে বাংলায় ৩-৪ লাইনের আকর্ষণীয়, 
human-like ফেসবুক পোস্ট স্টাইলে সাজাও। ইমোজি ব্যবহার করবে।
নিউজ কনটেন্ট:
---
{title}
{source}
{time_text}
"""

summary_resp = model.generate_content(summary_prompt)
summary_text = summary_resp.text.strip()

keywords = title.split()[:3]
highlighted_text = highlight_keywords(summary_text, keywords)

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
# 8️⃣ Post to Facebook
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
# 10️⃣ Log successful post
# -----------------------------
posted_articles.append(title)
with open(LOG_FILE, "w") as f:
    import json
    json.dump(posted_articles, f)
