import asyncio
import os
import random
from playwright.async_api import async_playwright
from supabase import create_client, Client

# إعدادات Supabase (ضع بيانات مشروعك هنا)
SUPABASE_URL = "https://xfblvqckjdstixqdtpdt.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhmYmx2cWNramRzdGl4cWR0cGR0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODUzMzY5NTIsImV4cCI6MjEwMDkxMjk1Mn0.TJ9Vz5FFPFNc7EbsUzF3U4TzKYgQez-SlKHnGRUmCuo"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

FILES = {
    "films": "films",
    "tv": "tv_series",
    "episodes": "episodes",
    "anime": "anime_items"
}

# دالة لمحاكاة حركة بشرية عشوائية (تأخير زمني)
async def human_delay(min_sec=1.5, max_sec=3.5):
    delay = random.uniform(min_sec, max_sec)
    await asyncio.sleep(delay)

# دالة لتحريك الماوس بطريقة عشوائية داخل الصفحة
async def human_mouse_move(page):
    try:
        width = random.randint(300, 800)
        height = random.randint(200, 600)
        await page.mouse.move(width, height, steps=random.randint(5, 15))
    except:
        pass

# التحقق من وجود العنصر مسبقاً في Supabase لمنع التكرار
def check_if_exists_in_supabase(cat_name, page_url):
    try:
        response = supabase.table(cat_name).select("page_url").eq("page_url", page_url).execute()
        if response.data and len(response.data) > 0:
            return True
    except Exception as e:
        print(f"[-] Supabase check error: {e}")
    return False

# حفظ البيانات مباشرة في Supabase مع تنظيف الروابط
def save_media_to_supabase(cat_name, data):
    if not data or not data.get("title") or data.get("title") == "Unknown":
        return
    
    # فلترة الروابط المباشرة للاحتفاظ بالملفات المفيدة فقط وتجاهل الإعلانات والتتبع
    cleaned_links = []
    for link in data.get("direct_links", []):
        if any(ext in link for ext in [".mp4", ".m3u8", "streamruby", "downet", "video", "stream", "server", "embed"]):
            if not any(ad in link for ad in ["youtube", "doubleclick", "analytics", "dtscout", "googlesyndication", "2e903a817d"]):
                if link not in cleaned_links:
                    cleaned_links.append(link)

    payload = {
        "title": data["title"],
        "page_url": data["page_url"],
        "watch_url": data["watch_url"],
        "poster_url": data["poster_url"],
        "category_type": data["category_type"],
        "duration": data["duration"],
        "year": data["year"],
        "quality": data["quality"],
        "language": data["language"],
        "country": data["country"],
        "add_date": data["add_date"],
        "description": data["description"],
        "direct_links": cleaned_links
    }

    try:
        supabase.table(cat_name).upsert(payload, on_conflict="page_url").execute()
        print(f"[☁️ SUPABASE - {cat_name.upper()}] Saved/Updated: {payload['title']} (Clean Links: {len(cleaned_links)})")
    except Exception as e:
        print(f"[-] Supabase save error: {e}")

async def extract_full_media_details(page, media_url):
    data = {
        "title": "Unknown",
        "page_url": media_url,
        "watch_url": media_url.rstrip("/") + "/watch/",
        "poster_url": "",
        "category_type": "",
        "duration": "",
        "year": "",
        "quality": "",
        "language": "",
        "country": "",
        "add_date": "",
        "description": "",
        "direct_links": []
    }
    
    media_links = set()
    
    def handle_request(request):
        url = request.url
        if any(ext in url for ext in [".mp4", ".m3u8", "downet", "video", "stream", "server", "streamruby"]) and "ionicons" not in url and "analytics" not in url:
            media_links.add(url)

    page.on("request", handle_request)
    
    try:
        # الانتقال لصفحة الفيلم بسلوك بشري
        await page.goto(media_url, timeout=45000, wait_until="domcontentloaded")
        await human_delay(2, 4)
        await human_mouse_move(page)
        
        # محاكاة التمرير لأسفل الصفحة مثل البشر لقراءة المحتوى وتحميل العناصر
        await page.evaluate("window.scrollBy(0, window.innerHeight / 2)")
        await human_delay(1, 2)

        try:
            title_el = await page.locator("h1").first.inner_text()
            if title_el:
                data["title"] = title_el.replace("\n", " ").strip()
        except:
            pass

        try:
            poster_el = page.locator(".Thumb img, .poster img, .details-img img, .single-poster img, div[class*='poster'] img, .story img, .Image img").first
            if await poster_el.count() > 0:
                p_url = await poster_el.get_attribute("src") or await poster_el.get_attribute("data-src") or ""
                if p_url:
                    data["poster_url"] = p_url if p_url.startswith("http") else f"https://m.arsd.bid{p_url}"
        except:
            pass

        items_text = await page.locator("li, div[class*='info'], div[class*='details']").all()
        for el in items_text:
            txt = await el.inner_text()
            if "سنة العرض" in txt:
                data["year"] = txt.replace("سنة العرض", "").replace(":", "").strip()
            elif "مدة العرض" in txt:
                data["duration"] = txt.replace("مدة العرض", "").replace(":", "").strip()
            elif "جودة العرض" in txt:
                data["quality"] = txt.replace("جودة العرض", "").replace(":", "").strip()
            elif "تصنيف العرض" in txt:
                data["category_type"] = txt.replace("تصنيف العرض", "").replace(":", "").strip()
            elif "لغة العرض" in txt:
                data["language"] = txt.replace("لغة العرض", "").replace(":", "").strip()
            elif "بلد العرض" in txt:
                data["country"] = txt.replace("بلد العرض", "").replace(":", "").strip()
            elif "تاريخ الاضافة" in txt:
                data["add_date"] = txt.replace("تاريخ الاضافة", "").replace(":", "").strip()

        try:
            desc_el = await page.locator("div[class*='story'], div[class*='desc'], p[class*='desc']").first.inner_text()
            if desc_el:
                data["description"] = desc_el.strip()
        except:
            pass

        # الانتقال لصفحة المشاهدة
        await page.goto(data["watch_url"], timeout=30000, wait_until="domcontentloaded")
        await human_delay(2, 3)
        await human_mouse_move(page)
        
        try:
            play_selectors = ["video", ".plaasplay", "div[class*='play']", "button[class*='server']", ".servers-list li", ".watch-servers a"]
            for selector in play_selectors:
                btn = page.locator(selector).first
                if await btn.count() > 0:
                    # محاكاة الضغط البشري على زر التشغيل
                    await btn.hover()
                    await human_delay(0.5, 1)
                    await btn.click(timeout=1500)
                    await human_delay(2, 3)
                    break
        except:
            pass
            
        if len(media_links) == 0:
            try:
                iframes = await page.locator("iframe").all()
                for iframe in iframes:
                    src = await iframe.get_attribute("src")
                    if src:
                        media_links.add(src)
            except:
                pass

        data["direct_links"] = list(media_links)
        
    except Exception as e:
        print(f"[-] Error parsing {media_url}: {e}")
    
    try:
        page.remove_listener("request", handle_request)
    except:
        pass
        
    return data

