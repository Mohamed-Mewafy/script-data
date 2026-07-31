import asyncio
import base64
import os
import re
from urllib.parse import parse_qs, urlparse, urlunparse
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from supabase import create_client, Client

# --- إعدادات Supabase الخاصة بك ---
SUPABASE_URL = "https://xfblvqckjdstixqdtpdt.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhmYmx2cWNramRzdGl4cWR0cGR0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODUzMzY5NTIsImV4cCI6MjEwMDkxMjk1Mn0.TJ9Vz5FFPFNc7EbsUzF3U4TzKYgQez-SlKHnGRUmCuo"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def clean_url_string(raw_link: str) -> str:
    try:
        parsed = urlparse(raw_link)
        clean_path = urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))
        return clean_path if clean_path else raw_link
    except:
        return raw_link


def decode_mycima_link(link: str) -> str:
    try:
        parsed_url = urlparse(link)
        query_params = parse_qs(parsed_url.query)
        for key in ["mycimafsd", "link", "url", "data", "vfxcimavd"]:
            if key in query_params:
                encoded_val = query_params[key][0]
                padded = encoded_val + "=" * (-len(encoded_val) % 4)
                decoded_bytes = base64.b64decode(padded).decode("utf-8")
                return clean_url_string(decoded_bytes)
    except:
        pass
    return clean_url_string(link)


def clean_title(raw_title: str) -> str:
    title = re.sub(
        r"مشاهدة|مسلسل|فيلم|مترجم|ماي سيما|وي سيما|mycima|wecima|\([0-9]{4}\)",
        "",
        raw_title,
        flags=re.IGNORECASE,
    )
    title = re.sub(r"[-|–—:]+", " ", title)
    return re.sub(r"\s+", " ", title).strip()


def movie_already_exists(title: str) -> bool:
    try:
        response = supabase.table("movies").select("title").eq("title", title).execute()
        return len(response.data) > 0
    except Exception as e:
        print(f"[-] خطأ أثناء التحقق من وجود الفيلم: {e}")
        return False


def save_movie_to_supabase(data):
    if not data["title"] or "ماي سيما" in data["title"] or len(data["direct_links"]) == 0:
        return

    if movie_already_exists(data["title"]):
        print(f"[*] تخطي (موجود مسبقاً في Supabase): {data['title']}")
        return

    try:
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
            "direct_links": data["direct_links"]  # تُحفظ كمصفوفة نصية صافية ['url1', 'url2']
        }

        supabase.table("movies").insert(payload).execute()
        print(f"[+] تم حفظ الفيلم بنجاح في Supabase: {data['title']}")
    except Exception as e:
        print(f"[-] خطأ أثناء الحفظ في Supabase للعمل {data['title']}: {e}")


