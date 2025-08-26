import requests
from urllib.parse import quote

# -----------------------------
# Duplicate check via botlink.gt.tc (HTTP only)
# -----------------------------
def check_duplicate(title):
    encoded_title = quote(title)
    try:
        url_check = f"http://botlink.gt.tc/?urlcheck={encoded_title}"
        resp = requests.get(url_check, timeout=10)
        if "duplicate.php" in resp.text:
            return True
        elif "unique.php" in resp.text:
            submit_url = f"http://botlink.gt.tc/?urlsubmit={encoded_title}"
            requests.get(submit_url, timeout=10)
            return False
    except Exception as e:
        print("❌ Duplicate check failed:", e)
    return False

# -----------------------------
# Download image with headers + fallback
# -----------------------------
def download_image(url, filename):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, stream=True, timeout=10)
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
# Post comment to FB
# -----------------------------
def post_fb_comment(post_id, comment_text):
    import os
    FB_ACCESS_TOKEN = os.environ.get("FB_ACCESS_TOKEN")
    fb_comment_url = f"https://graph.facebook.com/v17.0/{post_id}/comments"
    data = {"message": comment_text, "access_token": FB_ACCESS_TOKEN}
    try:
        resp = requests.post(fb_comment_url, data=data)
        return resp.json()
    except Exception as e:
        print("❌ Comment failed:", e)
        return None
