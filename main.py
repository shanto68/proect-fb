import os
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote
from newspaper import Article
import google.generativeai as genai
import warnings

# -----------------------------
#  Utils
# -----------------------------
def check_duplicate(title):
    """Check if article title is duplicate using botlink.gt.tc"""
    encoded_title = quote(title)
    try:
        resp = requests.get(f"https://botlink.gt.tc/?urlcheck={encoded_title}", timeout=10, verify=False)
        if "duplicate.php" in resp.text:
            return True
        elif "unique.php" in resp.text:
            requests.get(f"https://botlink.gt.tc/?urlsubmit={encoded_title}", timeout=10, verify=False)
            return False
    except Exception as e:
        print("❌ Duplicate check failed:", e)
        return False

def download_image(url, filename):
    try:
        r = requests.get(url, stream=True, timeout=15)
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

def post_fb_comment(post_id, comment_text):
    fb_comment_url = f"https://graph.facebook.com/v17.0/{post_id}/comments"
    data = {"message": comment_text, "access_token": os.environ.get("FB_ACCESS_TOKEN")}
    try:
        resp = requests.post(fb_comment_url, data=data)
        return resp.json()
    except Exception as e:
        print("❌ Comment failed:", e)
        return None

# -----------------------------
#  Configuration
# -----------------------------
RSS_URL = "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx1YlY4U0FtSnVHZ0pDUkNnQVAB?hl=bn&gl=BD&ceid=BD%3Abn"
FB_PAGE_ID = os.environ.get("FB_PAGE_ID")
FB_ACCESS_TOKEN = os.environ.get("FB_ACCESS_TOKEN")
GEN_API_KEY = os.environ.get("GEMINI_API_KEY")
LOG_FILE = "posted_articles.json"

genai.configure(api_key=GEN_API_KEY)
warnings.filterwarnings("ignore", category=UserWarning, module='urllib3')  # HTTPS warnings ignore

# -----------------------------
#  Load posted articles
# -----------------------------
try:
    with open(LOG_FILE, "r") as f:
        posted_articles = json.load(f)
except:
    posted_articles = []

# -----------------------------
#  Scrape latest RSS article
# -----------------------------
resp = requests.get(RSS_URL)
soup = BeautifulSoup(resp.content, "xml")
item = soup.find("item")
if not item:
    print("❌ No article found in RSS.")
    exit()

title = item.title.text.strip()
article_url = item.link.text.strip()

# Duplicate check
if title in posted_articles or check_duplicate(title):
    print("❌ Already posted or duplicate. Exiting.")
    exit()

# -----------------------------
#  Full content extraction using Newspaper
# -----------------------------
try:
    article = Article(article_url, language='bn')
    article.download()
    article.parse()
    content = article.text.strip()
    if not content:
        content = title
except:
    content = title

# -----------------------------
#  Image detection (high-res first)
# -----------------------------
soup_html = BeautifulSoup(requests.get(article_url, verify=False, timeout=15).content, "html.parser")
image_urls = []
for img in soup_html.find_all("img"):
    srcset = img.get("srcset")
    if srcset:
        candidates = []
        for part in srcset.split(","):
            try:
                url_part, size_part = part.strip().split(" ")
                width = int(size_part.replace("w",""))
                candidates.append((width, url_part))
            except: pass
        if candidates:
            candidates.sort(reverse=True)
            image_urls.append(candidates[0][1])
    else:
        src = img.get("src")
        if src:
            image_urls.append(src)

# Download images
local_images = []
for i, url in enumerate(image_urls[:5]):  # Max 5 images
    fname = f"img_{i}.jpg"
    if download_image(url, fname):
        local_images.append(fname)

# -----------------------------
#  Generate FB content with Gemini
# -----------------------------
model = genai.GenerativeModel("gemini-2.5-flash")

summary_prompt = f"""
নিচের নিউজ কনটেন্টকে বাংলায় ৩–৪ লাইনের আকর্ষণীয়, সহজবোধ্য,
ফেসবুক পোস্ট স্টাইলে সাজাও। ইমোজি ব্যবহার করবে।
Article Content: {content}
"""
summary_resp = model.generate_content(summary_prompt)
summary_text = summary_resp.output_text.strip()

# Highlight first 3 keywords from title
highlighted_text = highlight_keywords(summary_text, title.split()[:3])

# Hashtags
hashtag_prompt = f"""
Generate 3-5 relevant Bengali hashtags for this news article.
Title: {title}
Summary: {summary_text}
"""
hashtag_resp = model.generate_content(hashtag_prompt)
hashtags = [tag.strip() for tag in hashtag_resp.output_text.split() if tag.startswith("#")]
hashtags_text = " ".join(hashtags)

fb_content = f"{highlighted_text}\n\n{hashtags_text}"

# -----------------------------
#  Post to Facebook
# -----------------------------
fb_api_url = f"https://graph.facebook.com/v17.0/{FB_PAGE_ID}/photos"
fb_result = []

if local_images:
    for idx, img_file in enumerate(local_images):
        data = {"caption": fb_content if idx==0 else "", "access_token": FB_ACCESS_TOKEN}
        files = {"source": open(img_file, "rb")}
        r = requests.post(fb_api_url, data=data, files=files)
        fb_result.append(r.json())
else:
    post_data = {"message": fb_content, "access_token": FB_ACCESS_TOKEN}
    r = requests.post(f"https://graph.facebook.com/v17.0/{FB_PAGE_ID}/feed", data=post_data)
    fb_result.append(r.json())

print("Facebook Response:", fb_result)

# -----------------------------
#  Auto-comment on first image
# -----------------------------
if local_images and fb_result:
    first_post_id = fb_result[0].get("id")
    if first_post_id:
        comment_prompt = f"""
        Article Title: {title}
        Summary: {summary_text}
        Write a short, friendly, engaging, and scroll-stopping comment in Bengali for this Facebook post.
        Include emojis naturally.
        """
        comment_resp = model.generate_content(comment_prompt)
        comment_text = comment_resp.output_text.strip()
        post_fb_comment(first_post_id, comment_text)

# -----------------------------
#  Log posted article
# -----------------------------
posted_articles.append(title)
with open(LOG_FILE, "w") as f:
    json.dump(posted_articles, f)
