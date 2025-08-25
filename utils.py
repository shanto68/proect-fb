import requests
import json

def check_duplicate(url):
    """
    Check if URL is duplicate using botlink.gt.tc
    Returns True if duplicate, False if unique
    """
    try:
        resp = requests.get(f"https://botlink.gt.tc/?urlcheck={url}", timeout=10)
        if "duplicate.php" in resp.text:
            return True
        elif "unique.php" in resp.text:
            # Submit URL if unique
            requests.get(f"https://botlink.gt.tc/?urlsubmit={url}", timeout=10)
            return False
    except Exception as e:
        print("❌ Duplicate check failed:", e)
    return False

def download_image(url, filename):
    try:
        r = requests.get(url, stream=True)
        if r.status_code == 200:
            with open(filename, 'wb') as f:
                for chunk in r.iter_content(1024):
                    f.write(chunk)
            return True
    except:
        pass
    return False

