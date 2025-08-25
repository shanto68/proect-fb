import os
import json
import requests
from bs4 import BeautifulSoup
from PIL import Image
from io import BytesIO
import firebase_admin
from firebase_admin import credentials, firestore
import google.generativeai as genai

# -----------------------------
# 1️⃣ Configuration
# -----------------------------
URL = "https://www.bbc.com/bengali/topics/c907347rezkt"  # Custom URL
FB_PAGE_ID = os.environ.get("FB_PAGE_ID")
FB_ACCESS_TOKEN = os.environ.get("FB_ACCESS_TOKEN")
GEN_API_KEY = os.environ.get("GEMINI_API_KEY")
FIREBASE_KEY_FILE = "firebase_key.json"

# Gemini API configure
genai.configure(api_key=GEN_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

# Firebase initialize
cred = credentials.Certificate(FIREBASE_KEY_FILE)
firebase_admin.initialize_app(cred)
db = firestore.client()
posts_ref = db.collection("posted_articles")

# -----------------------------
# 2️⃣ Scrape latest article
# -----------------------------
response = requests.get(URL)
soup = BeautifulSoup(response.content, "html.parser")

first_article = soup.find("li", class_="bbc-t44f9r")
if not first_article:
    print("❌ No article found. Exiting.")
    exit()

title_tag = first_article.find("h2", class_="bbc-qqcsu8")
title = title_tag.get_text(strip=True)
article_url = title_tag.find("a")["href"]
if not article_url.startswith("http"):
    article_url = "https://www.bbc.com" + article_url

# Feature images (supports multiple)
img_divs = first_article.find_all("div", class_="bbc-1gbs0ve")
image_urls = []
for div in img_divs:
    img_tag = div.find("img")
    if img_tag and "src" in img_tag.attrs:
        image_urls.append(img_tag["src"])

# -----------------------------
# 3️⃣ Duplicate check with Firebase
# -----------------------------
existing = posts_ref.where("url", "==", article_url).stream()
if any(existing):
    print("❌ Already posted in Firebase. Exiting.")
    exit()

# -----------------------------
# 4️⃣ Extract article summary
# -----------------------------
article_content_div = first_article.find("p")
article_content = article_content_div.get_text(strip=True) if article_content_div else ""
summary_prompt = f"Summarize this article in 2-3 sentences:\n{article_content}"
summary = model.generate_text(summary_prompt).text.strip()

# -----------------------------
# 5️⃣ Generate multiple FB post variants
# -----------------------------
variants = []
for i in range(3):
    prompt = f"""
Article Title: {title}
Summary: {summary}
Feature Images: {', '.join(image_urls) if image_urls else 'No image'}
Write a high-quality, engaging, eye-catching Facebook post content.
- Short punchy sentences
- Curiosity hooks
- Include emojis naturally
- Include 3-5 relevant hashtags
- Friendly and human-like tone
- Make variant number {i+1}
"""
    response = model.generate_text(prompt)
    variants.append(response.text.strip())

# Choose first variant as default (optional: add scoring later)
news_content = variants[0]

# -----------------------------
# 6️⃣ Download & optimize images
# -----------------------------
optimized_images = []
for idx, img_url in enumerate(image_urls):
    try:
        img_response = requests.get(img_url)
        img = Image.open(BytesIO(img_response.content))
        img = img.resize((1200, 630))
        optimized_path = f"optimized_{idx}.jpg"
        img.save(optimized_path)
        optimized_images.append(optimized_path)
    except Exception as e:
        print(f"⚠️ Image {img_url} failed: {e}")

# -----------------------------
# 7️⃣ Post to Facebook (single or carousel)
# -----------------------------
if len(optimized_images) <= 1:
    # Single post
    post_data = {
        "message": news_content,
        "link": article_url,
        "picture": optimized_images[0] if optimized_images else None,
        "access_token": FB_ACCESS_TOKEN
    }
    fb_response = requests.post(
        f"https://graph.facebook.com/v17.0/{FB_PAGE_ID}/feed",
        data=post_data
    )
else:
    # Carousel post
    media_ids = []
    for img_path in optimized_images:
        r = requests.post(
            f"https://graph.facebook.com/v17.0/{FB_PAGE_ID}/photos",
            files={"source": open(img_path, "rb")},
            data={"published": "false", "access_token": FB_ACCESS_TOKEN}
        ).json()
        if "id" in r:
            media_ids.append({"media_fbid": r["id"]})

    fb_response = requests.post(
        f"https://graph.facebook.com/v17.0/{FB_PAGE_ID}/feed",
        data={
            "message": news_content,
            "attached_media": json.dumps(media_ids),
            "access_token": FB_ACCESS_TOKEN
        }
    )

fb_result = fb_response.json()
print("Facebook Response:", fb_result)

# -----------------------------
# 8️⃣ Log successful post in Firebase
# -----------------------------
if "id" in fb_result:
    print(f"🎉 Post Successful! Post ID: {fb_result['id']}")
    posts_ref.add({
        "url": article_url,
        "title": title,
        "posted_at": firestore.SERVER_TIMESTAMP
    })
else:
    print("❌ Post failed. Check logs.")
