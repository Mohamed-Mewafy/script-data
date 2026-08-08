import os
import re
import time
from playwright.sync_api import sync_playwright
from supabase import create_client, Client

# إعدادات الاتصال
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("⚠️ تأكد من ضبط متغيرات البيئة SUPABASE_URL و SUPABASE_KEY.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def clean_text(text):
    return " ".join(re.sub(r'[\"\'\[\]\{\}]', '', text).split()).strip()

def get_poster_from_page(page):
    """استخراج رابط البوستر مباشرة من صفحة أكوام"""
    try:
        return page.evaluate("""() => {
            const img = document.querySelector('img[src*="wp-content/uploads/"][src$=".jpg"], img[src*="wp-content/uploads/"][src$=".png"]');
            return img ? img.src : null;
        }""")
    except:
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
    return f"{clean_text(clean_name)} - الموسم {season_num}", season_num, clean_text(clean_name)

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
                if frame and "akwams" not in frame: extracted.append(frame)
    except: pass
    return list(set(extracted))

def process_series_item(page, item_page_url):
    try:
        page.goto(item_page_url, wait_until="domcontentloaded", timeout=10000)
        title = clean_text(page.title())
    except: return

    invalid_keywords = ["page not found", "404", "افلام", "أفلام", "انمي", "ات انمي", "رمضان", "تصنيف"]
    if not title or any(kw in title.lower() for kw in invalid_keywords): return

    unique_season_title, s_num, raw_base_name = normalize_series_title(title)
    e_num = extract_episode_number(title)

    # 1. التحقق من وجود المسلسل والبوستر ولينكات الحلقات مسبقاً
    existing_series = supabase.table("tv_series").select("id, poster_url").eq("title", unique_season_title).execute()
    
    has_poster = False
    series_id = None

    if existing_series.data:
        series_id = existing_series.data[0]["id"]
        has_poster = bool(existing_series.data[0].get("poster_url"))
        
        # التحقق من حالة الحلقة وهل لينكات التشغيل أكتر من 1
        check_ep = supabase.table("episodes_cima").select("direct_links").eq("series_id", series_id).eq("season_number", s_num).eq("episode_number", e_num).execute()
        if check_ep.data:
            links = check_ep.data[0].get("direct_links", {}).get("streaming_links", [])
            # التخطي يحدث فقط إذا كانت اللينكات > 1 AND البوستر موجود بالفعل
            if len(links) > 1 and has_poster:
                print(f"⏩ تخطي (مكتملة ولهو بوستر): {unique_season_title} | حلقة {e_num}")
                return

    # استخراج البوستر من الصفحة إذا لم يكن موجوداً
    poster_url = get_poster_from_page(page)

    if existing_series.data:
        # إذا كان المسلسل موجود ولكن البوستر ناقص، نقوم بتحديثه
        if not has_poster and poster_url:
            supabase.table("tv_series").update({"poster_url": poster_url}).eq("id", series_id).execute()
            print(    🖼️ تم تحديث البوستر الناقص للمسلسل: {unique_season_title}")
    else:
        # إنشاء مسلسل جديد بالبوستر
        new_series = supabase.table("tv_series").insert({
            "title": unique_season_title, 
            "category_type": "مسلسلات اجنبي", 
            "poster_url": poster_url
        }).execute()
        series_id = new_series.data[0]["id"]

    print(f"    📺 جاري المعالجة: {unique_season_title} | حلقة {e_num}")
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
            supabase.table("episodes_cima").update(episode_data).eq("id", check_ep.data[0]["id"]).execute()
        else:
            supabase.table("episodes_cima").insert(episode_data).execute()
        print(f"    ✅ تم حفظ/تحديث الحلقة بنجاح.")
    except Exception as e:
        print(f"    ⚠️ خطأ: {e}")

def scrape_akwam_site():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page_num = 1
        visited_links = set()
        
        while True:
            url = f"https://akwams.org/category/مسلسلات-اجنبي/page/{page_num}/"
            page.goto(url)
            links = page.evaluate("() => Array.from(document.querySelectorAll('a[href]')).map(a => a.href).filter(h => h.includes('akwams.org') && !h.includes('/category/') && !h.includes('/page/') && h.split('/').length > 4)")
            unique_links = [l for l in list(set(links)) if l not in visited_links]
            if not unique_links: break
            
            for link in unique_links:
                visited_links.add(link)
                process_series_item(page, link)
            page_num += 1
        browser.close()

if __name__ == "__main__":
    scrape_akwam_site()
