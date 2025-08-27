import os
import requests
import json

# -----------------------------
# Download image with headers + extension fix
# -----------------------------
def download_image(url, folder="images", name="img"):
    try:
        ext = url.split(".")[-1].split("?")[0]
        if ext.lower() not in ["jpg", "jpeg", "png", "webp"]:
            ext = "jpg"
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"{name}.{ext}")
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, stream=True, timeout=10, headers=headers, verify=False)
        if r.status_code == 200:
            with open(path, "wb") as f:
                for chunk in r.iter_content(1024):
                    f.write(chunk)
            return path
    except Exception as e:
        print("❌ Image download error:", e, url)
    return None

# -----------------------------
# Highlight keywords
# -----------------------------
def highlight_keywords(text, keywords):
    for kw in keywords:
        if kw in text:
            text = text.replace(kw, f"⚡{kw}⚡")
    return text

# -----------------------------
# Post comment to FB
# -----------------------------
def post_fb_comment(post_id, comment_text, access_token):
    url = f"https://graph.facebook.com/v17.0/{post_id}/comments"
    data = {"message": comment_text, "access_token": access_token}
    try:
        resp = requests.post(url, data=data)
        return resp.json()
    except Exception as e:
        print("❌ Comment failed:", e)
        return None

# -----------------------------
# Duplicate check
# -----------------------------
def is_duplicate(title, log_file="posted_articles.json"):
    try:
        with open(log_file, "r") as f:
            posted = json.load(f)
    except:
        posted = []

    if title in posted:
        return True
    return False

def log_post(title, log_file="posted_articles.json"):
    try:
        with open(log_file, "r") as f:
            posted = json.load(f)
    except:
        posted = []

    posted.append(title)
    with open(log_file, "w") as f:
        json.dump(posted, f, ensure_ascii=False, indent=2)
