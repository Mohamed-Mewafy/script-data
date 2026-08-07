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

BLOCKED_DOMAINS = [
    "1xlite", "1xbet", "suphelper", "spendsdetachment", 
    "kettledrooping", "googlesyndication", "adsterra", 
    "propellerads", "traffic", "click", "registration",
    "t.me", "actor", "page", "ad-policy", "dmca", "traincdn",
    "akwams.org", "akwam"
]

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

def is_valid_link(link):
    if not link:
        return False
    link_lower = link.lower()
    if "akwams.org" in link_lower or "akwam" in link_lower:
        return False
    for blocked in BLOCKED_DOMAINS:
        if blocked in link_lower:
            return False
    return True

def shorten_link_via_shrinkme(original_url):
    if not original_url or not is_valid_link(original_url):
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

def extract_category_from_url_or_page(cat_url, page_genres, title):
    url_lower = cat_url.lower()
    if "اجنبي" in url_lower:
        return "افلام اجنبي" if "movies" in url_lower or "افلام" in url_lower else "مسلسلات اجنبي"
    elif "عربي" in url_lower:
        return "افلام عربي"
    elif "هندية" in url_lower:
        return "افلام هندية"
    elif "اسيوية" in url_lower:
        return "افلام اسيوية"
    elif "انمي" in url_lower:
        return "افلام انمي" if "movies" in url_lower else "مسلسلات انمي"
    elif "تركية" in url_lower:
        return "مسلسلات تركية"
    elif "series" in url_lower:
        return "مسلسلات"
    for g in page_genres:
        clean_g = clean_text(g)
        if "افلام" in clean_g or "مسلسلات" in clean_g:
            return clean_g
    if "مسلسل" in title or "الحلقة" in title:
        return "مسلسلات"
    return "افلام عامة"

def fetch_download_links_only(page, item_page_url, max_retries=2):
    raw_download_links = []
    clean_base_url = item_page_url.rstrip('/')
    if "/series/" in clean_base_url and not any(x in clean_base_url for x in ["episode", "الحلقة", "movie"]):
        return []

    if clean_base_url.endswith('/watch'):
        download_page_url = clean_base_url.replace('/watch', '/download')
    elif clean_base_url.endswith('/download'):
        download_page_url = clean_base_url
    else:
        download_page_url = f"{clean_base_url}/download"

    for attempt in range(max_retries):
        try:
            page.goto(download_page_url, wait_until="domcontentloaded", timeout=20000)
            links = page.evaluate("""() => {
                const downloadElements = Array.from(document.querySelectorAll('a[href*="download"], a[href*="/link/"], a[href*="niramirus"], a[href*="file"], a.link-download, a.btn-download, a.download-link, .download-link a, .buttons-list a, a.btn, a[class*="download"]'));
                return downloadElements.map(el => el.href).filter(Boolean);
            }""")
            for link in links:
                if is_valid_link(link) and link != download_page_url and link not in raw_download_links:
                    raw_download_links.append(link)
            if raw_download_links:
                break
        except Exception:
            time.sleep(1)

    shortened_download_links = []
    for raw_link in raw_download_links:
        short_link = shorten_link_via_shrinkme(raw_link)
        if is_valid_link(short_link):
            shortened_download_links.append(short_link)
    return shortened_download_links

