import os
import requests
import json
from urllib.parse import quote

# -----------------------------
# Duplicate check via botlink.gt.tc
# -----------------------------
def check_duplicate(title):
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
    return False  # fail-safe

# -----------------------------
# Download image with headers + fallback
# -----------------------------
def download_image(url, filename):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, stream=True, timeout=10, headers=headers, verify=False)
        if r.status_code == 200:
            with open(filename, 'wb') as f:
                for chunk in r.iter_content(1024):
                    f.write(chunk)
            return True
        else:
            print("❌ Failed to download:", url, r.status_code)
    except Exception as e:
        print("❌ Image download error:", e, url)
    return False

# -----------------------------
# Highlight keywords in text
# -----------------------------
def highlight_keywords(text, keywords):
    for kw in keywords:
        if kw in text:
            text = text.replace(kw, f"⚡{kw}⚡")
    return text

# -----------------------------
# Post comment to FB
# -----------------------------
def post_fb_comment(post_id, comment_text):
    FB_ACCESS_TOKEN = os.environ.get("FB_ACCESS_TOKEN")
    fb_comment_url = f"https://graph.facebook.com/v17.0/{post_id}/comments"
    data = {"message": comment_text, "access_token": FB_ACCESS_TOKEN}
    try:
        resp = requests.post(fb_comment_url, data=data)
        return resp.json()
    except Exception as e:
        print("❌ Comment failed:", e)
        return None
