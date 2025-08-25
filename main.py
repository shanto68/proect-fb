import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import os
import json

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
title_tag = first_article.find("h2", class_="bbc-qqcsu8")
title = title_tag.get_text(strip=True)
article_url = title_tag.find("a")["href"]
if not article_url.startswith("http"):
    article_url = "https://www.bbc.com" + article_url

# Feature image
img_div = first_article.find("div", class_="bbc-1gbs0ve")
img_tag = img_div.find("img") if img_div else None
feature_image = img_tag["src"] if img_tag else None

# Duplicate check
if article_url in posted_articles:
    print("❌ Already posted. Exiting.")
    exit()

# -----------------------------
# 4️⃣ Generate Eye-catching Content with Gemini
# -----------------------------
prompt = f"""
Article Title: {title}
Feature Image: {feature_image}
Write a high-quality, engaging, and eye-catching Facebook post content for this article.
Include:
- short punchy sentences
- curiosity hooks
- emojis
- relevant hashtags
"""

model = genai.TextModel("gemini-2.5-flash")
response = model.generate_content(prompt)
fb_content = response.result[0].content
print("Generated FB Content:\n", fb_content)

# -----------------------------
# 5️⃣ Post to Facebook Page
# -----------------------------
post_data = {
    "message": fb_content,
    "link": article_url,
    "picture": feature_image
}

fb_response = requests.post(
    f"https://graph.facebook.com/v17.0/{FB_PAGE_ID}/feed",
    data=post_data,
    params={"access_token": FB_ACCESS_TOKEN}
)
fb_result = fb_response.json()
print("Facebook Response:", fb_result)

# -----------------------------
# 6️⃣ Log successful post
# -----------------------------
if "id" in fb_result:
    print(f"🎉 Post Successful! Post ID: {fb_result['id']}")
    posted_articles.append(article_url)
    with open(LOG_FILE, "w") as f:
        json.dump(posted_articles, f)
else:
    print("❌ Post failed. Check logs.")