async def main():
    async with async_playwright() as p:
        # إعداد المتصفح بإخفاء بصمات البوت (Stealth Mode)
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled"
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15",
            viewport={"width": 1280, "height": 800},
            locale="ar-EG",
            timezone_id="Africa/Cairo"
        )
        page = await context.new_page()

        sections = {
            "films": "https://m.arsd.bid/category/films/",
            "tv": "https://m.arsd.bid/category/tv/",
            "anime": "https://m.arsd.bid/category/anime/"
        }

        for cat_name, cat_url in sections.items():
            print(f"\n==================== Starting Agent Scrape: {cat_name} ====================")
            page_num = 1
            consecutive_empty = 0
            
            while True:
                target_url = f"{cat_url}page/{page_num}/" if page_num > 1 else cat_url
                print(f"\n[*] Crawling [{cat_name.upper()}] - Page {page_num}: {target_url}")
                
                try:
                    response = await page.goto(target_url, timeout=60000, wait_until="domcontentloaded")
                    if response and response.status == 404:
                        print(f"[-] Reached 404 at page {page_num}.")
                        break
                        
                    await human_delay(2, 4)
                    await human_mouse_move(page)
                    
                    links = await page.locator(".GridItem a, .movies-list a, div[class*='Grid'] a, div[class*='item'] a").all()
                    if len(links) == 0:
                        links = await page.locator("a[href*='m.arsd.bid']").all()

                    if len(links) == 0:
                        consecutive_empty += 1
                        if consecutive_empty >= 3:
                            break
                        page_num += 1
                        continue
                    else:
                        consecutive_empty = 0
                        
                    page_urls = []
                    for item in links:
                        href = await item.get_attribute("href")
                        if href:
                            full_url = href if href.startswith("http") else f"https://m.arsd.bid{href}"
                            
                            if "/category/" in full_url or "/tag/" in full_url or "/watch" in full_url:
                                continue
                                
                            if cat_name == "films" and "mslsl" in full_url:
                                continue

                            page_urls.append(full_url)
                                
                    page_urls = list(dict.fromkeys(page_urls))
                    print(f"[+] Found {len(page_urls)} items on page {page_num}")
                    
                    if len(page_urls) == 0 and page_num > 3:
                        break

                    for index, url in enumerate(page_urls, start=1):
                        target_cat = cat_name
                        if cat_name == "tv" and ("/episode/" in url):
                            target_cat = "episodes"

                        if check_if_exists_in_supabase(target_cat, url):
                            print(f"[⏭️ Skipped] Already exists in Supabase: {url}")
                            continue

                        print(f"[*] Agent scraping {cat_name} [Page {page_num}] ({index}/{len(page_urls)}): {url}")
                        details = await extract_full_media_details(page, url)
                        
                        if details and details["title"] != "Unknown":
                            save_media_to_supabase(target_cat, details)
                        else:
                            print(f"[-] Skipped saving due to missing title: {url}")

                        # استراحة عشوائية بين كل فيلم والثاني لعدم لفت انتباه حماية الموقع
                        await human_delay(3, 6)

                except Exception as e:
                    print(f"[-] Error on page {page_num}: {e}")
                    break
                    
                page_num += 1

            print(f"[+] Successfully finished category {cat_name}.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
