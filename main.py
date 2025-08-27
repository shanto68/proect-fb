import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import google.generativeai as genai
from utils import download_image, highlight_keywords, post_fb_comment
import json
import random
from datetime import datetime, timedelta
import urllib3

# -----------------------------
# Disable HTTPS warnings
# -----------------------------
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
# 2️⃣ Load / Create posted_articles.json
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
    exit()

# -----------------------------
# 4️⃣ Extract multiple latest articles (last 15 min)
# -----------------------------
articles = []
time_limit = datetime.now() - timedelta(minutes=15)

for item in soup.select("a.gPFEn"):
    title = item.text.strip()
    link = urljoin(PAGE_URL, item.get("href", ""))
    
    source_tag = item.find_parent().select_one("div.vr1PYe")
    source = source_tag.text.strip() if source_tag else ""
    
    time_tag = item.find_parent().select_one("time.hvbAAd")
    time_text = time_tag.text.strip() if time_tag else ""
    
    # Skip already posted
    if link in posted_articles:
        continue

    articles.append({
        "title": title,
        "link": link,
        "source": source,
        "time": time_text
    })

if not articles:
    print("⚠️ No new articles found in the last 15 min")
    exit()

# -----------------------------
# 5️⃣ AI-based Priority / Deduplication
# -----------------------------
model = genai.GenerativeModel("gemini-2.5-flash")

for article in articles:
    # Generate engagement & uniqueness score (placeholder random)
    article["score"] = random.randint(5, 10)

# Sort by score (descending)
articles.sort(key=lambda x: x["score"], reverse=True)

# Pick top 3 articles
top_articles = articles[:3]

# -----------------------------
# 6️⃣ Process top articles
# -----------------------------
def upgrade_attachment_url(url):
    if "-w" in url and "-h" in url:
        url = url.split("-w")[0] + "-w1080-h720"
    return url

for art in top_articles:
    title = art["title"]
    link = art["link"]
    source = art["source"]
    time_text = art["time"]

    # Safe image extraction
    a_tag = soup.find("a", href=link)
    img_tag = a_tag.find_next("img") if a_tag else None
    img_url = None
    if img_tag:
        if img_tag.has_attr("data-src"):
            img_url = img_tag["data-src"]
        elif img_tag.has_attr("srcset"):
            srcset = img_tag["srcset"].split(",")
            img_url = srcset[-1].split()[0]
        elif img_tag.has_attr("src"):
            img_url = img_tag["src"]

    # Fallback: og:image
    if not img_url:
        meta_img = soup.find("meta", property="og:image")
        if meta_img:
            img_url = meta_img.get("content")
    
    if img_url:
        img_url = upgrade_attachment_url(urljoin(PAGE_URL, img_url))

    local_images = []
    if img_url:
        if download_image(img_url, "img_0.jpg"):
            local_images.append("img_0.jpg")

    # AI content generation
    summary_prompt = f"""
    নিচের নিউজ কনটেন্টকে বাংলায় **সরাসরি, আকর্ষণীয় এবং বিস্তারিত ফেসবুক পোস্ট স্টাইলে** সাজাও। 
    - Full coverage, কখনো ৩-৪ লাইনের সীমাবদ্ধতা নেই। 
    - কখনো intro বা spoiler text যোগ করা হবে না। 
    - Human-like, engaging tone হবে। 
    - Natural emojis ব্যবহার করবে। 
    - পোস্ট শেষে মানুষকে comment করতে উদ্দীপিত করবে, যেমন: 'আপনার মতামত কমেন্টে জানান 👇'
    
    নিউজ কনটেন্ট:
    ---
    {title}
    {source}
    {time_text}
    """
    summary_text = model.generate_content(summary_prompt).text.strip()
    highlighted_text = highlight_keywords(summary_text, title.split()[:3])

    # Hashtags
    hashtag_prompt = f"Generate 3-5 relevant Bengali hashtags for this news article.\nTitle: {title}\nSummary: {summary_text}"
    hashtags = [tag.strip() for tag in model.generate_content(hashtag_prompt).text.split() if tag.startswith("#")]
    hashtags_text = " ".join(hashtags)

    fb_content = f"{highlighted_text}\n\n{hashtags_text}"

    # Post to FB
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

    # Auto-comment / discussion starter
    if fb_result:
        first_post_id = fb_result[0].get("id")
        if first_post_id:
            comment_prompt = f"""
            Article Title: {title}
            Summary: {summary_text}
            Generate a short, friendly, discussion-starter comment in Bengali, include emojis.
            """
            comment_text = model.generate_content(comment_prompt).text.strip()
            post_fb_comment(first_post_id, comment_text)

    # Log link
    posted_articles.append(link)
    with open(LOG_FILE, "w") as f:
        json.dump(posted_articles, f, ensure_ascii=False, indent=2)

print("✅ Top articles posted successfully!")
