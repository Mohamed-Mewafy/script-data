import asyncio
import os
from playwright.async_api import async_playwright
from supabase import create_client, Client

# بيانات الاتصال بـ Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL", "ضع_رابط_سوبابيز_هنا")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "ضع_مفتاح_سوبابيز_هنا")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def check_if_exists(cat_name, page_url):
    try:
        table_name = "movies" if cat_name == "films" else ("anime_items" if cat_name == "anime" else "tv_series")
        res = supabase.table(table_name).select("id").eq("page_url", page_url).execute()
        if res.data and len(res.data) > 0:
            return True
    except Exception as e:
        print(f"[-] Check existence error: {e}")
    return False

def save_media_to_supabase(cat_name, data):
    if not data or not data.get("title") or data.get("title") == "Unknown":
        return
    try:
        # إزالة التقييم من البيانات قبل الرفع
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
            "direct_links": data["direct_links"]
        }

        if cat_name == "films":
            supabase.table("movies").upsert(payload, on_conflict="page_url").execute()
            print(f"[☁️ Supabase - Movies] Saved: {payload['title']} (Links: {len(payload['direct_links'])})")
        elif cat_name == "anime":
            supabase.table("anime_items").upsert(payload, on_conflict="page_url").execute()
            print(f"[☁️ Supabase - Anime] Saved: {payload['title']} (Links: {len(payload['direct_links'])})")
        elif cat_name == "tv":
            supabase.table("tv_series").upsert(payload, on_conflict="page_url").execute()
            print(f"[☁️ Supabase - TV Series] Saved: {payload['title']} (Links: {len(payload['direct_links'])})")
    except Exception as e:
        print(f"[-] Supabase Error ({cat_name}): {e}")

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
    
    # مراقبة الشبكة لالتقاط أي روابط فيديو أو سيرفرات تشغيل
    def handle_request(request):
        url = request.url
        if any(ext in url for ext in [".mp4", ".m3u8", "downet", "video", "stream", "server"]) and "ionicons" not in url and "analytics" not in url:
            media_links.add(url)

    page.on("request", handle_request)
    
    try:
        # 1. زيارة صفحة التفاصيل الأساسية لجلب المعلومات النصية
        await page.goto(media_url, timeout=45000)
        await asyncio.sleep(1)
        
        try:
            title_el = await page.locator("h1").first.inner_text()
            if title_el:
                data["title"] = title_el.replace("\n", " ").strip()
        except:
            pass

        try:
            poster_el = page.locator("img[class*='poster'], .poster img, .details-img img").first
            if await poster_el.count() > 0:
                data["poster_url"] = await poster_el.get_attribute("src") or await poster_el.get_attribute("data-src") or ""
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

        # 2. الانتقال لصفحة المشاهدة واستخراج روابط السيرفرات
        await page.goto(data["watch_url"], timeout=30000)
        await asyncio.sleep(2)
        
        try:
            play_selectors = ["video", ".plaasplay", "div[class*='play']", "button[class*='server']", ".servers-list li", ".watch-servers a"]
            for selector in play_selectors:
                btn = page.locator(selector).first
                if await btn.count() > 0:
                    await btn.click(timeout=1500)
                    await asyncio.sleep(1)
        except:
            pass
            
        await asyncio.sleep(2)
        
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
        
    return data

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
        )
        page = await context.new_page()

        sections = {
            "films": "https://m.arsd.bid/category/films/",
            "tv": "https://m.arsd.bid/category/tv/",
            "anime": "https://m.arsd.bid/category/anime/"
        }

        for cat_name, cat_url in sections.items():
            print(f"\n==================== Starting Clean Scrape: {cat_name} ====================")
            page_num = 1
            consecutive_empty = 0
            
            while True:
                target_url = f"{cat_url}page/{page_num}/" if page_num > 1 else cat_url
                print(f"\n[*] Crawling [{cat_name.upper()}] - Page {page_num}: {target_url}")
                
                try:
                    response = await page.goto(target_url, timeout=60000)
                    if response and response.status == 404:
                        print(f"[-] Reached 404 at page {page_num}.")
                        break
                        
                    await asyncio.sleep(2)
                    
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
                        if check_if_exists(cat_name, url):
                            print(f"[⏭️ Skipped] Already exists in Supabase: {url}")
                            continue

                        print(f"[*] Scraping {cat_name} [Page {page_num}] ({index}/{len(page_urls)}): {url}")
                        details = await extract_full_media_details(page, url)
                        
                        if details and details["title"] != "Unknown":
                            save_media_to_supabase(cat_name, details)
                        else:
                            print(f"[-] Skipped saving due to missing title: {url}")

                except Exception as e:
                    print(f"[-] Error on page {page_num}: {e}")
                    break
                    
                page_num += 1

            print(f"[+] Successfully finished category {cat_name}.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
