import asyncio
import os
from playwright.async_api import async_playwright
from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

TABLES = {
    "films": "movies",
    "tv": "tv_series",
    "episodes": "episodes",
    "anime": "anime_items"
}

def check_if_exists_in_supabase(cat_name, page_url):
    table_name = TABLES.get(cat_name, "movies")
    try:
        response = supabase.table(table_name).select("page_url").eq("page_url", page_url).execute()
        if response.data and len(response.data) > 0:
            return True
    except Exception as e:
        print(f"[-] Error checking Supabase for {page_url}: {e}")
    return False

def save_media_to_supabase(cat_name, data):
    if not data or not data.get("title") or data.get("title") == "Unknown":
        print(f"[-] Skipped saving due to invalid title: {data.get('title')}")
        return
    
    table_name = TABLES.get(cat_name, "movies")
    
    if check_if_exists_in_supabase(cat_name, data["page_url"]):
        print(f"[⏭️ Skipped] Already exists in Supabase: {data['page_url']}")
        return

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

    try:
        res = supabase.table(table_name).insert(payload).execute()
        print(f"[☁️ Supabase - {table_name.upper()}] Inserted successfully: {payload['title']} (Links: {len(payload['direct_links'])})")
    except Exception as e:
        print(f"[-] Error inserting into Supabase ({table_name}): {e} | Payload: {payload['title']}")

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
    
    try:
        print(f"   [->] Loading media page: {media_url}")
        await page.goto(media_url, timeout=45000, wait_until="domcontentloaded")
        await asyncio.sleep(2)
        
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

        print(f"   [->] Loading watch page: {data['watch_url']}")
        await page.goto(data["watch_url"], timeout=30000, wait_until="domcontentloaded")
        await asyncio.sleep(2)
        
        try:
            play_selectors = ["video", ".plaasplay", "div[class*='play']", "button[class*='server']", ".servers-list li", ".watch-servers a", "ul.servers li"]
            for selector in play_selectors:
                btns = await page.locator(selector).all()
                for btn in btns:
                    if await btn.is_visible():
                        await btn.click(timeout=1000)
                        await asyncio.sleep(0.5)
        except:
            pass

        elements_with_links = await page.locator("a, source, iframe, video").all()
        for el in elements_with_links:
            for attr in ["href", "src", "data-src", "data-url"]:
                val = await el.get_attribute(attr)
                if val and any(ext in val for ext in [".mp4", ".m3u8", "downet", "video", "stream", "server"]):
                    if "ionicons" not in val and "analytics" not in val:
                        full_link = val if val.startswith("http") else f"https://m.arsd.bid{val}"
                        media_links.add(full_link)

        data["direct_links"] = list(media_links)
        print(f"   [+] Extracted title: '{data['title']}' with {len(data['direct_links'])} links.")
        
    except Exception as e:
        print(f"[-] Error parsing {media_url}: {e}")
        
    return data

async def main():
    print("[*] Launching browser...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ]
        )
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15",
            viewport={"width": 1440, "height": 900},
            locale="ar-EG",
            timezone_id="Africa/Cairo",
            extra_http_headers={
                "Accept-Language": "ar-EG,ar;q=0.9,en-US;q=0.8,en;q=0.7",
                "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"macOS"'
            }
        )
        
        page = await context.new_page()

        sections = {
            "films": "https://m.arsd.bid/category/films/",
            "tv": "https://m.arsd.bid/category/tv/",
            "anime": "https://m.arsd.bid/category/anime/"
        }

        for cat_name, cat_url in sections.items():
            print(f"\n==================== Starting Supabase Scrape: {cat_name} ====================")
            page_num = 1
            consecutive_empty = 0
            
            while True:
                target_url = f"{cat_url}page/{page_num}/" if page_num > 1 else cat_url
                print(f"\n[*] Crawling [{cat_name.upper()}] - Page {page_num}: {target_url}")
                
                try:
                    response = await page.goto(target_url, timeout=60000, wait_until="domcontentloaded")
                    if response:
                        print(f"[*] Response status: {response.status}")
                        if response.status == 404:
                            print(f"[-] Reached 404 at page {page_num}.")
                            break
                        
                    await asyncio.sleep(2)
                    
                    # محاولة البحث عن الروابط بأكثر من طريقة لضمان التقاطها
                    links = await page.locator(".GridItem a, .movies-list a, div[class*='Grid'] a, div[class*='item'] a, .PostItem a").all()
                    if len(links) == 0:
                        links = await page.locator("a[href*='m.arsd.bid']").all()

                    print(f"[*] Found raw elements count: {len(links)}")

                    if len(links) == 0:
                        consecutive_empty += 1
                        if consecutive_empty >= 3:
                            print("[-] Too many empty pages, breaking loop.")
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
                            
                            if "/category/" in full_url or "/tag/" in full_url or "/watch" in full_url or "page/" in full_url:
                                continue
                                
                            if cat_name == "films" and "mslsl" in full_url:
                                continue

                            page_urls.append(full_url)
                                
                    page_urls = list(dict.fromkeys(page_urls))
                    print(f"[+] Filtered unique media URLs count: {len(page_urls)}")
                    
                    if len(page_urls) == 0 and page_num > 3:
                        break

                    for index, url in enumerate(page_urls, start=1):
                        target_cat = cat_name
                        if cat_name == "tv" and "/episode/" in url:
                            target_cat = "episodes"
                            
                        if check_if_exists_in_supabase(target_cat, url):
                            print(f"[⏭️ Skipped] Already exists in Supabase: {url}")
                            continue

                        print(f"[*] Scraping item ({index}/{len(page_urls)}): {url}")
                        details = await extract_full_media_details(page, url)
                        
                        if cat_name == "tv" and "حلقة" in details.get("title", ""):
                            target_cat = "episodes"

                        if details and details["title"] != "Unknown":
                            save_media_to_supabase(target_cat, details)
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