async def scrape_single_item(page, url):
    print(f"[*] جاري فحص الرابط التفصيلي: {url}")
    try:
        await page.goto(url, timeout=60000, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        html_content = await page.content()
        soup = BeautifulSoup(html_content, "html.parser")

        title_tag = soup.find("h1") or soup.find("title")
        raw_title = title_tag.get_text(strip=True) if title_tag else ""
        print(f"[*] العنوان المستخرج: {raw_title}")
        
        if not raw_title or "ماي سيما" in raw_title and len(raw_title) > 60:
            return

        clean_name = clean_title(raw_title)
        lower_raw = raw_title.lower()

        if "حلقة" in lower_raw or "الحلقة" in lower_raw or "مسلسل" in lower_raw or "موسم" in lower_raw or "series" in url or "episodes" in url:
            print(f"[*] تخطي (ليس فيلماً): {clean_name}")
            return

        if movie_already_exists(clean_name):
            print(f"[*] تخطي السحب لفيلم مسجل مسبقاً: {clean_name}")
            return

        quality, country, duration, language = "", "", "", ""

        for li in soup.find_all(['li', 'div', 'p', 'span']):
            text = li.get_text(" ", strip=True)
            if "الجودة" in text and not quality:
                parts = text.split(":")
                if len(parts) > 1: quality = parts[1].strip()
            if "الدولة" in text and not country:
                parts = text.split(":")
                if len(parts) > 1: country = parts[1].strip()
            if "اللغة" in text and not language:
                parts = text.split(":")
                if len(parts) > 1: language = parts[1].strip()
            if "المدة" in text and not duration:
                parts = text.split(":")
                if len(parts) > 1: duration = parts[1].strip()

        description = ""
        desc_container = soup.find(string=lambda t: t and "قصة العرض" in t)
        if desc_container:
            parent = desc_container.find_parent()
            if parent:
                next_elem = parent.find_next_sibling() or parent.find_next("p")
                if next_elem:
                    description = next_elem.get_text(strip=True)
        
        if not description:
            story_div = soup.select_one(".Story, .story, div.StoryText, div.story-content")
            if story_div:
                description = story_div.get_text(strip=True)

        description = re.sub(r"قصة العرض", "", description).strip()

        poster_url = ""
        try:
            poster_url = await page.evaluate("""() => {
                const badKeywords = ['favicon', 'icon', 'logo', 'avatar', 'placeholder', 'spinner', 'default', 'ads', 'banner', 'hamada'];
                const imgs = document.querySelectorAll('img');
                for (let img of imgs) {
                    let src = img.src || img.getAttribute('data-src') || img.getAttribute('data-lazy-src');
                    if (src) {
                        let lower = src.toLowerCase();
                        if (lower.includes('/wp-content/uploads/') && !badKeywords.some(b => lower.includes(b))) {
                            return src;
                        }
                    }
                }
                return "";
            }""")
        except:
            poster_url = ""

        year = ""
        year_tag = soup.find("a", href=lambda h: h and "year" in h)
        if year_tag:
            year = year_tag.get_text(strip=True)

        server_elements = await page.locator(
            ".ServersList-ItemList li, ul.load-servers li, .WatchServersList li"
        ).all()
        direct_links_extracted = []

        for el in server_elements:
            try:
                data_watch = await el.get_attribute("data-watch")
                if data_watch:
                    final_link = decode_mycima_link(data_watch)
                    if final_link and final_link not in direct_links_extracted:
                        direct_links_extracted.append(final_link)
            except:
                continue

        item_data = {
            "title": clean_name,
            "page_url": clean_url_string(url),
            "watch_url": direct_links_extracted[0] if direct_links_extracted else "",
            "poster_url": poster_url,
            "category_type": "أفلام",
            "duration": duration,
            "year": year,
            "quality": quality,
            "language": language,
            "country": country,
            "add_date": "",
            "description": description,
            "direct_links": direct_links_extracted,
        }

        save_movie_to_supabase(item_data)

    except Exception as e:
        print(f"[-] خطأ في scrape_single_item للرابط {url}: {e}")


async def crawl_movies_section(sections_urls, max_pages_per_section: int = 1):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        for section_url in sections_urls:
            for page_num in range(1, max_pages_per_section + 1):
                current_page_url = (
                    f"{section_url}page/{page_num}/" if page_num > 1 else section_url
                )
                print(f"\n--- جاري فحص قسم الأفلام: {current_page_url} ---")

                try:
                    await page.goto(
                        current_page_url, timeout=60000, wait_until="domcontentloaded"
                    )
                    await page.wait_for_timeout(3000)

                    item_links = await page.evaluate(
                        """
                        () => {
                            const anchors = document.querySelectorAll('a.term-block, div.Thumb--Grid a, div.GridItem a, div.movies-oppers a, .EpisodesList a, .MovieList a, div.BlockItem a');
                            let links = [];
                            if (anchors.length > 0) {
                                anchors.forEach(a => { if (a.href) links.push(a.href); });
                            } else {
                                document.querySelectorAll('a').forEach(a => {
                                    let href = a.href;
                                    if (href && (href.includes('/movie/') || href.includes('/watch/'))) {
                                        links.push(href);
                                    }
                                });
                            }
                            return Array.from(new Set(links));
                        }
                        """
                    )

                    print(f"[*] عدد الروابط المستخرجة من الصفحة: {len(item_links)}")

                    for item_url in item_links:
                        await scrape_single_item(page, item_url)
                        await asyncio.sleep(0.3)

                except Exception as e:
                    print(f"[-] خطأ أثناء تصفح القسم {current_page_url}: {e}")
                    break

        await browser.close()
    print("\n[+] تم الانتهاء من عملية الفحص والتنفيذ!")


if __name__ == "__main__":
    target_sections = [
        "https://mycima.gripe/movies/",
    ]
    max_pages = 10000
    asyncio.run(crawl_movies_section(target_sections, max_pages))
