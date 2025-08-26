import os
import json
import feedparser
import requests
import google.generativeai as genai
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

# Google News RSS gives redirect link → extract original URL
link = first_entry.link
try:
    resp = requests.get(link, timeout=10, headers={"User-Agent":"Mozilla/5.0"}, allow_redirects=True)
    original_url = resp.url
except:
    original_url = link

print("📰 Latest Article:", title)
print("🔗 Original URL:", original_url)

# -----------------------------
# 4️⃣ Duplicate check
# -----------------------------
if title in posted_articles or check_duplicate(title):
    print("⚠️ Already posted or duplicate. Skipping.")
    exit()

# -----------------------------
# 5️⃣ Scrape full article + images
# -----------------------------
full_content = title
candidate_images = []
tags = []

try:
    resp = requests.get(original_url, headers={"User-Agent":"Mozilla/5.0"}, timeout=10)
    soup = BeautifulSoup(resp.content, "html.parser")

    # Full text
    paragraphs = soup.find_all("p")
    full_content = "\n".join(p.get_text().strip() for p in paragraphs if p.get_text().strip())

    # Images
    imgs = soup.find_all("img")
    candidate_images = [img.get("src") for img in imgs if img.get("src") and img.get("src").startswith("http")]

    # Optional tags/keywords
    keywords_meta = soup.find("meta", attrs={"name":"keywords"})
    tags = [t.strip() for t in keywords_meta.get("content", "").split(",")] if keywords_meta else []

except Exception as e:
    print("❌ Scraping failed:", e)

# -----------------------------
# 6️⃣ High-res images
# -----------------------------
def pick_high_res(images):
    scored = []
    for url in images:
        try:
            r = requests.head(url, timeout=5, headers={"User-Agent":"Mozilla/5.0"}, verify=False)
            size = int(r.headers.get("Content-Length", 0))
            scored.append((size, url))
        except:
            scored.append((0, url))
    scored.sort(reverse=True)
    return [url for size, url in scored]

high_res_images = pick_high_res(candidate_images)
print("High-res images selected:", high_res_images)

# -----------------------------
# 7️⃣ Download images locally
# -----------------------------
local_images = []
for idx, img_url in enumerate(high_res_images[:5]):  # max 5 images
    filename = f"img_{idx}.jpg"
    if download_image(img_url, filename):
        local_images.append(filename)
print("Local images downloaded:", local_images)

# -----------------------------
# 8️⃣ Prepare FB post content
# -----------------------------
keywords_for_highlight = title.split()[:3] + tags[:2]
fb_content = highlight_keywords(full_content, keywords_for_highlight)

# Hashtags via Gemini AI
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

if hashtags:
    fb_content = f"{fb_content}\n\n{' '.join(hashtags)}"

# -----------------------------
# 9️⃣ Post to Facebook
# -----------------------------
fb_result = []

if local_images:
    # First image with short caption
    first_caption = fb_content[:500]
    data = {"caption": first_caption, "access_token": FB_ACCESS_TOKEN}
    with open(local_images[0], "rb") as f:
        files = {"source": f}
        r = requests.post(f"https://graph.facebook.com/v17.0/{FB_PAGE_ID}/photos", data=data, files=files)
    fb_result.append(r.json())

    # Remaining images album style
    for img_file in local_images[1:]:
        data = {"caption": "", "access_token": FB_ACCESS_TOKEN}
        with open(img_file, "rb") as f:
            files = {"source": f}
            r = requests.post(f"https://graph.facebook.com/v17.0/{FB_PAGE_ID}/photos", data=data, files=files)
        fb_result.append(r.json())
else:
    # No images → normal post
    post_data = {"message": fb_content, "access_token": FB_ACCESS_TOKEN}
    r = requests.post(f"https://graph.facebook.com/v17.0/{FB_PAGE_ID}/feed", data=post_data)
    fb_result.append(r.json())

print("📤 Facebook Response:", fb_result)

# -----------------------------
# 🔟 Auto-comment
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
