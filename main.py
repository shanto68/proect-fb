import os
import json
import time
import random
import base64
import tempfile
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import firebase_admin
from firebase_admin import credentials, db
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# -----------------------------
# 1️⃣ Configuration
# -----------------------------
URL = os.environ.get("NEWS_LIST_URL", "https://www.bbc.com/bengali/topics/c907347rezkt")
FB_PAGE_ID = os.environ.get("FB_PAGE_ID")
FB_ACCESS_TOKEN = os.environ.get("FB_ACCESS_TOKEN")
GEN_API_KEY = os.environ.get("GEMINI_API_KEY")
FIREBASE_KEY_JSON = os.environ.get("FIREBASE_KEY_JSON")  # base64 encoded
FIREBASE_DB_URL = os.environ.get("FIREBASE_DB_URL")
MAX_IMAGES = int(os.environ.get("MAX_IMAGES", 4))
POST_AS_CAROUSEL = os.environ.get("POST_AS_CAROUSEL", "true").lower() == "true"
TIMEOUT = 60

# -----------------------------
# Check configs
# -----------------------------
if not all([FB_PAGE_ID, FB_ACCESS_TOKEN, GEN_API_KEY, FIREBASE_KEY_JSON, FIREBASE_DB_URL]):
    print("❌ Missing required environment variables.")
    raise SystemExit(1)

# -----------------------------
# Firebase init
# -----------------------------
temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
temp_file.write(base64.b64decode(FIREBASE_KEY_JSON))
temp_file.close()
cred = credentials.Certificate(temp_file.name)
firebase_admin.initialize_app(cred, {'databaseURL': FIREBASE_DB_URL})
ref = db.reference('posted_articles')

# -----------------------------
# Gemini init
# -----------------------------
genai.configure(api_key=GEN_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

# -----------------------------
# Selenium setup
# -----------------------------
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
driver = webdriver.Chrome(options=chrome_options)

def safe_gemini_text(resp):
    try:
        if hasattr(resp, "text") and resp.text:
            return resp.text.strip()
        cand = resp.candidates[0]
        parts = getattr(cand, "content", getattr(cand, "contents", None))
        if parts and hasattr(parts, "parts"):
            return parts.parts[0].text.strip()
    except Exception:
        pass
    return ""

def get_latest_article(url):
    driver.get(url)
    try:
        # wait for main article to load
        main_li = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "li.bbc-1fxtbkn"))
        )
        soup = BeautifulSoup(driver.page_source, "html.parser")
        first_article = soup.select_one("li.bbc-1fxtbkn a")
        if not first_article:
            return None
        title_tag = first_article.find("h3")
        title = title_tag.get_text(strip=True) if title_tag else first_article.get_text(strip=True)
        article_url = first_article.get("href")
        if not article_url.startswith("http"):
            article_url = "https://www.bbc.com" + article_url
        img_tag = first_article.find("img")
        feature_image = img_tag["src"] if img_tag else None
        return {"title": title, "url": article_url, "feature_image": feature_image}
    except Exception as e:
        print("❌ Error fetching article:", e)
        return None

def extract_article_images(article_url, max_images=4):
    driver.get(article_url)
    time.sleep(3)
    soup = BeautifulSoup(driver.page_source, "html.parser")
    imgs = []
    for tag in soup.select("article img, figure img, .ssrcss-uf6wea-RichTextComponentWrapper img"):
        src = tag.get("src") or tag.get("data-src")
        if src and src.startswith("http") and src not in imgs:
            imgs.append(src)
        if len(imgs) >= max_images:
            break
    return imgs

# -----------------------------
# Scrape latest article
# -----------------------------
item = get_latest_article(URL)
if not item:
    print("❌ No article found. Exiting.")
    driver.quit()
    raise SystemExit(0)

title = item['title']
article_url = item['url']
feature_image = item.get('feature_image')

# Firebase duplicate check
posted_list = ref.get() or []
if article_url in posted_list:
    print("❌ Duplicate detected in Firebase. Skipping post.")
    driver.quit()
    raise SystemExit(0)

images = extract_article_images(article_url, MAX_IMAGES)
if feature_image and feature_image not in images:
    images = [feature_image] + images
