from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import os
import json
import time
import requests
import google.generativeai as genai
import firebase_admin
from firebase_admin import credentials, db
import base64

# -----------------------------
# 1️⃣ Configuration
# -----------------------------
NEWS_LIST_URL = os.environ.get("NEWS_LIST_URL")
FB_PAGE_ID = os.environ.get("FB_PAGE_ID")
FB_ACCESS_TOKEN = os.environ.get("FB_ACCESS_TOKEN")
GEN_API_KEY = os.environ.get("GEMINI_API_KEY")
POST_AS_CAROUSEL = os.environ.get("POST_AS_CAROUSEL", "true").lower() == "true"
MAX_IMAGES = int(os.environ.get("MAX_IMAGES", 4))

# Firebase setup
FIREBASE_KEY_JSON = os.environ.get("FIREBASE_KEY_JSON")
FIREBASE_DB_URL = os.environ.get("FIREBASE_DB_URL")

if not FIREBASE_KEY_JSON or not FIREBASE_DB_URL:
    print("❌ Firebase config missing.")
    exit(1)

firebase_json = json.loads(base64.b64decode(FIREBASE_KEY_JSON))
cred = credentials.Certificate(firebase_json)
firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})
firebase_ref = db.reference("/posted_articles")

# Gemini setup
genai.configure(api_key=GEN_API_KEY)

# -----------------------------
# 2️⃣ Selenium headless browser
# -----------------------------
options = webdriver.ChromeOptions()
options.add_argument("--headless")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
driver.get(NEWS_LIST_URL)
wait = WebDriverWait(driver, 15)

# -----------------------------
# 3️⃣ Scrape first article (using new selectors)
# -----------------------------
try:
    first_article = wait.until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "li"))
    )

    # Title & URL
    title_tag = first_article.find_element(By.CSS_SELECTOR, "li .promo-text h2 a")
    title = title_tag.text.strip()
    article_url = title_tag.get_attribute("href")

    # Feature Image
    img_tag = first_article.find_elements(By.CSS_SELECTOR, "li .promo-image img[src]")
    feature_image = img_tag[0].get_attribute("src") if img_tag else None

except Exception as e:
    print("❌ Error fetching article:", e)
    driver.quit()
    exit(1)

driver.quit()

# -----------------------------
# 4️⃣ Duplicate prevention (Firebase)
# -----------------------------
posted_articles = firebase_ref.get() or []
if article_url in posted_articles:
    print("❌ Already posted. Exiting.")
    exit(0)

# -----------------------------
# 5️⃣ Generate content with Gemini
# -----------------------------
prompt = f"""
Article Title: {title}
Feature Image: {feature_image if feature_image else 'No image'}
Write a high-quality, engaging, and eye-catching Facebook post content for this article.
- Short, punchy sentences
- Curiosity hooks
- Emojis naturally
- 3-5 relevant hashtags
- Friendly, human-like
"""

model = genai.GenerativeModel("gemini-2.5-flash")
response = model.generate_content(prompt)
news_content = response.text.strip()

if not news_content:
    print("❌ Gemini content generate হয়নি। Exiting.")
    exit(0)

# -----------------------------
# 6️⃣ Post to Facebook
# -----------------------------
post_data = {
    "message": news_content,
    "link": article_url,
    "picture": feature_image,
    "access_token": FB_ACCESS_TOKEN
}

fb_response = requests.post(
    f"https://graph.facebook.com/v17.0/{FB_PAGE_ID}/feed",
    data=post_data
)
fb_result = fb_response.json()
print("Facebook Response:", fb_result)

if "id" in fb_result:
    print(f"🎉 Post Successful! Post ID: {fb_result['id']}")
    # Log in Firebase
    firebase_ref.push(article_url)
else:
    print("❌ Post failed. Check logs.")
