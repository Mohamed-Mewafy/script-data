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

def get_tmdb_poster(title):
    """محاولة جلب البوستر مع دعم البحث بالعربية والإنجليزية لتجنب فقدان البوستر"""
    clean_name = re.sub(r'[\d\-\_\:\,\.\(\)]', ' ', title)
    clean_name = clean_text(clean_name)
    if not clean_name or len(clean_name) < 2:
        return None

    queries = [clean_name]
    # محاولة ترجمة بسيطة أو إزالة الكلمات الزائدة إذا وجدت
    for q in queries:
        try:
            encoded_query = urllib.parse.quote(q)
            # البحث العام (أفلام ومسلسلات) أو البحث المخصص
            url = f"https://api.themoviedb.org/3/search/multi?api_key=3f4534f3c7e1451f28b49231f47d3c3d&query={encoded_query}&language=ar"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())
                results = data.get("results", [])
                for res in results:
                    poster_path = res.get("poster_path")
                    if poster_path:
                        return f"https://image.tmdb.org/t/p/w500{poster_path}"
        except Exception:
            pass
    return None

def normalize_series_title(raw_title):
    name = re.sub(r'^(مشاهدة|تحميل)?\s*(مسلسل|انمي|برنامج)?\s*', '', raw_title).strip()
    
    season_num = 1
    s_match = re.search(r'(?:الموسم|Season)\s*(?:الـ|ال)?\s*(\d+)', name, re.IGNORECASE)
    if s_match:
        season_num = int(s_match.group(1))
    else:
        arabic_numbers = {"الاول": 1, "الأول": 1, "الاولى": 1, "الثاني": 2, "الثانية": 2, "الثالث": 3, "الرابع": 4, "الخامس": 5}
        for word, num in arabic_numbers.items():
            if word in name:
                season_num = num
                break

    clean_name = re.sub(r'\s*(الموسم|Season|الاول|الأول|الثاني|الثالث|الرابع|الحلقة|\d+|-|\||مترجم|مدبلج|اكوام|Akwam).*', '', name, flags=re.IGNORECASE).strip()
    clean_name = clean_text(clean_name)
    
    if not clean_name:
        clean_name = "مسلسل غير معروف"

    return f"{clean_name} - الموسم {season_num}", season_num, clean_name

def extract_episode_number(text):
    e_match = re.search(r'(?:الحلقة|Episode)\s*(?:الـ|ال)?\s*(\d+)', text, re.IGNORECASE)
    return int(e_match.group(1)) if e_match else 1

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
                if frame and "akwams" not in frame: 
                    extracted.append(frame)
    except: 
        pass
    return list(set(extracted))

def process_series_item(page, item_page_url):
    try:
        page.goto(item_page_url, wait_until="domcontentloaded", timeout=10000)
        title = clean_text(page.title())
    except: 
        return

    invalid_keywords = [
        "page not found", "404", "افلام", "أفلام", "انمي", "ات انمي", 
        "ات اجنبي", "ات اسيوية", "ات تركية", "ات كرتون", "ات وثائقية", 
        "رمضان", "برامج تلفزيونية", "عروض وحفلات", "تصنيف"
    ]
    if not title or any(kw in title.lower() for kw in invalid_keywords):
        return

    unique_season_title, s_num, raw_base_name = normalize_series_title(title)
    e_num = extract_episode_number(title)

    # 1. التحقق الذكي من وجود المسلسل لتجنب التكرار
    existing = supabase.table("tv_series").select("id, poster_url").eq("title", unique_season_title).execute()
    
    if existing.data:
        series_id = existing.data[0]["id"]
        current_poster = existing.data[0].get("poster_url")
        # إذا كان المسلسل موجوداً لكن ليس لديه بوستر، نحاول جلبه وتحديثه
        if not current_poster:
            new_poster = get_tmdb_poster(raw_base_name)
            if new_poster:
                supabase.table("tv_series").update({"poster_url": new_poster}).eq("id", series_id).execute()
    else:
        # جلب البوستر الحقيقي من TMDb عند الإنشاء لأول مرة
        poster_url = get_tmdb_poster(raw_base_name)
        
        new_series_data = {
            "title": unique_season_title,
            "category_type": "مسلسلات اجنبي"
        }
        if poster_url:
            new_series_data["poster_url"] = poster_url

        new_series = supabase.table("tv_series").insert(new_series_data).execute()
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
    
    try:
        check_ep = supabase.table("episodes_cima").select("id").eq("series_id", series_id).eq("season_number", s_num).eq("episode_number", e_num).execute()
        
        if check_ep.data:
            ep_id = check_ep.data[0]["id"]
            supabase.table("episodes_cima").update(episode_data).eq("id", ep_id).execute()
            print(f"    🔄 تم تحديث الحلقة بنجاح.")
        else:
            supabase.table("episodes_cima").insert(episode_data).execute()
            print(f"    ✅ تم حفظ الحلقة بنجاح.")
    except Exception as e:
        print(f"    ⚠️ خطأ في الحفظ: {e}")

def scrape_akwam_site():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page_num = 1
        visited_links = set() # ذاكرة مؤقتة لمنع تكرار معالجة نفس الرابط داخل السشن
        
        while True:
            url = f"https://akwams.org/category/مسلسلات-اجنبي/page/{page_num}/"
            page.goto(url)
            
            links = page.evaluate("""() => Array.from(document.querySelectorAll('a[href]')).map(a => a.href)
                                     .filter(h => h.includes('akwams.org') && !h.includes('/category/') && !h.includes('/page/') && h.split('/').length > 4)""")
            
            unique_links = [l for l in list(set(links)) if l not in visited_links]
            if not unique_links: 
                # إذا انتهت الصفحات أو لم تعود توجد روابط جديدة
                break
            
            for link in unique_links:
                visited_links.add(link)
                process_series_item(page, link)
            
            page_num += 1
        browser.close()

if __name__ == "__main__":
    scrape_akwam_site()
