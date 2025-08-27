import os
import json
import requests
from bs4 import BeautifulSoup
from newspaper import Article
import google.generativeai as genai
from utils import check_duplicate, download_image, highlight_keywords, post_fb_comment

# -----------------------------
# 1️⃣ Configuration
# -----------------------------
NEWS_URL = "https://news.google.com/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx1YlY4U0FtSnVHZ0pDUkNnQVAB?hl=bn&gl=BD&ceid=BD%3Abn"
FB_PAGE_ID = os.environ.get("FB_PAGE_ID")
FB_ACCESS_TOKEN = os.environ.get("FB_ACCESS_TOKEN")
GEN_API_KEY = os.environ.get("GEMINI_API_KEY")
LOG_FILE = "posted_articles.json"

if not GEN_API_KEY:
    print("❌ GEMINI_API_KEY not provided.")
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
# 3️⃣ Scrape Google News Page
# -----------------------------
headers = {"User-Agent": "Mozilla/5.0"}
r = requests.get(NEWS_URL, headers=headers)
soup = BeautifulSoup(r.text, "html.parser")

article_link = None
article_title = None

for a in soup.select("a.WwrzSb"):
    title = a.get_text()
    link = "https://news.google.com" + a['href'][1:]
    if title not in posted_articles and not check_duplicate(title):
        article_title = title
        article_link = link
        break

if not article_link:
    print("⚠️ No new articles found.")
    exit()

print("📰 Latest Article:", article_title)
print("🔗 URL:", article_link)

# -----------------------------
# 4️⃣ Extract Full Content & Images
# -----------------------------
try:
    article = Article(article_link, language="bn")
    article.download()
    article.parse()
    full_content = article.text
    top_image = article.top_image
except Exception as e:
    print("❌ Full content extraction failed:", e)
    full_content = article_title
    top_image = None

candidate_images = []
if top_image:
    candidate_images.append(top_image)

# -----------------------------
# Auto-detect highest resolution images
# -----------------------------
def pick_high_res(images):
    scored = []
    for url in images:
        try:
            r = requests.head(url, timeout=5, headers=headers, verify=False)
            size = int(r.headers.get('Content-Length', 0))
            scored.append((size, url))
        except:
            scored.append((0, url))
    if scored:
        scored.sort(reverse=True)
        return [url for size, url in scored]
    return images

high_res_images = pick_high_res(candidate_images)

# -----------------------------
# Download images locally
# -----------------------------
local_images = []
for idx, img_url in enumerate(high_res_images):
    filename = f"img_{idx}.jpg"
    if download_image(img_url, filename):
        local_images.append(filename)
    if idx >= 4:
        break

# -----------------------------
# 5️⃣ Generate FB Post Content
# -----------------------------
model = genai.GenerativeModel("gemini-2.5-flash")

summary_prompt = f"""
নিচের নিউজ কনটেন্টকে বাংলায় ৩-৪ লাইনের আকর্ষণীয়, 
human-like ফেসবুক পোস্ট স্টাইলে সাজাও। ইমোজি ব্যবহার করবে।
নিউজ কনটেন্ট:
---
{full_content}
"""

summary_resp = model.generate_text(summary_prompt)
summary_text = summary_resp.text.strip()

keywords = article_title.split()[:3]
highlighted_text = highlight_keywords(summary_text, keywords)

hashtag_prompt = f"""
Generate 3-5 relevant Bengali hashtags for this news article.
Title: {article_title}
Summary: {summary_text}
"""
hashtag_resp = model.generate_text(hashtag_prompt)
hashtags = [tag.strip() for tag in hashtag_resp.text.split() if tag.startswith("#")]
hashtags_text = " ".join(hashtags)

fb_content = f"{highlighted_text}\n\n{hashtags_text}"

# -----------------------------
# 6️⃣ Post to Facebook
# -----------------------------
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

# -----------------------------
# 7️⃣ Auto-comment
# -----------------------------
if fb_result:
    first_post_id = fb_result[0].get("id")
    if first_post_id:
        comment_prompt = f"""
        Article Title: {article_title}
        Summary: {summary_text}
        Write a short, friendly, engaging comment in Bengali for this Facebook post.
        Include emojis naturally.
        """
        comment_resp = model.generate_text(comment_prompt)
        comment_text = comment_resp.text.strip()
        post_fb_comment(first_post_id, comment_text)

# -----------------------------
# 8️⃣ Log successful post
# -----------------------------
posted_articles.append(article_title)
with open(LOG_FILE, "w") as f:
    json.dump(posted_articles, f)

print("✅ Article posted successfully!")
