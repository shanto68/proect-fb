import os
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import google.generativeai as genai
from utils import check_duplicate, download_image, highlight_keywords, post_fb_comment

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
# 1️⃣ Load posted articles
# -----------------------------
try:
    with open(LOG_FILE, "r") as f:
        posted_articles = json.load(f)
except:
    posted_articles = []

# -----------------------------
# 2️⃣ Scrape the page
# -----------------------------
try:
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(PAGE_URL, headers=headers, timeout=10, verify=False)
    soup = BeautifulSoup(r.text, "html.parser")

    # Title & Link
    title_tag = soup.select_one("a.gPFEn")
    title = title_tag.text.strip()
    article_url = urljoin(PAGE_URL, title_tag.get("href"))

    # Source & Time
    source = soup.select_one("div.vr1PYe").text.strip() if soup.select_one("div.vr1PYe") else ""
    time_text = soup.select_one("time.hvbAAd").text.strip() if soup.select_one("time.hvbAAd") else ""

    # Images
    img_tags = soup.select("img.Quavad")
    candidate_images = []
    for img in img_tags:
        img_url = None
        if img.has_attr("data-src"):
            img_url = img["data-src"]
        elif img.has_attr("srcset"):
            srcset = img["srcset"].split(",")
            img_url = srcset[-1].split()[0]  # largest
        elif img.has_attr("src"):
            img_url = img["src"]
        if img_url:
            # If /api/attachments/... format, try replace low-res
            img_url = img_url.replace("-w280-h168", "-w1080-h720")
            img_url = urljoin(PAGE_URL, img_url)
            candidate_images.append(img_url)
except Exception as e:
    print("❌ Scraping failed:", e)
    exit()

print("📰 Latest Article:", title)
print("🔗 URL:", article_url)
print("🖼️ Candidate images:", candidate_images)

# -----------------------------
# 3️⃣ Duplicate check
# -----------------------------
if title in posted_articles or check_duplicate(title):
    print("⚠️ Already posted or duplicate. Skipping.")
    exit()

# -----------------------------
# 4️⃣ Download images (max 5)
# -----------------------------
local_images = []
for idx, img_url in enumerate(candidate_images):
    filename = f"img_{idx}.jpg"
    if download_image(img_url, filename):
        local_images.append(filename)
    if idx >= 4:
        break

print("✅ Local images downloaded:", local_images)

# -----------------------------
# 5️⃣ Generate FB content
# -----------------------------
model = genai.GenerativeModel("gemini-2.5-flash")

summary_prompt = f"""
নিচের নিউজ কনটেন্টকে বাংলায় ৩-৪ লাইনের আকর্ষণীয়,
human-like ফেসবুক পোস্ট স্টাইলে সাজাও। ইমোজি ব্যবহার করবে।
নিউজ কনটেন্ট:
---
{title}
Source: {source}
Time: {time_text}
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
# 6️⃣ Post to Facebook
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
# 7️⃣ Auto-comment
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
# 8️⃣ Log successful post
# -----------------------------
posted_articles.append(title)
with open(LOG_FILE, "w") as f:
    json.dump(posted_articles, f)
