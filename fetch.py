import asyncio
import os
from playwright.async_api import async_playwright
from supabase import create_client, Client

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

async def extract_media_details(page, media_url):
    # تم إزالة حقل watch_url نهائياً من هنا
    data = {
        "title": "Unknown",
        "page_url": media_url,
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
        ignored_domains = [
            "asdplay.cam", "255md.com", "cloudflareinsights", "googlesyndication", 
            "analytics", "facebook", "twitter", "ads", "ionicons", "googlevideo"
        ]
        if any(domain in url for domain in ignored_domains):
            return
            
        if any(ext in url for ext in [".mp4", ".m3u8", "downet.net", "get-link", "file/"]):
            media_links.add(url)

    page.on("request", handle_request)
    
    try:
        await page.goto(media_url, timeout=45000)
        await asyncio.sleep(2)
        
        try:
            title_el = await page.locator("h1").first.inner_text()
            if title_el:
                data["title"] = title_el.replace("\n", " ").strip()
        except:
            pass

        try:
            og_image = page.locator("meta[property='og:image']")
            if await og_image.count() > 0:
                data["poster_url"] = await og_image.get_attribute("content") or ""
            
            if not data["poster_url"]:
                poster_el = page.locator(".details-img img, .poster img, img[class*='poster'], .media-thumb img, .thumbnail img, .fixed-img img").first
                if await poster_el.count() > 0:
                    data["poster_url"] = await poster_el.get_attribute("src") or await poster_el.get_attribute("data-src") or await poster_el.get_attribute("data-lazy-src") or ""
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

        # الانتقال لصفحة المشاهدة لاستخراج الرابط فقط بدون حفظ رابط الصفحة نفسها
        watch_url = media_url.rstrip("/") + "/watch/"
        await page.goto(watch_url, timeout=30000)
        
        try:
            await page.wait_for_selector("video, .play-btn, [class*='play'], iframe, .servers-list", timeout=7000)
            play_buttons = page.locator(".play-btn, div[class*='play'], .servers-list li, .watch-servers a, button[class*='server']")
            if await play_buttons.count() > 0:
                await play_buttons.first.click(timeout=2000)
        except:
            pass
            
        for _ in range(6):
            if len(media_links) > 0:
                break
            await asyncio.sleep(2)
            
        if len(media_links) == 0:
            try:
                sources = await page.locator("video, video source, a[href*='.mp4'], iframe").all()
                for src_el in sources:
                    src = await src_el.get_attribute("src") or await src_el.get_attribute("data-src") or await src_el.get_attribute("href")
                    if src and not any(d in src for d in ["asdplay.cam", "255md.com", "ads"]):
                        media_links.add(src)
            except:
                pass

        data["direct_links"] = list(media_links)
        
    except Exception as e:
        print(f"[-] Error parsing {media_url}: {e})")
        
    return data

def save_media(cat_name, data):
    try:
        if cat_name == "films":
            supabase.table("movies").upsert(data, on_conflict="page_url").execute()
            print(f"[☁️ Supabase - Movies] Saved: {data['title']}")
        elif cat_name == "anime":
            supabase.table("anime_items").upsert(data, on_conflict="page_url").execute()
            print(f"[☁️ Supabase - Anime] Saved: {data['title']}")
        elif cat_name == "tv":
            series_payload = {
                "title": data["title"],
                "page_url": data["page_url"],
                "poster_url": data["poster_url"],
                "category_type": data["category_type"],
                "year": data["year"],
                "language": data["language"],
                "country": data["country"],
                "add_date": data["add_date"],
                "description": data["description"]
            }
            supabase.table("tv_series").upsert(series_payload, on_conflict="page_url").execute()
            print(f"[☁️ Supabase - TV Series] Saved: {data['title']}")
    except Exception as e:
        print(f"[-] Supabase Error ({cat_name}): {e}")

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
            "anime": "https://m.arsd.bid/category/anime/",
            "tv": "https://m.arsd.bid/category/tv/"
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
                        break
                        
                    await asyncio.sleep(2)
                    
                    links = await page.locator("div[class*='GridItem'] a, div[class*='movies-list'] a, .PostItem a, article a").all()
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
                            if "/category/" in full_url or "/tag/" in full_url or "/watch" in full_url or "#" in full_url:
                                continue
                            if full_url not in page_urls:
                                page_urls.append(full_url)
                                
                    print(f"[+] Found {len(page_urls)} unique items on page {page_num}")
                    
                    if len(page_urls) == 0 and page_num > 3:
                        break

                    for index, url in enumerate(page_urls, start=1):
                        if check_if_exists(cat_name, url):
                            print(f"[⏭️ Skipped] Already exists in Supabase: {url}")
                            continue

                        print(f"[*] Scraping {cat_name} [Page {page_num}] ({index}/{len(page_urls)}): {url}")
                        details = await extract_media_details(page, url)
                        save_media(cat_name, details)

                except Exception as e:
                    print(f"[-] Error on page {page_num}: {e}")
                    break
                    
                page_num += 1

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
