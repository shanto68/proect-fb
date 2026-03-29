import os
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import google.generativeai as genai
from utils import download_image, highlight_keywords, post_fb_comment
import json
import traceback

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
    exit(1)

genai.configure(api_key=GEN_API_KEY)

# -----------------------------
# 2️⃣ Load posted logs
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
    exit(1)

# -----------------------------
# 4️⃣ Extract article
# -----------------------------
title_tag = soup.select_one("a.gPFEn")
if not title_tag:
    print("❌ No article found")
    exit(1)

title = title_tag.text.strip()
link = urljoin(PAGE_URL, title_tag["href"])

source_tag = soup.select_one("div.vr1PYe")
source = source_tag.text.strip() if source_tag else ""

time_tag = soup.select_one("time.hvbAAd")
time_text = time_tag.text.strip() if time_tag else ""

print("📰", title)

# Duplicate check
if any(link in x or title in x for x in posted_articles):
    print("⚠️ Already posted")
    exit(0)

# -----------------------------
# 5️⃣ Image extract
# -----------------------------
def upgrade_attachment_url(url):
    return re.sub(r'([-=])w\d+-h\d+', r'\1w1080-h720', url)

img_tag = soup.select_one("img.Quavad")
img_url = None

if img_tag:
    if img_tag.get("data-src"):
        img_url = img_tag["data-src"]
    elif img_tag.get("srcset"):
        img_url = img_tag["srcset"].split(",")[-1].split()[0]
    elif img_tag.get("src"):
        img_url = img_tag["src"]

if img_url:
    img_url = urljoin(PAGE_URL, img_url)
    img_url = upgrade_attachment_url(img_url)

if not img_url:
    meta_img = soup.find("meta", property="og:image")
    if meta_img:
        img_url = upgrade_attachment_url(meta_img.get("content"))

local_images = []
if img_url and download_image(img_url, "img_0.jpg"):
    local_images.append("img_0.jpg")

# -----------------------------
# 6️⃣ AI Content Generate (SAFE)
# -----------------------------
model = genai.GenerativeModel("gemini-2.5-flash")

try:
    paragraph_prompt = f"""
নিউজকে viral Facebook পোস্ট বানাও।

STRICT:
- intro/explain না
- hook দিয়ে শুরু
- short paragraph
- emoji use
- CTA শেষে

NEWS:
{title}
{source}
{time_text}
"""

    resp = model.generate_content(paragraph_prompt)
    paragraph_text = resp.text.strip()
except:
    paragraph_text = f"😱 {title}\n\nবিস্তারিত জানুন...\n\n💬 মতামত দিন!"

# Clean
paragraph_text = re.sub(r"^.*?(😱|🔥|🚨|💥)", r"\1", paragraph_text, flags=re.DOTALL)
paragraph_text = paragraph_text.replace("---", "")

# Highlight
keywords = title.split()[:3]
highlighted_text = highlight_keywords(paragraph_text, keywords)

# -----------------------------
# 7️⃣ Hashtags
# -----------------------------
try:
    hashtag_resp = model.generate_content(f"Generate 5 Bengali hashtags for: {title}")
    hashtags = [t for t in hashtag_resp.text.split() if t.startswith("#")]
    hashtags_text = " ".join(hashtags)
except:
    hashtags_text = "#BreakingNews #BanglaNews"

# -----------------------------
# 8️⃣ Final FB Post
# -----------------------------
fb_content = f"""
🔥 {highlighted_text}

💬 আপনার কী মনে হয়? কমেন্টে জানান 👇
📤 শেয়ার করুন!

{hashtags_text}
"""

print("📄 POST:\n", fb_content)

# -----------------------------
# 9️⃣ Post to Facebook
# -----------------------------
fb_result = []

try:
    if local_images:
        for i, img in enumerate(local_images):
            data = {"caption": fb_content if i == 0 else "", "access_token": FB_ACCESS_TOKEN}
            with open(img, "rb") as f:
                r = requests.post(
                    f"https://graph.facebook.com/v17.0/{FB_PAGE_ID}/photos",
                    data=data,
                    files={"source": f}
                )
            res = r.json()
            if "error" in res:
                print("❌ FB Error:", res["error"])
            else:
                fb_result.append(res)
    else:
        r = requests.post(
            f"https://graph.facebook.com/v17.0/{FB_PAGE_ID}/feed",
            data={"message": fb_content, "access_token": FB_ACCESS_TOKEN}
        )
        res = r.json()
        if "error" in res:
            print("❌ FB Error:", res["error"])
        else:
            fb_result.append(res)

except Exception as e:
    print("❌ FB পোস্ট failed:", e)

print("📤 FB Response:", fb_result)

# -----------------------------
# 🔟 Auto Comment
# -----------------------------
if fb_result:
    post_id = fb_result[0].get("id")
    if post_id:
        try:
            comment = "😱 এই ঘটনা নিয়ে আপনার কী মতামত?"
            post_fb_comment(post_id, comment)
        except:
            pass

# -----------------------------
# 1️⃣1️⃣ Save log
# -----------------------------
posted_articles.append(link)
with open(LOG_FILE, "w") as f:
    json.dump(posted_articles, f, ensure_ascii=False, indent=2)
