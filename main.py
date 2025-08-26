import os
import json
import feedparser
import requests
import google.generativeai as genai
from newspaper import Article
from bs4 import BeautifulSoup
from utils import check_duplicate, download_image, highlight_keywords, post_fb_comment

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
# 5️⃣ Scrape full article content
# -----------------------------
try:
    # Newspaper3k
    article = Article(article_url, language="bn")
    article.download()
    article.parse()
    full_content = article.text
    top_image = article.top_image
    authors = article.authors
    publish_date = article.publish_date
except Exception as e:
    print("❌ Newspaper parsing failed:", e)
    full_content = title
    top_image = None
    authors = []
    publish_date = None

# BeautifulSoup for multiple images & tags
try:
    resp = requests.get(article_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
    soup = BeautifulSoup(resp.content, "html.parser")

    # Multiple images
    imgs = soup.find_all("img")
    candidate_images = [img.get("src") for img in imgs if img.get("src") and img.get("src").startswith("http")]
    if top_image:
        candidate_images.insert(0, top_image)  # top_image priority

    # Tags / keywords
    keywords_meta = soup.find("meta", attrs={"name": "keywords"})
    tags = [t.strip() for t in keywords_meta.get("content", "").split(",")] if keywords_meta else []

except Exception as e:
    print("❌ BeautifulSoup scraping failed:", e)
    candidate_images = [top_image] if top_image else []
    tags = []

# -----------------------------
# 6️⃣ Pick high-res images
# -----------------------------
def pick_high_res(images):
    scored = []
    for url in images:
        try:
            r = requests.head(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"}, verify=False)
            size = int(r.headers.get('Content-Length', 0))
            scored.append((size, url))
        except:
            scored.append((0, url))
    scored.sort(reverse=True)
    return [url for size, url in scored]

high_res_images = pick_high_res(candidate_images)
print("High-res images selected:", high_res_images)

# -----------------------------
# 7️⃣ Download images locally (max 5)
# -----------------------------
local_images = []
for idx, img_url in enumerate(high_res_images):
    filename = f"img_{idx}.jpg"
    if download_image(img_url, filename):
        local_images.append(filename)
    if idx >= 4:
        break
print("Local images downloaded:", local_images)

# -----------------------------
# 8️⃣ Prepare FB Post Content (full article)
# -----------------------------
keywords_for_highlight = title.split()[:3] + tags[:2]
fb_content = highlight_keywords(full_content, keywords_for_highlight)

# Optional: add hashtags
model = genai.GenerativeModel("gemini-2.5-flash")
hashtag_prompt = f"""
Generate 3-5 relevant Bengali hashtags for this news article.
Title: {title}
Content: {full_content}
"""
try:
    hashtag_resp = model.generate_content(hashtag_prompt)
    hashtags = [tag.strip() for tag in hashtag_resp.text.split() if tag.startswith("#")]
except:
    hashtags = []

hashtags_text = " ".join(hashtags)
if hashtags_text:
    fb_content = f"{fb_content}\n\n{hashtags_text}"

print("✅ FB Content prepared (full article)")

# -----------------------------
# 9️⃣ Post to Facebook
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
# 🔟 Auto-comment (optional)
# -----------------------------
if fb_result:
    first_post_id = fb_result[0].get("id")
    if first_post_id:
        comment_prompt = f"""
        Article Title: {title}
        Write a short, friendly, engaging comment in Bengali for this Facebook post. Include emojis naturally.
        """
        try:
            comment_resp = model.generate_content(comment_prompt)
            comment_text = comment_resp.text.strip()
            print("💬 Generated Comment:\n", comment_text)
            post_fb_comment(first_post_id, comment_text)
        except:
            print("⚠️ Comment generation failed")

# -----------------------------
# 1️⃣1️⃣ Log successful post
# -----------------------------
posted_articles.append(title)
with open(LOG_FILE, "w") as f:
    json.dump(posted_articles, f)

print("✅ Article posted successfully!")
