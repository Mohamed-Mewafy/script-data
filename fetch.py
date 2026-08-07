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

    # 1. البحث عن صيغة S01E01 الشهيرة
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

    # 2. استخراج رقم الموسم
    season_match = re.search(r'(?:الموسم|Season)\s*(?:الـ|ال)?\s*(\d+)', text, re.IGNORECASE)
    if season_match:
        season_num = int(season_match.group(1))
    else:
        season_word_match = re.search(r'(?:الموسم|Season)\s*([أ-ي]+)', text, re.IGNORECASE)
        if season_word_match and season_word_match.group(1) in arabic_numbers:
            season_num = arabic_numbers[season_word_match.group(1)]

    # 3. استخراج رقم الحلقة
    episode_match = re.search(r'(?:الحلقة|Episode)\s*(?:الـ|ال)?\s*(\d+)', text, re.IGNORECASE)
    if episode_match:
        episode_num = int(episode_match.group(1))
    else:
        ep_word_match = re.search(r'(?:الحلقة|Episode)\s*([أ-ي]+)', text, re.IGNORECASE)
        if ep_word_match and ep_word_match.group(1) in arabic_numbers:
            episode_num = arabic_numbers[ep_word_match.group(1)]

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
                poster_path = res.get("poster_path")
                if poster_path:
                    return f"https://image.tmdb.org/t/p/w500{poster_path}"
    except Exception:
        pass
    return "غير متوفر"

def fetch_download_links_only(page, item_page_url):
    raw_download_links = []
    download_page_url = f"{item_page_url.rstrip('/')}/download"

    try:
        page.goto(download_page_url, wait_until="domcontentloaded", timeout=15000)
        time.sleep(2)
        
        links = page.evaluate("""() => {
            const anchors = Array.from(document.querySelectorAll('a[href]'));
            return anchors.map(a => a.href).filter(h => {
                if (!h) return false;
                if (h === window.location.href || h.endsWith('/download') || h.endsWith('/download/')) return false;
                return h.includes('download') || h.includes('link') || h.includes('file') || h.includes('server') || !h.includes('akwams.org');
            });
        }""")
        
        for link in links:
            if link and link not in raw_download_links and not link.startswith("chrome-error://"):
                raw_download_links.append(link)
    except Exception:
        pass

    return list(set([shorten_link_via_shrinkme(l) for l in raw_download_links]))

def fetch_streaming_links_with_clicking(page, item_page_url):
    watch_page_url = f"{item_page_url.rstrip('/')}/watch/"
    extracted_streaming_links = []
    
    try:
        page.goto(watch_page_url, wait_until="domcontentloaded", timeout=15000)
        time.sleep(3)
        
        server_buttons = page.locator('button:has-text("سيرفر"), a:has-text("سيرفر")').all()
        if not server_buttons:
            server_buttons = page.locator('button').all()

        for btn in server_buttons:
            try:
                if btn.is_visible():
                    btn.click(timeout=2000)
                    time.sleep(1)
                    frame_url = page.evaluate("() => document.querySelector('iframe')?.src")
                    if frame_url and frame_url not in extracted_streaming_links and "akwams" not in frame_url and "about:blank" not in frame_url:
                        extracted_streaming_links.append(frame_url)
            except Exception:
                pass
            
            for frame in page.frames:
                f_url = frame.url
                if f_url and "akwams.org" not in f_url and "about:blank" not in f_url:
                    if f_url not in extracted_streaming_links:
                        extracted_streaming_links.append(f_url)
    except Exception:
        pass
        
    return list(set(extracted_streaming_links))

def process_series_item(page, item_page_url):
    try:
        page.goto(item_page_url, wait_until="domcontentloaded", timeout=15000)
    except Exception:
        return
    
    title = ""
    try:
        page_title = page.title()
        if page_title:
            title = clean_title(page_title)
    except Exception:
        pass

    if not title or "Page Not Found" in title or "404" in title or len(title) < 2:
        return

    series_name = extract_series_name_from_title(title)
    season_number, episode_number = extract_season_and_episode(title)
    
    if not series_name or len(series_name) < 2 or series_name.lower() in ["s1e1", "الحلقة"]:
        return

    # 1. حفظ أو جلب المسلسل الأساسي
    series_id = None
    existing_series = supabase.table("tv_series").select("id").ilike("title", f"%{series_name}%").execute()
    
    if existing_series.data:
        series_id = existing_series.data[0]["id"]
    else:
        poster = get_tmdb_poster(series_name)
        res = supabase.table("tv_series").insert({
            "title": series_name,
            "poster_url": poster,
            "category_type": "مسلسلات اجنبي"
        }).execute()
        if res.data:
            series_id = res.data[0]["id"]

    if not series_id:
        return

    # 2. فحص هل الحلقة موجودة مسبقاً بنفس المسلسل ورقم الموسم ورقم الحلقة لمنع التكرار تماماً
    existing_episode = supabase.table("episodes_cima").select("id").eq("series_id", series_id).eq("season_number", season_number).eq("episode_number", episode_number).execute()

    if existing_episode.data:
        print(f"    ⏭️ تخطي (الحلقة موجودة مسبقاً): {series_name} | S{season_number}E{episode_number}")
        return

    print(f"    📺 معالجة وحفظ حلقة جديدة: {series_name} | موسم {season_number} - حلقة {episode_number}")
    
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
        print(f"    ✅ تم حفظ الحلقة بنجاح.")
    except Exception as e:
        print(f"    ❌ خطأ أثناء حفظ الحلقة: {e}")

def scrape_akwam_site():
    print("🚀 بدء سكربت المسلسلات المحدث (بدون تكرار)...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        context.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,css}", lambda route: route.abort())
        page = context.new_page()
        
        base_category_url = "https://akwams.org/category/مسلسلات-اجنبي"
        page_number = 1
        
        while True:
            current_page_url = f"{base_category_url}/page/{page_number}/" if page_number > 1 else base_category_url
            print(f"\n📂 فحص الصفحة رقم [{page_number}]...")
            
            try:
                response = page.goto(current_page_url, wait_until="domcontentloaded", timeout=30000)
                if response and response.status == 404:
                    print("🏁 وصلنا لناية الصفحات.")
                    break

                time.sleep(2)
                
                item_links = page.evaluate("""() => {
                    const anchors = Array.from(document.querySelectorAll('a[href]'));
                    const links = anchors.map(a => a.href).filter(h => {
                        if (!h || !h.includes('akwams.org')) return false;
                        if (h.includes('/category/') || h.includes('/page/') || h.includes('/tag/') || h.includes('/search/')) return false;
                        const parts = h.split('/').filter(Boolean);
                        return parts.length >= 3;
                    });
                    return [...new Set(links)];
                }""")
                
                if not item_links:
                    break
                
                print(f"🔗 عُثر على {len(item_links)} رابط في هذه الصفحة...")
                for index, link in enumerate(item_links, 1):
                    print(f"\n  -- عنصر ({index}/{len(item_links)})")
                    process_series_item(page, link)
                
                page_number += 1
            except Exception as e:
                print(f"⚠️ خطأ: {e}")
                break

        browser.close()
        print("\n🎉 تم الانتهاء بنجاح!")

if __name__ == "__main__":
    scrape_akwam_site()
