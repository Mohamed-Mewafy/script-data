import os
import re
from playwright.sync_api import sync_playwright
from supabase import create_client, Client

# سحب المفاتيح بأمان من بيئة النظام (GitHub Secrets)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("⚠️ تنبيه: يرجى التأكد من ضبط متغيرات البيئة SUPABASE_URL و SUPABASE_KEY بشكل صحيح.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

BLOCKED_DOMAINS = [
    "1xlite", "1xbet", "suphelper", "spendsdetachment", 
    "kettledrooping", "googlesyndication", "adsterra", 
    "propellerads", "traffic", "click", "registration",
    "t.me", "actor", "page", "ad-policy", "dmca", "traincdn"
]

STREAMING_DOMAINS = [
    "https://hgplaycdn.com/e/",
    "https://playnixes.com/e/",
    "https://cybervynx.com/e/",
    "https://playmogo.com/e/",
    "https://doodstream.com/e/",
    "https://streamwish.fun/e/",
    "https://miixdrop.com/e/"
]

def clean_text(text):
    if not text:
        return ""
    text = re.sub(r'[\"\'\[\]\{\}]', '', text)
    return " ".join(text.split()).strip()

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

def extract_series_and_episode_info(full_title):
    ep_num = 1
    ep_match = re.search(r'(?:الحلقة|ep|episode)\s*(\d+)', full_title, re.IGNORECASE)
    if ep_match:
        try:
            ep_num = int(ep_match.group(1))
        except:
            pass

    season_num = 1
    season_match = re.search(r'(?:الموسم|season|s)\s*(\d+)', full_title, re.IGNORECASE)
    if season_match:
        try:
            season_num = int(season_match.group(1))
        except:
            pass

    series_title = full_title
    series_title = re.sub(r'(?:الموسم|season|s)\s*\d+', '', series_title, flags=re.IGNORECASE)
    series_title = re.sub(r'(?:الحلقة|ep|episode)\s*\d+', '', series_title, flags=re.IGNORECASE)
    series_title = series_title.replace("مشاهدة", "").replace("مسلسل", "").replace("مترجم", "").replace("مدبلج", "").replace("اكوام", "").replace("Akwam", "")
    series_title = series_title.split("|")[0].split("-")[0]
    
    series_title = clean_text(series_title)
    words = series_title.split()
    if len(words) > 1 and len(words[-1]) == 1:
        words.pop()
        series_title = " ".join(words)

    return series_title if series_title else full_title, season_num, ep_num

def save_to_supabase(item_data, category_type, current_cat_url):
    title = item_data.get("title", "")
    
    unwanted_words = ["دخول", "تسجيل", "ات", "جديد", "الحلقات", "صفحة"]
    if not title or any(w == title for w in unwanted_words) or len(title) < 3:
        return

    try:
        raw_genres = item_data.get("genres", [])
        clean_category = extract_category_from_url_or_page(current_cat_url, raw_genres, title)
        cleaned_genres = [clean_text(g) for g in raw_genres if clean_text(g)]

        if category_type == "movie":
            table_name = "movies_cima"
            payload = {
                "title": title,
                "watch_url": item_data.get("watch_url"),
                "poster_url": item_data.get("poster_url", "غير متوفر"),
                "category_type": clean_category,
                "year": int(item_data["year"]) if item_data.get("year") else None,
                "description": item_data.get("description", "غير متوفر"),
                "rating": item_data.get("rating", "غير متوفر"),
                "genres": cleaned_genres,
                "external_id": item_data.get("external_id"),
                "direct_links": item_data.get("direct_links", {"streaming_links": [], "download_links": []})
            }
            
            existing = supabase.table(table_name).select("id").eq("title", title).execute()
            if existing.data and len(existing.data) > 0:
                print(f"ℹ️ [الفيلم موجود مسبقاً]: {title}")
                return

            supabase.table(table_name).insert(payload).execute()
            print(f"✅ [تم رفع الفيلم بنجاح تحت تصنيف ({clean_category})]: {title}")

        else:
            series_title, season_num, episode_num = extract_series_and_episode_info(title)
            
            series_existing = supabase.table("tv_series").select("id").eq("title", series_title).execute()
            
            if series_existing.data and len(series_existing.data) > 0:
                series_id = series_existing.data[0]["id"]
            else:
                series_payload = {
                    "title": series_title,
                    "poster_url": item_data.get("poster_url", "غير متوفر"),
                    "category_type": clean_category,
                    "year": int(item_data["year"]) if item_data.get("year") else None,
                    "description": item_data.get("description", "غير متوفر"),
                    "rating": item_data.get("rating", "غير متوفر"),
                    "genres": cleaned_genres,
                    "watch_url": item_data.get("watch_url")
                }
                res = supabase.table("tv_series").insert(series_payload).execute()
                if res.data and len(res.data) > 0:
                    series_id = res.data[0]["id"]
                else:
                    re_check = supabase.table("tv_series").select("id").eq("title", series_title).execute()
                    if re_check.data:
                        series_id = re_check.data[0]["id"]
                    else:
                        print(f"⚠️ فشل إنشاء المسلسل الأساسي: {series_title}")
                        return
                print(f"📁 [تم إنشاء مسلسل جديد وإضافته تحت تصنيف ({clean_category})]: {series_title}")

            episode_table = "episodes_cima"
            episode_payload = {
                "series_id": series_id,
                "title": title,
                "watch_url": item_data.get("watch_url"),
                "season_number": season_num,
                "episode_number": episode_num,
                "direct_links": item_data.get("direct_links", {"streaming_links": [], "download_links": []})
            }

            existing_ep = supabase.table(episode_table).select("id").eq("watch_url", item_data.get("watch_url")).execute()
            if existing_ep.data and len(existing_ep.data) > 0:
                print(f"ℹ️ [الحلقة موجودة مسبقاً]: {title}")
                return

            supabase.table(episode_table).insert(episode_payload).execute()
            print(f"✅ [تم رفع الحلقة بنجاح تحت المسلسل ({series_title})]: الحلقة {episode_num}")

    except Exception as e:
        print(f"⚠️ خطأ أثناء الرفع ({title}): {str(e)}")
        
