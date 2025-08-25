import os
import json
import random
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai

# -----------------------------
# Utils
# -----------------------------
def check_duplicate(url):
    """Check if URL is duplicate using botlink.gt.tc"""
    try:
        resp = requests.get(f"https://botlink.gt.tc/?urlcheck={url}", timeout=10, verify=False)
        if "duplicate.php" in resp.text:
            return True
        elif "unique.php" in resp.text:
            requests.get(f"https://botlink.gt.tc/?urlsubmit={url}", timeout=10, verify=False)
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

# -----------------------------
# 1️⃣ Configuration
# -----------------------------
URL = "https://www.bbc.com/bengali/topics/c907347rezkt"
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
# 3️⃣ Scrape latest article & images
# -----------------------------
response = requests.get(URL)
soup = BeautifulSoup(response.content, "html.parser")

first_article = soup.find("li", class_="bbc-t44f9r")
if not first_article:
    print("❌ No article found. Exiting.")
    exit()

# Title
title_tag = first_article.find("h2", class_="bbc-qqcsu8")
title = title_tag.get_text(strip=True)
article_url = title_tag.find("a")["href"]
if not article_url.startswith("http"):
    article_url = "https://www.bbc.com" + article_url

# Image(s)
image_urls = []
promo_image_div = first_article.find("div", class_="promo-image")
if promo_image_div:
    imgs = promo_image_div.find_all("img")
    for img in imgs:
        src = img.get("src")
        if src:
            image_urls.append(src)

print("Images found:", image_urls)

# -----------------------------
# 4️⃣ Duplicate check
# -----------------------------
if article_url in posted_articles or check_duplicate(article_url):
    print("❌ Already posted or duplicate. Skipping.")
    exit()

# -----------------------------
# 5️⃣ Generate content with Gemini
# -----------------------------
model = genai.GenerativeModel("gemini-2.5-flash")

# Auto summarization
summary_prompt = f"""
নিচের নিউজের মূল বিষয়গুলো নিয়ে 2-3 sentence এর আকর্ষণীয় summary বানাও। 
Article Title: {title}
Language: Bengali
Tone: Friendly, human-like, eye-catching
Include emojis naturally
"""
summary_resp = model.generate_content(summary_prompt)
summary_text = summary_resp.text.strip()

# Headline variations
headline_prompt = f"""
Generate 3 catchy Facebook headlines for this article:
Title: {title}
Language: Bengali
Friendly, punchy, scroll-stopping
Include emojis
"""
headline_resp = model.generate_content(headline_prompt)
headline_list = [line.strip() for line in headline_resp.text.split("\n") if line.strip()]
headline = random.choice(headline_list) if headline_list else title

# Auto hashtag generation
hashtag_prompt = f"""
Generate 3-5 relevant Bengali hashtags for this news article.
Title: {title}
Summary: {summary_text}
"""
hashtag_resp = model.generate_content(hashtag_prompt)
hashtags = [tag.strip() for tag in hashtag_resp.text.split() if tag.startswith("#")]
hashtags_text = " ".join(hashtags)

# Keyword highlighting (using emojis)
keywords = title.split()[:3]  # first 3 words as sample keywords
highlighted_text = highlight_keywords(summary_text, keywords)

# Final FB post content
fb_content = f"{headline}\n\n{highlighted_text}\n\n{hashtags_text}"
print("Generated FB Content:\n", fb_content)

# -----------------------------
# 6️⃣ Download & prepare images
# -----------------------------
local_images = []
for i, url in enumerate(image_urls):
    filename = f"img_{i}.jpg"
    if download_image(url, filename):
        local_images.append(filename)

# -----------------------------
# 7️⃣ Post to Facebook (Photo Only, No Link)
# -----------------------------
fb_api_url = f"https://graph.facebook.com/v17.0/{FB_PAGE_ID}/photos"

fb_result = []
if local_images:
    for idx, img_file in enumerate(local_images):
        data = {"caption": fb_content if idx == 0 else "", "access_token": FB_ACCESS_TOKEN}
        files = {"source": open(img_file, "rb")}
        r = requests.post(fb_api_url, data=data, files=files)
        fb_result.append(r.json())
else:
    # fallback: text-only post
    post_data = {"message": fb_content, "access_token": FB_ACCESS_TOKEN}
    r = requests.post(f"https://graph.facebook.com/v17.0/{FB_PAGE_ID}/feed", data=post_data)
    fb_result.append(r.json())

print("Facebook Response:", fb_result)

# -----------------------------
# 8️⃣ Log successful post
# -----------------------------
posted_articles.append(article_url)
with open(LOG_FILE, "w") as f:
    json.dump(posted_articles, f)