images = images[:MAX_IMAGES] if images else ([] if not feature_image else [feature_image])

# -----------------------------
# Generate content
# -----------------------------
summary_prompt = f"""
তুমি একজন সোশ্যাল মিডিয়া কপিরাইটার। নিচের নিউজের জন্য ২–৩ লাইনের ছোট বাংলা সারাংশ লিখো।
শিরোনাম: {title}
লিংক: {article_url}
"""
summary_text = safe_gemini_text(model.generate_content(summary_prompt))
if not summary_text:
    print("❌ Gemini summary generate হয়নি।")
    driver.quit()
    raise SystemExit(0)

caption_prompt = f"""
তুমি একজন ফেসবুক কপিরাইটার। নিচের নিউজের জন্য ৩টি ভিন্ন স্ক্রল-স্টপিং ক্যাপশন লেখো।
শর্ত:
- শুধু বাংলায় হবে
- ছোট বাক্য
- কৌতূহল জাগাবে
- ইমোজি ব্যবহার করো
- মূল কিওয়ার্ডের আগে 👉 বা 🔥
শিরোনাম: {title}
সারাংশ: {summary_text}
"""
raw_caps = safe_gemini_text(model.generate_content(caption_prompt))
captions = [c.strip("- •\n ") for c in raw_caps.split("\n") if c.strip()]
captions = [c for c in captions if len(c)>3][:3] or [summary_text]
selected_caption = random.choice(captions)

hashtag_prompt = f"""
নিচের শিরোনাম ও সারাংশ থেকে বাংলা ৩–৫টি হ্যাশট্যাগ দাও।
শিরোনাম: {title}
সারাংশ: {summary_text}
"""
hlist = safe_gemini_text(model.generate_content(hashtag_prompt)).replace("\n"," ").split()
hashtags = " ".join([h for h in hlist if h.startswith("#")][:5])

message = f"{selected_caption}\n\n{hashtags}".strip()
print("\nGenerated FB Content:\n", message)

# -----------------------------
# Post to Facebook
# -----------------------------
uploaded_media_ids = []
for idx, img_url in enumerate(images):
    try:
        resp = requests.post(f"https://graph.facebook.com/v17.0/{FB_PAGE_ID}/photos",
                             data={"url": img_url, "published": False, "access_token": FB_ACCESS_TOKEN},
                             timeout=TIMEOUT)
        data = resp.json()
        if resp.status_code == 200 and "id" in data:
            uploaded_media_ids.append(data["id"])
            print(f"✅ Uploaded image {idx+1}/{len(images)}")
        else:
            print("⚠️ Photo upload failed:", data)
    except Exception as e:
        print("⚠️ Photo upload error:", e)

# Publish post
if not uploaded_media_ids:
    result = requests.post(f"https://graph.facebook.com/v17.0/{FB_PAGE_ID}/feed",
                           data={"message": message, "link": article_url, "access_token": FB_ACCESS_TOKEN},
                           timeout=TIMEOUT).json()
else:
    if POST_AS_CAROUSEL and len(uploaded_media_ids) > 1:
        payload = {"message": message, "access_token": FB_ACCESS_TOKEN}
        for i, mid in enumerate(uploaded_media_ids):
            payload[f"attached_media[{i}]"] = json.dumps({"media_fbid": mid})
        result = requests.post(f"https://graph.facebook.com/v17.0/{FB_PAGE_ID}/feed",
                               data=payload, timeout=TIMEOUT).json()
    else:
        result = requests.post(f"https://graph.facebook.com/v17.0/{FB_PAGE_ID}/feed",
                               data={"message": message,
                                     "attached_media[0]": json.dumps({"media_fbid": uploaded_media_ids[0]}),
                                     "access_token": FB_ACCESS_TOKEN},
                               timeout=TIMEOUT).json()

print("Facebook Response:", result)

# -----------------------------
# Log successful post in Firebase
# -----------------------------
if "id" in result:
    print(f"🎉 Post Successful! Post ID: {result['id']}")
    posted_list.append(article_url)
    ref.set(posted_list)

driver.quit()
