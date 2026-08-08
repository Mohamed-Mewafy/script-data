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

def normalize_series_title(raw_title):
    name = re.sub(r'^(مشاهدة|تحميل)?\s*(مسلسل|انمي|برنامج|حصريا|جديد)?\s*', '', raw_title).strip()
    
    season_num = 1
    s_match = re.search(r'(?:الموسم|Season)\s*(?:الـ|ال)?\s*(\d+)', name, re.IGNORECASE)
    if s_match:
        season_num = int(s_match.group(1))
    else:
        arabic_numbers = {
            "الاول": 1, "الأول": 1, "الاولى": 1, "الأولى": 1,
            "الثاني": 2, "الثانية": 2,
            "الثالث": 3, "الثالثة": 3,
            "الرابع": 4, "الرابعة": 4,
            "الخامس": 5, "الخامسة": 5,
            "السادس": 6, "السابعة": 7, "الثامن": 8, "التاسع": 9, "العاشر": 10
        }
        for word, num in arabic_numbers.items():
            if word in name:
                season_num = num
                break

    clean_name = re.sub(r'\s*(الموسم|Season|الاول|الأول|الثاني|الثالث|الرابع|الخامس|الحلقة|\d+|-|\||مترجم|مدبلج|اكوام|Akwam).*', '', name, flags=re.IGNORECASE).strip()
    clean_name = clean_text(clean_name)
    
    invalid_names = ["جديد", "حصريا", "مسلسل", "انمي", "برنامج", "الحلقة"]
    if not clean_name or clean_name in invalid_names or len(clean_name) < 2:
        return None, None, None

    unified_title = f"{clean_name} - الموسم {season_num}"
    return unified_title, season_num, clean_name

def extract_episode_number(text):
    e_match = re.search(r'(?:الحلقة|Episode)\s*(?:الـ|ال)?\s*(\d+)', text, re.IGNORECASE)
    return int(e_match.group(1)) if e_match else 1

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
    clean_base_url = item_page_url.rstrip('/')
    
    target_urls = [f"{clean_base_url}/download", clean_base_url]

    for target in target_urls:
        try:
            res = page.goto(target, wait_until="domcontentloaded", timeout=12000)
            if res and res.status == 404 and target != clean_base_url:
                continue
                
            time.sleep(1.5)
            
            links = page.evaluate("""() => {
                const anchors = Array.from(document.querySelectorAll('a[href]'));
                return anchors.map(a => a.href).filter(h => {
                    if (!h || h.startsWith('javascript') || h.startsWith('chrome-error://')) return false;
                    if (h === window.location.href || h.endsWith('/download') || h.endsWith('/download/')) return false;
                    
                    return h.includes('/download/') || 
                           h.includes('link') || 
                           h.includes('file') || 
                           h.includes('niramirus') || 
                           h.includes('server') ||
                           h.includes('direct') ||
                           h.includes('get') ||
                           !h.includes('akwams.org');
                });
            }""")
            
            for link in links:
                if link and link not in raw_download_links:
                    raw_download_links.append(link)
                    
            if raw_download_links:
                break
        except Exception:
            pass

    return [shorten_link_via_shrinkme(l) for l in raw_download_links if l]

def fetch_streaming_links_with_clicking(page, item_page_url):
    watch_page_url = f"{item_page_url.rstrip('/')}/watch/"
    extracted_streaming_links = set()

    try:
        page.goto(watch_page_url, wait_until="domcontentloaded", timeout=15000)
        time.sleep(2)
        
        # 1. فحص الإطارات المباشرة
        iframes = page.locator('iframe').all()
        for iframe in iframes:
            try:
                src = iframe.get_attribute('src') or iframe.get_attribute('data-src')
                if src and "akwams" not in src and not src.startswith("about:blank"):
                    extracted_streaming_links.add(src)
            except Exception:
                pass

        # 2. الضغط على أزرار السيرفرات
        server_selectors = [
            'button:has-text("سيرفر")', 
            'a:has-text("سيرفر")', 
            '.servers-list button', 
            '.servers-list a',
            'ul.servers button',
            'div[class*="server"] button',
            'div[class*="server"] a'
        ]
        
        server_buttons = []
        for selector in server_selectors:
            btns = page.locator(selector).all()
            if btns:
                server_buttons.extend(btns)

        if not server_buttons:
            server_buttons = page.locator('button').all()

        for btn in server_buttons[:8]:
            try:
                if btn.is_visible():
                    btn.click(timeout=1500)
                    time.sleep(1)
                    
                    frame_url = page.evaluate("() => document.querySelector('iframe')?.src || document.querySelector('iframe')?.getAttribute('data-src')")
                    if frame_url and "akwams" not in frame_url and not frame_url.startswith("about:blank"):
                        extracted_streaming_links.add(frame_url)
            except Exception:
                pass

        # 3. جلب الـ Frames بالصفحة
        for frame in page.frames:
            f_url = frame.url
            if f_url and "akwams.org" not in f_url and "about:blank" not in f_url and not f_url.startswith("chrome-error://"):
                extracted_streaming_links.add(f_url)

    except Exception:
        pass
        
    return list(extracted_streaming_links)

