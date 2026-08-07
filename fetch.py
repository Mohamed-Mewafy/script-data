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
    raise ValueError("⚠️ تنبيه: يرجى التأكد من ضبط متغيرات البيئة SUPABASE_URL و SUPABASE_KEY بشكل صحيح.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def clean_text(text):
    if not text:
        return ""
    text = re.sub(r'[\"\'\[\]\{\}]', '', text)
    return " ".join(text.split()).strip()

def clean_title(raw_title):
    title = raw_title.replace("مشاهدة", "").replace("فيلم", "").replace("مسلسل", "")
    title = title.replace("مترجم", "").replace("مدبلج", "").replace("اكوام", "").replace("Akwam", "")
    title = title.split("|")[0].split("-")[0]
    return clean_text(title)

def extract_series_name_from_title(raw_title):
    if not raw_title:
        return ""
    name = re.sub(r'^(مشاهدة|تحميل)?\s*(مسلسل|انمي|برنامج)?\s*', '', raw_title).strip()
    name = re.sub(r'\s*(الموسم|الحلقة|مترجم|مدبلج|اكوام|Akwam|-|\|).*', '', name, flags=re.IGNORECASE).strip()
    return clean_text(name)

def extract_season_and_episode(text):
    season_num = 1
    episode_num = 1
    
    if not text:
        return season_num, episode_num

    # 1. صيغة S01E01
    s_e_match = re.search(r'S(\d+)\s*E(\d+)', text, re.IGNORECASE)
    if s_e_match:
        return int(s_e_match.group(1)), int(s_e_match.group(2))

    arabic_numbers = {
        "الاول": 1, "الأول": 1, "الاولى": 1,
        "الثاني": 2, "التاني": 2, "الثانية": 2,
        "الثالث": 3, "التالت": 3, "الثالثة": 3,
        "الرابع": 4, "الرابعة": 4,
        "الخامس": 5, "الخامسة": 5,
        "السادس": 6, "السادسة": 6,
        "السابع": 7, "السابعة": 7,
        "الثامن": 8, "الثامنة": 8,
        "التاسع": 9, "التاسعة": 9,
        "العاشر": 10, "العاشرة": 10
    }

    # 2. استخراج الموسم
    season_match = re.search(r'(?:الموسم|Season)\s*(?:الـ|ال)?\s*(\d+)', text, re.IGNORECASE)
    if season_match:
        season_num = int(season_match.group(1))
    else:
        season_word_match = re.search(r'(?:الموسم|Season)\s*([أ-ي]+)', text, re.IGNORECASE)
        if season_word_match and season_word_match.group(1) in arabic_numbers:
            season_num = arabic_numbers[season_word_match.group(1)]

    # 3. استخراج الحلقة
    episode_match = re.search(r'(?:الحلقة|Episode)\s*(?:الـ|ال)?\s*(\d+)', text, re.IGNORECASE)
    if episode_match:
        episode_num = int(episode_match.group(1))
    else:
        ep_word_match = re.search(r'(?:الحلقة|Episode)\s*([أ-ي]+)', text, re.IGNORECASE)
        if ep_word_match and ep_word_match.group(1) in arabic_numbers:
            episode_num = arabic_numbers[ep_word_match.group(1)]

    # حماية ضد الأرقام غير المنطقية
    if season_num > 20: 
        season_num = 1
        
    return season_num, episode_num

def shorten_link_via_shrinkme(original_url):
    if not original_url: 
        return original_url
    if "shrinkme.io" in original_url or "shrinkme.click" in original_url: 
        return original_url
    try:
        encoded_url = urllib.parse.quote(original_url)
        api_url = f"https://shrinkme.io/api?api={SHRINKME_API_TOKEN}&url={encoded_url}"
        response = requests.get(api_url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success" and data.get("shortenedUrl"):
                return data.get("shortenedUrl")
    except Exception: 
        pass
    return original_url

def get_tmdb_poster(title):
    try:
        clean_name = re.sub(r'[\d\-\_\:\,\.\(\)]', ' ', title)
        clean_name = clean_text(clean_name)
        if not clean_name or len(clean_name) < 2: 
            return "غير متوفر"
        query = urllib.parse.quote(clean_name)
        url = f"https://api.themoviedb.org/3/search/multi?api_key=3f4534f3c7e1451f28b49231f47d3c3d&query={query}&language=ar"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            results = data.get("results", [])
            for res in results:
                if res.get("poster_path"): 
                    return f"https://image.tmdb.org/t/p/w500{res.get('poster_path')}"
    except Exception: 
        pass
    return "غير متوفر"

def fetch_download_links_only(page, item_page_url):
    raw_download_links = []
    download_page_url = f"{item_page_url.rstrip('/')}/download"
    try:
        page.goto(download_page_url, wait_until="domcontentloaded", timeout=15000)
        time.sleep(2)
        links = page.evaluate("""() => Array.from(document.querySelectorAll('a[href]')).map(a => a.href).filter(h => h && !h.includes('akwams.org'))""")
        for link in links:
            if link and link not in raw_download_links: 
                raw_download_links.append(link)
    except Exception: 
        pass
    return list(set([shorten_link_via_shrinkme(l) for l in raw_download_links]))

def fetch_streaming_links_with_clicking(page, item_page_url):
    watch_page_url = f"{item_page_url.rstrip('/')}/watch/"
    extracted = []
    try:
        page.goto(watch_page_url, wait_until="domcontentloaded", timeout=15000)
        time.sleep(3)
        buttons = page.locator('button:has-text("سيرفر"), a:has-text("سيرفر")').all()
        for btn in buttons:
            try:
                if btn.is_visible():
                    btn.click(timeout=1000)
                    time.sleep(1)
                    frame_url = page.evaluate("() => document.querySelector('iframe')?.src")
                    if frame_url and "akwams" not in frame_url: 
                        extracted.append(frame_url)
            except Exception: 
                pass
    except Exception: 
        pass
    return list(set(extracted))

def process_series_item(page, item_page_url):
    try:
        page.goto(item_page_url, wait_until="domcontentloaded", timeout=15000)
    except Exception: 
        return
    
    title = page.title()
    
    # 🛑 فلترة صفحات الخطأ أو الروابط الميتة
    if not title or "Page Not Found" in title or "404" in title:
        print(f"⚠️ تجاهل رابط غير صالح أو صفحة غير موجودة: {item_page_url}")
        return

    series_name = extract_series_name_from_title(title)
    season_number, episode_number = extract_season_and_episode(title)
    
    if not series_name or len(series_name) < 2 or series_name.lower() in ["s1e1", "الحلقة"]: 
        return

    try:
        series = supabase.table("tv_series").select("id").ilike("title", f"%{series_name}%").execute()
        if series.data:
            s_id = series.data[0]["id"]
            if supabase.table("episodes_cima").select("id").eq("series_id", s_id).eq("season_number", season_number).eq("episode_number", episode_number).execute().data:
                print(f"⏭️ تخطي (موجود مسبقاً): {series_name} S{season_number}E{episode_number}")
                return
    except Exception: 
        pass

    print(f"📺 معالجة: {series_name} | موسم {season_number} - حلقة {episode_number}")
    
    series_id = None
    existing = supabase.table("tv_series").select("id").ilike("title", f"%{series_name}%").execute()
    if existing.data: 
        series_id = existing.data[0]["id"]
    else:
        res = supabase.table("tv_series").insert({
            "title": series_name, 
            "poster_url": get_tmdb_poster(series_name), 
            "category_type": "مسلسلات اجنبي"
        }).execute()
        if res.data: 
            series_id = res.data[0]["id"]
    
    if not series_id: 
        return
    
    streaming_links = fetch_streaming_links_with_clicking(page, item_page_url)
    download_links = fetch_download_links_only(page, item_page_url)
    final_watch_url = streaming_links[0] if streaming_links else None

    episode_data = {
        "series_id": series_id,
        "title": f"الحلقة {episode_number}",
        "season_number": season_number,
        "episode_number": episode_number,
        "watch_url": final_watch_url,
        "direct_links": {
            "streaming_links": streaming_links, 
            "download_links": download_links
        }
    }
    
    try:
        supabase.table("episodes_cima").insert(episode_data).execute()
        print("✅ تم الحفظ بنجاح")
    except Exception as e:
        print(f"❌ خطأ أثناء الحفظ: {e}")

def scrape_section(page, base_url, section_type):
    page_num = 1
    while True:
        url = f"{base_url}/page/{page_num}/" if page_num > 1 else base_url
        resp = page.goto(url)
        if resp and resp.status == 404: 
            break
        links = page.evaluate("() => Array.from(document.querySelectorAll('a[href]')).map(a => a.href).filter(h => h.includes('akwams.org/') && !h.includes('/category/'))")
        for link in set(links):
            if section_type == "series": 
                process_series_item(page, link)
        page_num += 1

def scrape_akwam_site():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        scrape_section(page, "https://akwams.org/category/مسلسلات-اجنبي", "series")
        browser.close()

if __name__ == "__main__":
    scrape_akwam_site()
