import feedparser
import google.generativeai as genai
import requests
import os

# Environment Variables (Secrets from GitHub)
RSS_URL = os.getenv("RSS_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
FB_PAGE_ID = os.getenv("FB_PAGE_ID")
FB_ACCESS_TOKEN = os.getenv("FB_ACCESS_TOKEN")

# 1) RSS থেকে লেটেস্ট টাইটেল আনা
feed = feedparser.parse(RSS_URL)
latest_title = feed.entries[0].title

# 2) Gemini API দিয়ে নিউজ বানানো
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-pro")
prompt = f"এই টাইটেল থেকে আকর্ষণীয় নিউজ লিখুন (মানুষ পড়তে চাইবে এমনভাবে): {latest_title}"
response = model.generate_content(prompt)
news_content = response.text

# 3) ফেসবুকে পোস্ট করা
post_url = f"https://graph.facebook.com/{FB_PAGE_ID}/feed"
payload = {
    "message": news_content,
    "access_token": FB_ACCESS_TOKEN
}
res = requests.post(post_url, data=payload)
print(res.json())