def clean_title(raw_title):
    title = raw_title.replace("مشاهدة", "").replace("فيلم", "").replace("مسلسل", "")
    title = title.replace("مترجم", "").replace("مدبلج", "").replace("اكوام", "").replace("Akwam", "")
    title = title.split("|")[0].split("-")[0]
    return clean_text(title)

def is_valid_link(link):
    if not link:
        return False
    link_lower = link.lower()
    for blocked in BLOCKED_DOMAINS:
        if blocked in link_lower:
            return False
    return True

def extract_identifier(url):
    if not url or "registration" in url or "?" in url or "ad" in url:
        return None
        
    match = re.search(r'/e/([a-zA-Z0-9_-]+)', url)
    if match:
        identifier = match.group(1)
        if "registration" not in identifier and len(identifier) < 30:
            return identifier
            
    return None

def scrape_akwam_item_details(page, item_page_url):
    try:
        page.goto(item_page_url, wait_until="domcontentloaded", timeout=15000)
    except:
        return None

    title = ""
    try:
        page_title = page.title()
        if page_title:
            title = clean_title(page_title)
    except:
        pass

    if not title or title in ["ات", "جديد", "الحلقات", "دخول"] or "اكوام" in title or len(title) < 3 or "صفحة" in title:
        return None

    is_series = "الحلقة" in title or "الموسم" in title or "/series/" in item_page_url
    category_type = "series" if is_series else "movie"

    print(f"\n-> جاري معالجة ({'مسلسل' if is_series else 'فيلم'}): {title}")

    year = None
    match = re.search(r'20\d{2}|19\d{2}', title)
    if match:
        try:
            year = int(match.group(0))
        except:
            pass

    poster = "غير متوفر"
    try:
        poster = page.evaluate("""() => {
            const selectors = ['.entry-image img', '.poster img', '.movie-poster img', '.details-img img', '.img-fluid', 'meta[property="og:image"]'];
            for (let sel of selectors) {
                const el = document.querySelector(sel);
                if (el) {
                    const src = el.src || el.getAttribute('data-src') || el.content;
                    if (src && !src.includes('logo') && !src.includes('traincdn') && src.startsWith('http')) return src;
                }
            }
            return "غير متوفر";
        }""")
    except:
        pass

    description = "غير متوفر"
    try:
        desc_text = page.evaluate("""() => {
            const el = document.querySelector('.widget-body .text-white, .story, div[class*="story"], article p');
            return el ? el.innerText.trim() : "غير متوفر";
        }""")
        if desc_text and len(desc_text) > 10:
            description = desc_text
    except:
        pass

    rating = "غير متوفر"
    try:
        rating_text = page.evaluate("""() => {
            const el = document.querySelector('span.mx-2, .rating span, span:has(.icon-star)');
            return el ? el.innerText.trim() : "غير متوفر";
        }""")
        if rating_text and ("10" in rating_text or "/" in rating_text):
            rating = rating_text
    except:
        pass

    genres = []
    try:
        raw_genres = page.evaluate("""() => {
            const tags = document.querySelectorAll('.genres a, .cats a, a[href*="category"], .badge');
            return Array.from(tags).map(t => t.innerText.trim()).filter(Boolean);
        }""")
        genres = [g for g in raw_genres if "اعمار" not in g and g != "G"]
    except:
        pass

    clean_base_url = item_page_url.rstrip('/')
    watch_page_url = clean_base_url if clean_base_url.endswith('/watch') else f"{clean_base_url}/watch/"

    item_identifier = None
    extracted_streaming_links = []

    try:
        page.goto(watch_page_url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(1500)
        
        frames = page.frames
        for frame in frames:
            f_url = frame.url
            if f_url and "akwams.org" not in f_url and is_valid_link(f_url):
                extracted_streaming_links.append(f_url)
                identifier = extract_identifier(f_url)
                if identifier and not item_identifier:
                    item_identifier = identifier

        if not item_identifier or not extracted_streaming_links:
            iframes_data = page.evaluate("""() => {
                return Array.from(document.querySelectorAll('iframe, embed, object')).map(el => el.src || el.getAttribute('data-src')).filter(Boolean);
            }""")
            for link in iframes_data:
                if is_valid_link(link):
                    extracted_streaming_links.append(link)
                    identifier = extract_identifier(link)
                    if identifier and not item_identifier:
                        item_identifier = identifier
    except:
        pass

    if item_identifier and "registration" not in item_identifier:
        all_links = [f"{domain}{item_identifier}" for domain in STREAMING_DOMAINS]
        final_watch_url = all_links[0]
        direct_streaming_links = all_links[1:]
    else:
        final_watch_url = watch_page_url
        direct_streaming_links = list(set(extracted_streaming_links))

    direct_links_json = {
        "streaming_links": direct_streaming_links,
        "download_links": []
    }

    return {
        "title": title,
        "year": year,
        "category_type": category_type,
        "poster_url": poster,
        "description": description,
        "rating": rating,
        "genres": list(set(genres)),
        "external_id": item_identifier,
        "watch_url": final_watch_url,
        "direct_links": direct_links_json
    }, category_type

def scrape_akwam_site():
    print("🚀 بدء تشغيل سكريبت السحب مع تنظيف التصنيفات...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        context.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,css}", lambda route: route.abort())
        
        page = context.new_page()
        
        target_categories = [
            "https://akwams.org/movies",
            "https://akwams.org/series",
            "https://akwams.org/category/movies/افلام-اجنبي",
            "https://akwams.org/category/movies/افلام-عربي",
            "https://akwams.org/category/movies/افلام-هندية",
            "https://akwams.org/category/movies/افلام-اسيوية",
            "https://akwams.org/category/movies/افلام-انمي",
            "https://akwams.org/category/series/مسلسلات-اجنبي",
            "https://akwams.org/category/series/مسلسلات-تركية",
            "https://akwams.org/category/series/مسلسلات-انمي"
        ]

        for cat_url in target_categories:
            print(f"\n========================================")
            print(f"📁 الانتقال للقسم: {cat_url}")
            print(f"========================================")
            current_page_url = cat_url
            page_number = 1
            max_pages = 9999
            
            while current_page_url and page_number <= max_pages:
                try:
                    print(f"\n📄 جاري سحب الصفحة رقم ({page_number} من أصل {max_pages if max_pages != 9999 else '?' }): {current_page_url}")
                    page.goto(current_page_url, wait_until="domcontentloaded", timeout=25000)
                    page.wait_for_timeout(1000)
                    
                    if page_number == 1:
                        max_pages = page.evaluate("""() => {
                            let pageLinks = Array.from(document.querySelectorAll('.pagination a, .pages a, a.page-link'));
                            let numbers = pageLinks.map(el => parseInt(el.innerText.trim())).filter(n => !isNaN(n));
                            return numbers.length > 0 ? Math.max(...numbers) : 999;
                        }""")
                        print(f"📌 تم اكتشاف أن هذا القسم يحتوي على {max_pages} صفحة كحد أقصى.")

                    item_cards = page.evaluate("""() => {
                        return Array.from(document.querySelectorAll('a')).map(a => a.href).filter(h => {
                            if (!h || !h.includes('akwams.org')) return false;
                            if (h.includes('/category/') || h.includes('/page/') || h.includes('/tag/') || h.includes('/search/') || h.includes('/user/')) return false;
                            if (h === 'https://akwams.org/' || h === 'https://akwams.org') return false;
                            return h.split('/').length >= 4;
                        });
                    }""")
                    
                    item_links = list(set(item_cards))
                    print(f"🔗 تم العثور على {len(item_links)} عنصر في هذه الصفحة، جاري المعالجة...")
                    
                    for link in item_links:
                        if not is_valid_link(link):
                            continue
                        
                        result = scrape_akwam_item_details(page, link)
                        if result:
                            item_data, cat_type = result
                            if item_data and item_data.get("title"):
                                save_to_supabase(item_data, cat_type, cat_url)
                    
                    if page_number >= max_pages:
                        print(f"🏁 لقد وصلت إلى الصفحة الأخيرة ({max_pages}) من هذا القسم.")
                        break

                    page_number += 1
                    if "/page/" in current_page_url:
                        current_page_url = re.sub(r'/page/\d+', f'/page/{page_number}', current_page_url)
                    else:
                        base = current_page_url.rstrip('/')
                        current_page_url = f"{base}/page/{page_number}"
                        
                except Exception as e:
                    print(f"⚠️ حدث توقف مؤقت أو انتهت صفحات القسم: {e}")
                    break

        browser.close()
        print("\n🎉 تم الانتهاء من سحب وتصنيف جميع العناصر وتنظيفها بنجاح تام!")

if __name__ == "__main__":
    scrape_akwam_site()
