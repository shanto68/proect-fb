import os
import json
import feedparser
import requests
from bs4 import BeautifulSoup
from newspaper import Article
from utils import check_duplicate, download_image, highlight_keywords, post_fb_comment
import google.generativeai as genai

RSS_FEED = os.environ.get("RSS_FEED_URL")
FB_PAGE_ID = os.environ.get("FB_PAGE_ID")
FB_ACCESS_TOKEN = os.environ.get("FB_ACCESS_TOKEN")
GEN_API_KEY = os.environ.get("GEMINI_API_KEY")
LOG_FILE = "posted_articles.json"

DEFAULT_IMAGE = "https://i.ibb.co/7JfqXxB/default-news.jpg"   # fallback logo/image

genai.configure(api_key=GEN_API_KEY)


def extract_images_with_bs4(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, timeout=10, headers=headers, verify=False)
        soup = BeautifulSoup(r.text, "html.parser")
        imgs = []
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src")
            if src:
                if src.startswith("//"):
                    src = "https:" + src
                if src.startswith("http"):
                    imgs.append(src)
        return list(set(imgs))
    except Exception as e:
        print("❌ Image scrape failed:", e)
        return []


# -----------------------------
# Load posted log
# -----------------------------
try:
    with open(LOG_FILE, "r") as f:
        posted_articles = json.load(f)
except:
    posted_articles = []

feed = feedparser.parse(RSS_FEED)
if not feed.entries:
    print("❌ No RSS entries found.")
    exit()

entry = feed.entries[0]
title = entry.title
article_url = entry.link

print("📰 Latest Article:", title)

# Duplicate check
if title in posted_articles or check_duplicate(title):
    print("⚠️ Already posted. Skipping.")
    exit()

# -----------------------------
# Extract content + images
# -----------------------------
full_content = title
candidate_images = []

try:
    article = Article(article_url, language="bn")
    article.download()
    article.parse()
    full_content = article.text.strip() or title
    if article.top_image:
        candidate_images.append(article.top_image)
    if article.images:
        candidate_images.extend(list(article.images))
except Exception as e:
    print("⚠️ Newspaper3k failed:", e)

# fallback bs4
if not candidate_images:
    candidate_images = extract_images_with_bs4(article_url)

# fallback rss media
if not candidate_images and hasattr(entry, "media_content"):
    for media in entry.media_content:
        img_url = media.get("url")
        if img_url:
            candidate_images.append(img_url)

# final fallback default image
if not candidate_images:
    candidate_images = [DEFAULT_IMAGE]

print("Candidate images:", candidate_images)

# -----------------------------
# Download first few images
# -----------------------------
local_images = []
for idx, img in enumerate(candidate_images[:3]):  # max 3 img
    saved = download_image(img, f"article_{idx}")
    if saved:
        local_images.append(saved)

# Ensure at least default
if not local_images:
    saved = download_image(DEFAULT_IMAGE, "default_img")
    if saved:
        local_images.append(saved)

print("✅ Local images ready:", local_images)

# -----------------------------
# FB Content (with Gemini hashtags)
# -----------------------------
model = genai.GenerativeModel("gemini-2.5-flash")
prompt = f"Generate 3-5 Bengali hashtags for this article.\nTitle: {title}\nContent: {full_content}"
hashtags = []
try:
    resp = model.generate_content(prompt)
    hashtags = [t for t in resp.text.split() if t.startswith("#")]
except:
    pass

fb_content = f"{full_content}\n\n{' '.join(hashtags)}" if hashtags else full_content

# -----------------------------
# Post to FB
# -----------------------------
fb_api_url = f"https://graph.facebook.com/v17.0/{FB_PAGE_ID}/photos"
results = []
for idx, img_file in enumerate(local_images):
    data = {"caption": fb_content if idx == 0 else "", "access_token": FB_ACCESS_TOKEN}
    with open(img_file, "rb") as f:
        files = {"source": f}
        r = requests.post(fb_api_url, data=data, files=files)
    results.append(r.json())

print("📤 FB Response:", results)

# -----------------------------
# Log success
# -----------------------------
posted_articles.append(title)
with open(LOG_FILE, "w") as f:
    json.dump(posted_articles, f, ensure_ascii=False, indent=2)
