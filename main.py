import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import urllib3
from utils import download_image, highlight_keywords, post_fb_comment, is_duplicate, log_post
import google.generativeai as genai

# -----------------------------
# ⚡ Warnings hide
# -----------------------------
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# -----------------------------
# CONFIG
# -----------------------------
FB_PAGE_ID = os.environ.get("FB_PAGE_ID")
FB_ACCESS_TOKEN = os.environ.get("FB_ACCESS_TOKEN")
GEN_API_KEY = os.environ.get("GEMINI_API_KEY")
TOPIC_URL = os.environ.get("TOPIC_URL")  # Google News topic page

genai.configure(api_key=GEN_API_KEY)

# -----------------------------
# 1️⃣ Collect article links from Google News
# -----------------------------
def get_google_news_articles(topic_url):
    headers = {"User-Agent": "Mozilla/5.0"}
    print("🔹 Fetching Google News topic page...")
    r = requests.get(topic_url, headers=headers, verify=False)
    soup = BeautifulSoup(r.text, "html.parser")
    articles = []
    for a in soup.select("a.DY5T1d"):
        link = urljoin("https://news.google.com", a["href"].replace("./", ""))
        title = a.get_text(strip=True)
        articles.append({"title": title, "link": link})
    print(f"🔹 {len(articles)} articles found on topic page.")
    return articles

# -----------------------------
# 2️⃣ Scrape publisher page for content + images
# -----------------------------
def scrape_article_content(article_url):
    headers = {"User-Agent": "Mozilla/5.0"}
    print(f"🔹 Scraping article: {article_url}")
    try:
        r = requests.get(article_url, headers=headers, timeout=10, verify=False)
        soup = BeautifulSoup(r.text, "html.parser")
        paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
        text = "\n".join(paragraphs)

        imgs = []
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src")
            if src and src.startswith("http"):
                imgs.append(src)
        print(f"🔹 {len(imgs)} images found in article.")
        return {"text": text, "images": list(set(imgs))}
    except Exception as e:
        print("❌ Article scrape failed:", e)
        return {"text": "", "images": []}

# -----------------------------
# 3️⃣ Gemini AI post generator
# -----------------------------
def ai_generate_post(title, content):
    prompt = f"""
Article Title: {title}
Content: {content[:1500]}

Task:
1. Rewrite title for FB eye-catching style.
2. Create short 3-5 line engaging FB post.
3. Suggest 8-12 trending hashtags (Bangla + English).
4. Generate one engaging comment for FB post.
"""
    model = genai.GenerativeModel("gemini-2.5-flash")
    print("🔹 Generating AI post content...")
    resp = model.generate_content(prompt)
    return resp.text

# -----------------------------
# 4️⃣ Post to Facebook
# -----------------------------
def post_to_facebook(content, images):
    fb_api_url = f"https://graph.facebook.com/v17.0/{FB_PAGE_ID}/photos"
    results = []
    if images:  # only post images if available
        for idx, img_file in enumerate(images):
            data = {"caption": content if idx==0 else "", "access_token": FB_ACCESS_TOKEN}
            with open(img_file, "rb") as f:
                files = {"source": f}
                print(f"🔹 Posting image {img_file} to FB...")
                r = requests.post(fb_api_url, data=data, files=files, verify=False)
            results.append(r.json())
    else:  # no images, post text only
        print("🔹 No images found. Posting text-only FB post...")
        data = {"message": content, "access_token": FB_ACCESS_TOKEN}
        r = requests.post(f"https://graph.facebook.com/v17.0/{FB_PAGE_ID}/feed", data=data, verify=False)
        results.append(r.json())
    return results

# -----------------------------
# RUN
# -----------------------------
articles = get_google_news_articles(TOPIC_URL)
for art in articles[:3]:  # প্রথম ৩টা article test
    print(f"\n==============================")
    print("Article Title:", art["title"])

    if is_duplicate(art["title"]):
        print("⚠️ Duplicate article. Skipping.")
        continue

    scraped = scrape_article_content(art["link"])
    text = scraped["text"] or art["title"]
    imgs = scraped["images"][:3]  # only existing images

    # Download images locally
    local_imgs = []
    for idx, img in enumerate(imgs):
        filename = f"article_{idx}.jpg"
        if download_image(img, filename):
            local_imgs.append(filename)

    print("Local images ready:", local_imgs if local_imgs else "No images")

    # Gemini AI generate post + hashtags + comment
    ai_output = ai_generate_post(art["title"], text)
    print("AI Generated Content Preview:\n", ai_output[:500])

    # FB Post
    fb_resp = post_to_facebook(ai_output, local_imgs)
    print("FB Response:", fb_resp)

    # Log article
    log_post(art["title"])
