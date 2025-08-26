import requests
import json
import os  # << added
import urllib3

# Suppress insecure request warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def check_duplicate(title):
    """Check if article title is duplicate using botlink.gt.tc"""
    from urllib.parse import quote
    encoded_title = quote(title)
    try:
        resp = requests.get(f"https://botlink.gt.tc/?urlcheck={encoded_title}", timeout=10, verify=False)
        if "duplicate.php" in resp.text:
            return True
        elif "unique.php" in resp.text:
            # Submit URL if unique
            requests.get(f"https://botlink.gt.tc/?urlsubmit={encoded_title}", timeout=10, verify=False)
            return False
    except Exception as e:
        print("❌ Duplicate check failed:", e)
        return False

def download_image(url, filename):
    try:
        r = requests.get(url, stream=True, timeout=10)
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
    """Post a comment on a Facebook photo post"""
    fb_comment_url = f"https://graph.facebook.com/v17.0/{post_id}/comments"
    data = {"message": comment_text, "access_token": os.environ.get("FB_ACCESS_TOKEN")}
    try:
        resp = requests.post(fb_comment_url, data=data)
        result = resp.json()
        print("Comment Response:", result)
        return result
    except Exception as e:
        print("❌ Comment failed:", e)
        return None