def scrape_akwam_item_details(page, item_page_url):
    try:
        page.goto(item_page_url, wait_until="domcontentloaded", timeout=15000)
    except Exception as e:
        print(f"❌ خطأ في فتح صفحة العنصر {item_page_url}: {e}")
        return None

    title = ""
    try:
        page_title = page.title()
        if page_title:
            title = clean_title(page_title)
    except Exception:
        pass

    if not title or len(title) < 3:
        return None

    is_series = "الحلقة" in title or "الموسم" in title or "/series/" in item_page_url
    category_type = "series" if is_series else "movie"

    year = None
    match = re.search(r'20\d{2}|19\d{2}', title)
    if match:
        try:
            year = int(match.group(0))
        except Exception:
            pass

    poster = "غير متوفر"
    try:
        poster = page.evaluate("""() => {
            let metaImg = document.querySelector('meta[property="og:image"]') || document.querySelector('meta[name="twitter:image"]');
            if (metaImg && metaImg.content && metaImg.content.startsWith('http')) return metaImg.content;
            const el = document.querySelector('.entry-image img, .poster img, .movie-poster img, .details-img img, .img-fluid');
            return el ? (el.src || el.getAttribute('data-src')) : "غير متوفر";
        }""")
    except Exception:
        pass

    description = "غير متوفر"
    try:
        desc_text = page.evaluate("""() => {
            const el = document.querySelector('.widget-body .text-white, .story, div[class*="story"], article p');
            return el ? el.innerText.trim() : "غير متوفر";
        }""")
        if desc_text and len(desc_text) > 10:
            description = desc_text
    except Exception:
        pass

    rating = "غير متوفر"
    try:
        rating_text = page.evaluate("""() => {
            const el = document.querySelector('span.mx-2, .rating span');
            return el ? el.innerText.trim() : "غير متوفر";
        }""")
        if rating_text:
            rating = rating_text
    except Exception:
        pass

    genres = []
    try:
        genres = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('.genres a, .cats a, a[href*="category"]')).map(t => t.innerText.trim()).filter(Boolean);
        }""")
    except Exception:
        pass

    clean_base_url = item_page_url.rstrip('/')
    watch_page_url = clean_base_url if clean_base_url.endswith('/watch') else f"{clean_base_url}/watch/"
    extracted_streaming_links = []
    try:
        page.goto(watch_page_url, wait_until="domcontentloaded", timeout=12000)
        frames = page.frames
        for frame in frames:
            f_url = frame.url
            if f_url and is_valid_link(f_url):
                extracted_streaming_links.append(f_url)
    except Exception:
        pass

    final_watch_url = extracted_streaming_links[0] if extracted_streaming_links else None
    extracted_download_links = fetch_download_links_only(page, item_page_url) if category_type == "movie" else []

    direct_links_json = {
        "streaming_links": list(set(extracted_streaming_links)),
        "download_links": list(set(extracted_download_links))
    }

    return {
        "title": title,
        "year": year,
        "category_type": category_type,
        "poster_url": poster,
        "description": description,
        "rating": rating,
        "genres": list(set(genres)),
        "watch_url": final_watch_url,
        "direct_links": direct_links_json
    }, category_type

def save_or_update_download_links(page, item_data, category_type, current_cat_url, item_page_url):
    title = item_data.get("title", "")
    if not title or len(title) < 3:
        return

    if category_type == "movie":
        existing_movie = supabase.table("movies_cima").select("id, direct_links").eq("title", title).execute()
        
        if existing_movie.data:
            row = existing_movie.data[0]
            movie_id = row.get("id")
            direct_links = row.get("direct_links") or {}
            
            if isinstance(direct_links, dict):
                download_links = direct_links.get("download_links", [])
                
                if not download_links:
                    print(f"🔄 الفيلم [{title}] موجود وروابط التحميل فارغة. جاري الجلب والتحديث...")
                    new_download_links = fetch_download_links_only(page, item_page_url)
                    
                    if new_download_links:
                        direct_links["download_links"] = list(set(new_download_links))
                        supabase.table("movies_cima").update({"direct_links": direct_links}).eq("id", movie_id).execute()
                        print(f"✅ تم تحديث وإضافة ({len(new_download_links)}) رابط تحميل للفيلم: {title}")
                    else:
                        print(f"⚠️ لم يتم العثور على روابط تحميل جديدة للفيلم: {title}")
                else:
                    print(f"⏭️ الفيلم [{title}] يحتوي على روابط تحميل بالفعل.")
            return

        raw_genres = item_data.get("genres", [])
        clean_category = extract_category_from_url_or_page(current_cat_url, raw_genres, title)
        poster_url = item_data.get("poster_url", "غير متوفر")
        if poster_url == "غير متوفر":
            poster_url = get_tmdb_poster(title)

        formatted_movie = {
            "title": title,
            "category_type": clean_category,
            "year": int(item_data["year"]) if item_data.get("year") else None,
            "poster_url": poster_url,
            "description": item_data.get("description", "غير متوفر"),
            "rating": item_data.get("rating", "غير متوفر"),
            "genres": [clean_text(g) for g in raw_genres if clean_text(g)],
            "watch_url": item_data.get("watch_url"),
            "direct_links": item_data.get("direct_links", {"streaming_links": [], "download_links": []})
        }
        supabase.table("movies_cima").upsert(formatted_movie, on_conflict="title").execute()
        print(f"✅ [تم حفظ فيلم جديد]: {title}")

def scrape_akwam_site():
    print("🚀 بدء السكربت الشامل لسحب أقسام الأفلام صفحة بصفحة...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        context.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,css}", lambda route: route.abort())
        page = context.new_page()
        
        base_category_url = "https://akwams.org/category/movies"
        page_number = 1
        
        while True:
            # تحديد رابط الصفحة الحالية بدقة
            if page_number == 1:
                current_page_url = f"{base_category_url}/"
            else:
                current_page_url = f"{base_category_url}/page/{page_number}/"
                
            print(f"\n📂 جاري فحص الصفحة رقم [{page_number}] | الرابط: {current_page_url}")
            
            try:
                page.goto(current_page_url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(2)
                
                # جلب الروابط برمجياً بالطريقة المضمونة
                item_cards = page.evaluate("""() => {
                    return Array.from(document.querySelectorAll('a')).map(a => a.href).filter(h => {
                        if (!h || !h.includes('akwams.org')) return false;
                        if (h.includes('/category/') || h.includes('/page/') || h.includes('/tag/') || h.includes('/search/') || h.includes('/user/')) return false;
                        if (h === 'https://akwams.org/' || h === 'https://akwams.org') return false;
                        return h.split('/').length >= 4;
                    });
                }""")
                
                item_links = list(set(item_cards))
                
                # إذا لم يتم العثور على أي عناصر في الصفحة الحالية، فهذا يعني أننا وصلنا لنهاية الصفحات
                if not item_links:
                    print(f"🏁 لا توجد عناصر أخرى في الصفحة رقم [{page_number}]. تم الانتهاء من سحب القسم بالكامل بنجاح!")
                    break
                
                print(f"🔗 عُثر على {len(item_links)} عنصر في هذه الصفحة. جاري معالجة وسحب البيانات...")
                
                for index, link in enumerate(item_links, 1):
                    if not is_valid_link(link):
                        continue
                    
                    print(f"  ⏳ معالجة العنصر ({index}/{len(item_links)})... الرابط: {link}")
                    result = scrape_akwam_item_details(page, link)
                    if result:
                        item_data, cat_type = result
                        if item_data and item_data.get("title"):
                            save_or_update_download_links(page, item_data, cat_type, current_page_url, link)
                
                # الانتقال للصفحة التالية فقط بعد التأكد من انتهاء الحالية بالكامل
                page_number += 1
                
            except Exception as e:
                print(f"⚠️ حدث خطأ أو انتهت الصفحات عند الصفحة [{page_number}]: {e}")
                break

        browser.close()
        print("\n🎉 تم الانتهاء من كافة العمليات وحفظ البيانات في قاعدة البيانات بنجاح!")

if __name__ == "__main__":
    scrape_akwam_site()
