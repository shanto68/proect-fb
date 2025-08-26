import os
import requests
import json
import logging
from urllib.parse import quote
from typing import Optional, Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Disable SSL warnings (use with caution)
requests.packages.urllib3.disable_warnings()

# -----------------------------
# Duplicate check via botlink.gt.tc
# -----------------------------
def check_duplicate(title: str, timeout: int = 10) -> bool:
    """
    Check if a title is duplicate using botlink.gt.tc service
    
    Args:
        title: The title to check for duplicates
        timeout: Request timeout in seconds
        
    Returns:
        bool: True if duplicate, False if unique
    """
    encoded_title = quote(title)
    session = requests.Session()
    
    try:
        # Check URL
        check_url = f"https://botlink.gt.tc/?urlcheck={encoded_title}"
        resp = session.get(check_url, timeout=timeout, verify=False)
        
        if resp.status_code != 200:
            logger.warning(f"Duplicate check returned status {resp.status_code}")
            return False
            
        if "duplicate.php" in resp.text:
            return True
        elif "unique.php" in resp.text:
            # Submit as unique
            submit_url = f"https://botlink.gt.tc/?urlsubmit={encoded_title}"
            session.get(submit_url, timeout=timeout, verify=False)
            return False
        else:
            logger.warning("Unexpected response from duplicate check service")
            return False
            
    except requests.exceptions.Timeout:
        logger.error("Duplicate check timed out")
    except requests.exceptions.RequestException as e:
        logger.error(f"Duplicate check failed: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in duplicate check: {e}")
    
    return False

# -----------------------------
# Download image with headers + fallback
# -----------------------------
def download_image(url: str, filename: str, timeout: int = 30) -> bool:
    """
    Download an image from URL and save to file
    
    Args:
        url: Image URL to download
        filename: Local filename to save the image
        timeout: Request timeout in seconds
        
    Returns:
        bool: True if download successful, False otherwise
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    try:
        with requests.get(url, stream=True, timeout=timeout, 
                         headers=headers, verify=False) as r:
            r.raise_for_status()
            
            with open(filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            # Verify file was created and has content
            if os.path.exists(filename) and os.path.getsize(filename) > 0:
                logger.info(f"Successfully downloaded image: {filename}")
                return True
            else:
                logger.error("Downloaded file is empty or doesn't exist")
                return False
                
    except requests.exceptions.RequestException as e:
        logger.error(f"Image download failed for {url}: {e}")
    except IOError as e:
        logger.error(f"File write error for {filename}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error downloading image: {e}")
    
    return False

# -----------------------------
# Highlight keywords in text
# -----------------------------
def highlight_keywords(text: str, keywords: list) -> str:
    """
    Highlight keywords in text with emoji markers
    
    Args:
        text: The text to process
        keywords: List of keywords to highlight
        
    Returns:
        str: Text with highlighted keywords
    """
    if not text or not keywords:
        return text
    
    # Case-insensitive highlighting while preserving original case
    for kw in keywords:
        if kw and kw.lower() in text.lower():
            # Find the actual case variant in the text
            pattern = re.compile(re.escape(kw), re.IGNORECASE)
            text = pattern.sub(f"⚡{kw}⚡", text)
    
    return text

# -----------------------------
# Post comment to FB
# -----------------------------
def post_fb_comment(post_id: str, comment_text: str) -> Optional[Dict[str, Any]]:
    """
    Post a comment to a Facebook post
    
    Args:
        post_id: Facebook post ID
        comment_text: Text of the comment to post
        
    Returns:
        Optional[Dict]: Facebook API response or None if failed
    """
    FB_ACCESS_TOKEN = os.environ.get("FB_ACCESS_TOKEN")
    
    if not FB_ACCESS_TOKEN:
        logger.error("Facebook access token not found in environment variables")
        return None
    
    if not comment_text.strip():
        logger.error("Comment text is empty")
        return None
    
    fb_comment_url = f"https://graph.facebook.com/v17.0/{post_id}/comments"
    
    data = {
        "message": comment_text,
        "access_token": FB_ACCESS_TOKEN
    }
    
    try:
        resp = requests.post(fb_comment_url, data=data, timeout=30)
        resp.raise_for_status()
        
        response_data = resp.json()
        
        if "error" in response_data:
            logger.error(f"Facebook API error: {response_data['error']}")
            return None
        
        logger.info("Comment posted successfully")
        return response_data
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Facebook comment request failed: {e}")
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Facebook response: {e}")
    except Exception as e:
        logger.error(f"Unexpected error posting comment: {e}")
    
    return None

# Example usage
if __name__ == "__main__":
    # Test duplicate check
    duplicate = check_duplicate("Test Title")
    print(f"Duplicate: {duplicate}")
    
    # Test image download
    # download_image("https://example.com/image.jpg", "test_image.jpg")
    
    # Test keyword highlighting
    text = "This is a test with important keywords"
    highlighted = highlight_keywords(text, ["test", "important"])
    print(f"Highlighted: {highlighted}")
