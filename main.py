import os
import json
import time
import random
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
from urllib.parse import urljoin
import firebase_admin
from firebase_admin import credentials, db

# -----------------------------
# 1️⃣ Configuration
# -----------------------------
URL = os.environ.get("NEWS_LIST_URL", "https://www.bbc.com/bengali/topics/c907347rezkt")
FB_PAGE_ID = os.environ.get("FB_PAGE_ID")
FB_ACCESS_TOKEN = os.environ.get("FB_ACCESS_TOKEN")
GEN_API_KEY = os.environ.get("GEMINI_API_KEY")
FIREBASE_KEY_JSON = os.environ.get("FIREBASE_KEY_JSON")  # base64 encoded service account JSON
FIREBASE_DB_URL = os.environ.get("FIREBASE_DB_URL")  # Realtime DB URL
MAX_IMAGES = int(os.environ.get("MAX_IMAGES", 4))  # কতগুলো ছবি পোস্ট করবে (1..4)
POST_AS_CAROUSEL = os.environ.get("POST_AS_CAROUSEL", "true").lower() == "true"
TIMEOUT = 20

# -----------------------------
# Install/check firebase-admin
# -----------------------------
try:
    import firebase_admin
except ImportError:
    import subprocess
    subprocess.check_call(["python", "-m", "pip", "install", "firebase-admin"])
    import firebase_admin

# Gemini init
if not GEN_API_KEY:
    print("❌ GEMINI_API_KEY missing.")
    raise SystemExit(1)

genai.configure(api_key=GEN_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

# Firebase init
import base64, tempfile
if not FIREBASE_KEY_JSON or not FIREBASE_DB_URL:
    print("❌ Firebase config missing.")
    raise SystemExit(1)
key_bytes = base64.b64decode(FIREBASE_KEY_JSON)
temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
temp_file.write(key_bytes)
temp_file.close()
cred = credentials.Certificate(temp_file.name)
firebase_admin.initialize_app(cred, {'databaseURL': FIREBASE_DB_URL})
ref = db.reference('posted_articles')

# -----------------------------
# 2️⃣ Helpers
# -----------------------------

def safe_gemini_text(resp):
    try:
        if hasattr(resp, "text") and resp.text:
            return resp.text.strip()
        cand = resp.candidates[0]
        parts = getattr(cand, "content", getattr(cand, "contents", None))
        if parts and hasattr(parts, "parts"):
            return parts.parts[0].text.strip()
        if hasattr(cand, "content") and isinstance(cand.content, list):
            return cand.content[0].text.strip()
    except Exception:
        pass
    return ""


def get_soup(url):
    r = requests.get(url, timeout=TIMEOUT, headers={
        "User-Agent": "Mozilla/5.0"
    })
    r.raise_for_status()
    return BeautifulSoup(r.content, "html.parser")


def extract_listing_first_article(list_url):
    soup = get_soup(list_url)
    candidates = ["li.bbc-t44f9r", "li[data-testid='edinburgh-card']"]
    first = None
    for sel in candidates:
        first = soup.select_one(sel)
        if first:
            break
    if not first:
        return None
    h2 = first.select_one("h2 a") or first.find("a")
    if not h2:
        return None
    title = h2.get_text(strip=True)
    href = h2.get("href", "").strip()
    article_url = urljoin("https://www.bbc.com", href)
    img = first.find("img")
    feature_image = img.get("src") if img else None
    return {"title": title, "url": article_url, "feature_image": feature_image}


def extract_article_images(article_url, max_images=4):
    imgs = []
    try:
        soup = get_soup(article_url)
        for tag in soup.select("article img, figure img, .ssrcss-uf6wea-RichTextComponentWrapper img"):
            src = tag.get("src") or tag.get("data-src")
            if src and src.startswith("http") and src not in imgs:
                imgs.append(src)
            if len(imgs) >= max_images:
                break
    except Exception as e:
        print("⚠️ Image parse error:", e)
    return imgs

# -----------------------------
# 3️⃣ Scrape latest article
# -----------------------------
item = extract_listing_first_article(URL)
if not item:
    print("❌ No article found. Exiting.")
    raise SystemExit(0)

title = item['title']
article_url = item['url']
feature_image = item.get('feature_image')

# Firebase duplicate check
posted_list = ref.get() or []
if article_url in posted_list:
    print("❌ Duplicate detected in Firebase. Skipping post.")
    raise SystemExit(0)

images = extract_article_images(article_url, MAX_IMAGES)
if feature_image and feature_image not in images:
    images = [feature_image] + images
images = images[:MAX_IMAGES] if images else ([] if not feature_image else [feature_image])

# -----------------------------
# 4️⃣ Generate content (Summary, Variations, Hashtags)
# -----------------------------
summary_prompt = f"""
তুমি একজন সোশ্যাল মিডিয়া কপিরাইটার। নিচের নিউজের জন্য ২–৩ লাইনের ছোট বাংলা সারাংশ লিখো।
শিরোনাম: {title}
লিংক: {article_url}
"""
summary_text = safe_gemini_text(model.generate_content(summary_prompt))
if not summary_text:
    print("❌ Gemini summary generate হয়নি।")
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
# 5️⃣ Post to Facebook (Photo upload / Carousel)
# -----------------------------
if not FB_PAGE_ID or not FB_ACCESS_TOKEN:
    print("❌ FB credentials missing.")
    raise SystemExit(1)

uploaded_media_ids = []
if images:
    for idx, img_url in enumerate(images):
        try:
            resp = requests.post(f"https://graph.facebook.com/v17.0/{FB_PAGE_ID}/photos", data={"url": img_url, "published": False, "access_token": FB_ACCESS_TOKEN}, timeout=TIMEOUT)
            data = resp.json()
            if resp.status_code == 200 and "id" in data:
                uploaded_media_ids.append(data["id"])
                print(f"✅ Uploaded image {idx+1}/{len(images)}")
            else:
                print("⚠️ Photo upload failed:", data)
        except Exception as e:
            print("⚠️ Photo upload error:", e)

# Post to FB
if not uploaded_media_ids:
    print("ℹ️ Fallback to link post.")
    result = requests.post(f"https://graph.facebook.com/v17.0/{FB_PAGE_ID}/feed", data={"message": message, "link": article_url, "access_token": FB_ACCESS_TOKEN}, timeout=TIMEOUT).json()
else:
    if POST_AS_CAROUSEL and len(uploaded_media_ids) > 1:
        payload = {"message": message, "access_token": FB_ACCESS_TOKEN}
        multipart = [(f"attached_media[{i}]", json.dumps({"media_fbid": mid})) for i, mid in enumerate(uploaded_media_ids)]
        req = requests.Request("POST", f"https://graph.facebook.com/v17.0/{FB_PAGE_ID}/feed", data=payload, files=multipart).prepare()
        s = requests.Session()
        result = s.send(req, timeout=TIMEOUT).json()
    else:
        first_media = uploaded_media_ids[0]
        result = requests.post(f"https://graph.facebook.com/v17.0/{FB_PAGE_ID}/photos", data={"caption": message, "access_token": FB_ACCESS_TOKEN, "object_attachment": first_media, "published": True}, timeout=TIMEOUT).json()

print("Facebook Response:", result)

# -----------------------------
# 6️⃣ Log successful post to Firebase
# -----------------------------
if isinstance(result, dict) and "id" in result:
    print(f"🎉 Post Successful! Post ID: {result['id']}")
    posted_list.append(article_url)
    ref.set(posted_list)
else:
    print("❌ Post failed or no ID returned.")
