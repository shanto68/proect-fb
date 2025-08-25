import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
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

genai.configure(api_key=GEN_API_KEY)

# -----------------------------
# 2️⃣ Google Sheet Setup
# -----------------------------
scope = ["https://spreadsheets.google.com/feeds",
         "https://www.googleapis.com/auth/drive"]

creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)
sheet = client.open("posted_articles").sheet1

def already_posted(url):
    urls = sheet.col_values(1)
    return url in urls

def log_post(url):
    sheet.append_row([url])

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

# Duplicate check
if already_posted(article_url):
    print("❌ Already posted. Exiting.")
    exit()

# -----------------------------
# 4️⃣ Generate Multiple Post Variants with Gemini
# -----------------------------
variants = []
for i in range(3):
    prompt = f"""
    Article Title: {title}
    Feature Image: {feature_image if feature_image else 'No image'}
    Write a high-quality, engaging, and eye-catching Facebook post content.
    Make it:
    - Short and punchy sentences
    - Curiosity hooks
    - Include emojis naturally
    - Include 3-5 relevant hashtags
    - Friendly and human-like tone
    - Variant number: {i+1}
    """
    model = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content(prompt)
    text = response.text.strip()
    if text:
        variants.append(text)

if not variants:
    print("❌ Gemini content generate হয়নি। Exiting.")
    exit(0)

news_content = random.choice(variants)
print("Generated FB Content:\n", news_content)

# -----------------------------
# 5️⃣ Auto Image Download & Optimization
# -----------------------------
if feature_image:
    try:
        img_response = requests.get(feature_image)
        img = Image.open(BytesIO(img_response.content))
        img = img.resize((1200, 630))  # FB recommended size
        img.save("optimized_image.jpg")
        feature_image = "optimized_image.jpg"
    except Exception as e:
        print("❌ Image download/optimization failed:", e)
        feature_image = None

# -----------------------------
# 6️⃣ Post to Facebook Page
# -----------------------------
post_data = {
    "message": news_content,
    "link": article_url,
    "access_token": FB_ACCESS_TOKEN
}

if feature_image:
    post_data["picture"] = feature_image

fb_response = requests.post(
    f"https://graph.facebook.com/v17.0/{FB_PAGE_ID}/feed",
    data=post_data
)
fb_result = fb_response.json()
print("Facebook Response:", fb_result)

# -----------------------------
# 7️⃣ Log successful post in Google Sheet
# -----------------------------
if "id" in fb_result:
    print(f"🎉 Post Successful! Post ID: {fb_result['id']}")
    log_post(article_url)
else:
    print("❌ Post failed. Check logs.")
