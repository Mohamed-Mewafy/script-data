import os
import re
import time
import urllib.parse
import urllib.request
import json
import requests
from playwright.sync_api import sync_playwright
from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
SHRINKME_API_TOKEN = os.environ.get("SHRINKME_API_TOKEN")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("⚠️ تأكد من ضبط متغيرات البيئة SUPABASE_URL و SUPABASE_KEY.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def clean_text(text):
    return " ".join(re.sub(r'[\"\'\[\]\{\}]', '', text).split()).strip()

def extract_series_name_from_title(raw_title):
    name = re.sub(r'^(مشاهدة|تحميل)?\s*(مسلسل|انمي|برنامج)?\s*', '', raw_title).strip()
    name = re.sub(r'\s*(الموسم|Season|الحلقة|مترجم|مدبلج|اكوام|Akwam|-|\|).*', '', name, flags=re.IGNORECASE).strip()
    return clean_text(name)

def extract_season_and_episode(text):
    s_match = re.search(r'(?:الموسم|Season)\s*(?:الـ|ال)?\s*(\d+)', text, re.IGNORECASE)
    e_match = re.search(r'(?:الحلقة|Episode)\s*(?:الـ|ال)?\s*(\d+)', text, re.IGNORECASE)
    return int(s_match.group(1)) if s_match else 1, int(e_match.group(1)) if e_match else 1

def fetch_streaming_links_with_clicking(page, item_page_url):
    extracted = []
    try:
        page.goto(f"{item_page_url.rstrip('/')}/watch/", wait_until="domcontentloaded", timeout=15000)
        time.sleep(2)
        buttons = page.locator('button:has-text("سيرفر"), a:has-text("سيرفر")').all()
        for btn in buttons[:5]:
            if btn.is_visible():
                btn.click()
                time.sleep(1)
                frame = page.evaluate("() => document.querySelector('iframe')?.src")
                if frame and "akwams" not in frame: extracted.append(frame)
    except: pass
    return list(set(extracted))

def process_series_item(page, item_page_url):
    try:
        page.goto(item_page_url, wait_until="domcontentloaded", timeout=10000)
        title = clean_text(page.title())
    except: return

    base_name = extract_series_name_from_title(title)
    s_num, e_num = extract_season_and_episode(title)
    
    unique_season_title = f"{base_name} - الموسم {s_num}"

    # 1. البحث عن هذا الموسم أو إضافته
    existing = supabase.table("tv_series").select("id").eq("title", unique_season_title).execute()
    
    if existing.data:
        series_id = existing.data[0]["id"]
    else:
        new_series = supabase.table("tv_series").insert({
            "title": unique_season_title,
            "category_type": "مسلسلات اجنبي"
        }).execute()
        series_id = new_series.data[0]["id"]

    print(f"    📺 جاري حفظ: {unique_season_title} | حلقة {e_num}")
    
    links = fetch_streaming_links_with_clicking(page, item_page_url)
    
    episode_data = {
        "series_id": series_id,
        "title": f"الحلقة {e_num}",
        "season_number": s_num,
        "episode_number": e_num,
        "watch_url": links[0] if links else None,
        "direct_links": {"streaming_links": links}
    }
    
    # 2. استخدام Insert مباشر مع التحقق لمنع الأخطاء
    try:
        # فحص هل الحلقة موجودة مسبقاً بنفس المسلسل ورقم الحلقة لتجنب التكرار برمجياً
        check_ep = supabase.table("episodes_cima").select("id").eq("series_id", series_id).eq("season_number", s_num).eq("episode_number", e_num).execute()
        
        if check_ep.data:
            # تحديث الرابط لو موجودة
            ep_id = check_ep.data[0]["id"]
            supabase.table("episodes_cima").update(episode_data).eq("id", ep_id).execute()
            print(f"    🔄 تم تحديث الحلقة الحالية بنجاح.")
        else:
            # إضافتها لو مش موجودة
            supabase.table("episodes_cima").insert(episode_data).execute()
            print(f"    ✅ تم حفظ الحلقة بنجاح.")
    except Exception as e:
        print(f"    ⚠️ خطأ في الحفظ: {e}")

def scrape_akwam_site():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page_num = 1
        
        while True:
            url = f"https://akwams.org/category/مسلسلات-اجنبي/page/{page_num}/"
            page.goto(url)
            
            links = page.evaluate("""() => Array.from(document.querySelectorAll('a[href]')).map(a => a.href)
                                     .filter(h => h.includes('akwams.org') && h.split('/').length > 4)""")
            
            unique_links = list(set(links))
            if not unique_links: break
            
            for link in unique_links:
                process_series_item(page, link)
            
            page_num += 1
        browser.close()

if __name__ == "__main__":
    scrape_akwam_site()
