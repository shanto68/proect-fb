import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import os
import json
from PIL import Image
from io import BytesIO
import random

# -----------------------------
# 1️⃣ Configuration
# -----------------------------
URL = "https://www.bbc.com/bengali/topics/c907347rezkt"  # Custom URL
FB_PAGE_ID = os.environ.get("FB_PAGE_ID")
FB_ACCESS_TOKEN = os.environ.get("FB_ACCESS_TOKEN")
GEN_API_KEY = os.environ.get("GEMINI_API_KEY")
LOG_FILE = "posted_articles.json"

genai.configure(api_key=GEN_API_KEY)

# -----------------------------
# 2️⃣ Load previously posted articles
# -----------------------------
try:
    with open(LOG_FILE, "r") as f:
        posted_articles = json.load(f)
except:
    posted_articles = []

# -----------------------------
# 3️⃣ Scrape latest article
# -----------------------------
response = requests.get(URL)
soup = BeautifulSoup(response.content, "html.parser")

first_article = soup.find("li", class_="bbc-t44f9r")
if not first_article:
    print("❌ No article found on page. Exiting.")
    exit()

title_tag = first_article.find("h2", class_="bbc-qqcsu8")
title = title_tag.get_text(strip=True)
article_url = title_tag.find("a")["href"]
if not article_url.startswith("http"):
    article_url = "https://www.bbc.com" + article_url

# Feature image
img_div = first_article.find("div", class_="bbc-1gbs0ve")
img_tag = img_div.find("img") if img_div else None
feature_image = img_tag["src"] if img_tag else None

# -----------------------------
# 4️⃣ Duplicate Handling (URL-based)
# -----------------------------
if article_url in posted_articles:
    print("❌ Already posted. Exiting.")
    exit()

# -----------------------------
# 5️⃣ Scrape article body for summary
# -----------------------------
article_body = soup.find("div", class_="ssrcss-uf6wea-RichTextComponentWrapper")
article_text = article_body.get_text(separator=" ", strip=True) if article_body else ""

# -----------------------------
# 6️⃣ Generate Multiple Post Variants with Gemini
# -----------------------------
model = genai.GenerativeModel("gemini-2.5-flash")
variants = []

for i in range(3):
    prompt = f"""
Article Title: {title}
Article Content: {article_text[:1000]}
Feature Image: {feature_image if feature_image else 'No image'}
Write a high-quality, engaging, and eye-catching Facebook post content for this article.
- Short and punchy sentences
- Curiosity hooks
- Include emojis naturally
- Include 3-5 relevant hashtags
- Friendly and human-like tone
- Variant number: {i+1}
"""
    response = model.generate_content(prompt)
    text = response.text.strip()
    if text:
        variants.append(text)

if not variants:
    print("❌ Gemini content generate হয়নি। Exiting.")
    exit(0)

# Randomly choose one variant
news_content = random.choice(variants)

# -----------------------------
# 7️⃣ Auto Image Download & Optimization
# -----------------------------
if feature_image:
    try:
        img_response = requests.get(feature_image)
        img = Image.open(BytesIO(img_response.content))
        img = img.resize((1200, 630))  # FB recommended size
        optimized_image_path = "optimized_image.jpg"
        img.save(optimized_image_path)
    except Exception as e:
        print("❌ Image download/optimization failed:", e)
        optimized_image_path = None
else:
    optimized_image_path = None

# -----------------------------
# 8️⃣ Post to Facebook Page
# -----------------------------
post_data = {
    "message": news_content,
    "link": article_url,
    "access_token": FB_ACCESS_TOKEN
}

if optimized_image_path:
    post_data["picture"] = optimized_image_path

fb_response = requests.post(
    f"https://graph.facebook.com/v17.0/{FB_PAGE_ID}/feed",
    data=post_data
)
fb_result = fb_response.json()
print("Facebook Response:", fb_result)

# -----------------------------
# 9️⃣ Log successful post
# -----------------------------
if "id" in fb_result:
    print(f"🎉 Post Successful! Post ID: {fb_result['id']}")
    posted_articles.append(article_url)
    with open(LOG_FILE, "w") as f:
        json.dump(posted_articles, f)
else:
    print("❌ Post failed. Check logs.")
