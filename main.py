import os
import json
import requests
import feedparser
from bs4 import BeautifulSoup
import google.generativeai as genai
from urllib.parse import quote
import warnings

# -----------------------------
# Ignore HTTPS Warnings
# -----------------------------
warnings.filterwarnings("ignore", message="Unverified HTTPS request")

# -----------------------------
# Utils
# -----------------------------
def check_duplicate(title):
    """Check duplicate using botlink.gt.tc"""
    try:
        encoded_title = quote(title)
        resp = requests.get(f"https://botlink.gt.tc/?urlcheck={encoded_title}", timeout=10, verify=False)
        if "duplicate.php" in resp.text:
            return True
        elif "unique.php" in resp.text:
            requests.get(f"https://botlink.gt.tc/?urlsubmit={encoded_title}", timeout=10, verify=False)
            return False
    except Exception as e:
        print("❌ Duplicate check failed:", e)
        return False

def download_image(url, filename):
    try:
        r = requests.get(url, stream=True, timeout=10)
        if r.status_code == 200:
            with open(filename, 'wb') as f:
                for chunk in r.iter_content(1024):
                    f.write(chunk)
            return True
    except Exception as e:
        print("❌ Image download failed:", e)
    return False

def highlight_keywords(text, keywords):
    for kw in keywords:
        if kw in text:
            text = text.replace(kw, f"⚡{kw}⚡")
    return text

def post_fb_comment(post_id, comment_text):
    """Post comment on FB post"""
    fb_comment_url = f"https://graph.facebook.com/v17.0/{post_id}/comments"
    data = {"message": comment_text, "access_token": os.environ.get("FB_ACCESS_TOKEN")}
    try:
        resp = requests.post(fb_comment_url, data=data)
        print("Comment Response:", resp.json())
    except Exception as e:
        print("❌ Comment failed:", e)

# -----------------------------
# Configuration
# -----------------------------
RSS_URL = os.environ.get("RSS_URL")  # secret RSS link
FB_PAGE_ID = os.environ.get("FB_PAGE_ID")
FB_ACCESS_TOKEN = os.environ.get("FB_ACCESS_TOKEN")
GEN_API_KEY = os.environ.get("GEMINI_API_KEY")
LOG_FILE = "posted_articles.json"

genai.configure(api_key=GEN_API_KEY)

# -----------------------------
# Load posted articles
# -----------------------------
try:
    with open(LOG_FILE, "r") as f:
        posted_articles = json.load(f)
except:
    posted_articles = []

# -----------------------------
# Fetch latest RSS entry
# -----------------------------
feed = feedparser.parse(RSS_URL)
if not feed.entries:
    print("❌ No RSS entries found.")
    exit()

latest_entry = feed.entries[0]
title = latest_entry.title
link = latest_entry.link

print("📰 Latest Article:", title)
print("🔗 URL:", link)

if title in posted_articles or check_duplicate(title):
    print("❌ Already posted or duplicate. Skipping.")
    exit()

# -----------------------------
# Extract full content from article
# -----------------------------
try:
    resp = requests.get(link, timeout=10)
    soup = BeautifulSoup(resp.content, "html.parser")
    paragraphs = soup.find_all("p")
    content = " ".join([p.get_text() for p in paragraphs if len(p.get_text())>20])
except Exception as e:
    print("❌ Full content extraction failed:", e)
    content = title  # fallback

# -----------------------------
# Extract images
# -----------------------------
images = []
img_tags = soup.find_all("img")
for img in img_tags:
    srcset = img.get("srcset")
    if srcset:
        candidates = []
        for part in srcset.split(","):
            url_part, size_part = part.strip().split(" ")
            width = int(size_part.replace("w", ""))
            candidates.append((width, url_part))
        candidates.sort(reverse=True)
        high_res_url = candidates[0][1]
        images.append(high_res_url)
    else:
        src = img.get("src")
        if src:
            images.append(src)

# Remove duplicates and limit to max 5 images
images = list(dict.fromkeys(images))[:5]

# -----------------------------
# Gemini AI summary
# -----------------------------
model = genai.GenerativeModel("gemini-2.5-flash")

summary_prompt = f"""
নিচের নিউজ কনটেন্টকে বাংলায় ৩–৪ লাইনের আকর্ষণীয়,
সহজবোধ্য, ফেসবুক পোস্ট স্টাইলে সাজাও। ইমোজি ব্যবহার করবে।
Article Content: {content}
"""

summary_resp = model.generate_content(summary_prompt)
summary_text = summary_resp.content[0].text.strip()
highlighted_text = highlight_keywords(summary_text, title.split()[:3])

# Hashtags
hashtag_prompt = f"""
Generate 3-5 relevant Bengali hashtags for this news article.
Title: {title}
Summary: {summary_text}
"""
hashtag_resp = model.generate_content(hashtag_prompt)
hashtags = [tag.strip() for tag in hashtag_resp.content[0].text.split() if tag.startswith("#")]
hashtags_text = " ".join(hashtags)

fb_content = f"{highlighted_text}\n\n{hashtags_text}"

# -----------------------------
# Download images
# -----------------------------
local_images = []
for i, url in enumerate(images):
    filename = f"img_{i}.jpg"
    if download_image(url, filename):
        local_images.append(filename)

# -----------------------------
# Post to Facebook
# -----------------------------
fb_api_url = f"https://graph.facebook.com/v17.0/{FB_PAGE_ID}/photos"
fb_result = []

if local_images:
    for idx, img_file in enumerate(local_images):
        data = {"caption": fb_content if idx == 0 else "", "access_token": FB_ACCESS_TOKEN}
        files = {"source": open(img_file, 'rb')}
        r = requests.post(fb_api_url, data=data, files=files)
        fb_result.append(r.json())
else:
    post_data = {"message": fb_content, "access_token": FB_ACCESS_TOKEN}
    r = requests.post(f"https://graph.facebook.com/v17.0/{FB_PAGE_ID}/feed", data=post_data)
    fb_result.append(r.json())

print("📤 Facebook Response:", fb_result)

# -----------------------------
# Auto-comment on first image
# -----------------------------
if local_images and fb_result:
    first_post_id = fb_result[0].get("id")
    if first_post_id:
        comment_prompt = f"""
        Article Title: {title}
        Summary: {summary_text}
        Write a short, friendly, engaging, and scroll-stopping comment in Bengali for this Facebook post.
        Include emojis naturally.
        """
        comment_resp = model.generate_content(comment_prompt)
        comment_text = comment_resp.content[0].text.strip()
        print("💬 Generated Comment:\n", comment_text)
        post_fb_comment(first_post_id, comment_text)

# -----------------------------
# Log posted article
# -----------------------------
posted_articles.append(title)
with open(LOG_FILE, "w") as f:
    json.dump(posted_articles, f)