def process_item(page, item_page_url, cat_type):
    if "مسلسلات" not in cat_type:
        return

    try:
        page.goto(item_page_url, wait_until="domcontentloaded", timeout=15000)
    except Exception:
        return

    title = ""
    try:
        page_title = page.title()
        if page_title:
            title = clean_text(page_title)
    except Exception:
        pass

    invalid_keywords = ["page not found", "404", "رمضان", "تصنيف", "الصفحة الرئيسية", "تسجيل الدخول"]
    if not title or any(kw in title.lower() for kw in invalid_keywords):
        return

    unique_season_title, s_num, raw_base_name = normalize_series_title(title)
    if not unique_season_title:
        return
        
    e_num = extract_episode_number(title)
    print(f"    📺 مسلسل: {unique_season_title} | حلقة {e_num}")

    poster = "غير متوفر"
    try:
        poster = page.evaluate("""() => {
            let metaImg = document.querySelector('meta[property="og:image"]');
            if (metaImg && metaImg.content) return metaImg.content;
            const el = document.querySelector('.entry-image img, .poster img, img');
            return el ? (el.src || el.getAttribute('data-src')) : "غير متوفر";
        }""")
    except Exception:
        pass

    if poster == "غير متوفر" or not poster.startswith("http"):
        poster = get_tmdb_poster(raw_base_name)

    description = "غير متوفر"
    try:
        desc_text = page.evaluate("() => document.querySelector('.story, .text-white, article p')?.innerText.trim()")
        if desc_text and len(desc_text) > 5:
            description = desc_text
    except Exception:
        pass

    rating = "غير متوفر"
    try:
        rating_text = page.evaluate("() => document.querySelector('span.mx-2, .rating span')?.innerText.trim()")
        if rating_text:
            rating = rating_text
    except Exception:
        pass

    genres = []
    try:
        genres = page.evaluate("() => Array.from(document.querySelectorAll('.genres a, .cats a, a[href*=\"category\"]')).map(t => t.innerText.trim()).filter(Boolean)")
    except Exception:
        pass

    formatted_series = {
        "title": unique_season_title,
        "category_type": cat_type,
        "poster_url": poster,
        "description": description,
        "rating": rating,
        "genres": [clean_text(g) for g in genres if clean_text(g)]
    }

    try:
        # حفظ أو تحديث بيانات المسلسل
        supabase.table("tv_series").upsert(formatted_series, on_conflict="title").execute()
        get_id = supabase.table("tv_series").select("id").eq("title", unique_season_title).execute()
        if not get_id.data:
            return
        series_id = get_id.data[0]["id"]
    except Exception:
        return

    # سحب الروابط الجديدة من الصفحة
    new_streaming_links = fetch_streaming_links_with_clicking(page, item_page_url)
    new_download_links = fetch_download_links_only(page, item_page_url)

    try:
        # 🔍 الاستعلام عن الحلقة هل هي موجودة مسبقاً أم لا؟
        existing_ep = supabase.table("episodes_cima") \
            .select("id, watch_url, direct_links") \
            .eq("series_id", series_id) \
            .eq("season_number", s_num) \
            .eq("episode_number", e_num) \
            .execute()

        final_streaming = new_streaming_links
        final_download = new_download_links
        existing_watch_url = None

        if existing_ep.data:
            ep_row = existing_ep.data[0]
            existing_watch_url = ep_row.get("watch_url")
            existing_direct_links = ep_row.get("direct_links") or {}

            old_streaming = existing_direct_links.get("streaming_links", []) or []
            old_download = existing_direct_links.get("download_links", []) or []

            # 🔄 دمج الروابط القديمة مع الجديدة وإزالة التكرار مع الحفاظ على الترتيب
            final_streaming = list(dict.fromkeys(old_streaming + new_streaming_links))
            final_download = list(dict.fromkeys(old_download + new_download_links))

        # تحديث watch_url برابط صالح
        watch_url_val = existing_watch_url if existing_watch_url else (final_streaming[0] if final_streaming else None)

        episode_data = {
            "series_id": series_id,
            "title": f"الحلقة {e_num}",
            "season_number": s_num,
            "episode_number": e_num,
            "watch_url": watch_url_val,
            "direct_links": {
                "streaming_links": final_streaming,
                "download_links": final_download
            }
        }

        # حفظ / تحديث الحلقة
        supabase.table("episodes_cima").upsert(episode_data, on_conflict="series_id,season_number,episode_number").execute()
        print(f"    ✅ تم تحديث/حفظ الحلقة بنجاح | (مشاهدة: {len(final_streaming)} | تحميل: {len(final_download)})")

    except Exception as e:
        print(f"    ❌ خطأ أثناء حفظ الحلقة: {e}")

def scrape_akwam_site():
    categories = [
        ("https://akwams.org/category/مسلسلات-اجنبي", "مسلسلات اجنبي"),
        ("https://akwams.org/category/مسلسلات-عربي", "مسلسلات عربي")
    ]

    print("🚀 بدء السكربت المخصص للمسلسلات مع التحديث الذكي للروابط...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36")
        context.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,css}", lambda route: route.abort())
        page = context.new_page()

        for base_url, cat_type in categories:
            print(f"\n📂 بدء سحب قسم: {cat_type}")
            page_number = 1
            while True:
                url = f"{base_url}/page/{page_number}/" if page_number > 1 else f"{base_url}/"
                print(f"  📄 صفحة [{page_number}]")
                
                try:
                    response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    if response and response.status == 404:
                        break

                    time.sleep(2)
                    item_links = page.evaluate("""() => {
                        return [...new Set(Array.from(document.querySelectorAll('a')).map(a => a.href).filter(h => {
                            if (!h || !h.includes('akwams.org') || h.includes('/category/') || h.includes('/page/') || h.includes('/tag/')) return false;
                            const parts = h.split('/').filter(Boolean);
                            return parts.length >= 3 && parts[parts.length - 1].length > 5;
                        }))];
                    }""")
                    
                    if not item_links:
                        break
                    
                    for link in item_links:
                        process_item(page, link, cat_type)
                    page_number += 1
                except Exception:
                    break

        browser.close()

if __name__ == "__main__":
    scrape_akwam_site()
