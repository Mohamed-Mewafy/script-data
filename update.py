import os
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import requests
from supabase import create_client, Client

# --- بيانات اتصال سوبابيز ---
SUPABASE_URL = "https://xfblvqckjdstixqdtpdt.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhmYmx2cWNramRzdGl4cWR0cGR0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODUzMzY5NTIsImV4cCI6MjEwMDkxMjk1Mn0.TJ9Vz5FFPFNc7EbsUzF3U4TzKYgQez-SlKHnGRUmCuo"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "ar-EG,ar;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "max-age=0",
    "Referer": "https://w1.movizland.watch/",
    "Sec-Ch-UA": '"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"',
    "Sec-Ch-UA-Mobile": "?1",
    "Sec-Ch-UA-Platform": '"Android"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36",
}

COOKIES = {
    "_ga": "GA1.1.1075885453.1785509757",
    "_ga_T32S8XQYBY": "GS2.1.s1785509756$o1$g1$t1785510278$j9$l0$h0",
}

BASE_URL = "https://w1.movizland.watch/"


def clean_title(raw_title: str) -> str:
    title = re.sub(
        r"مشاهدة|مسلسل|فيلم|مترجم|موفيز لاند|ماي سيما|وي سيما|mycima|wecima|\([0-9]{4}\)",
        "",
        raw_title,
        flags=re.IGNORECASE,
    )
    title = re.sub(r"[-|–—:]+", " ", title)
    title = re.sub(r"\s+", " ", title).strip()
    return re.sub(r"\s+ة$", "", title).strip()


def get_all_categories(session: requests.Session) -> dict:
    print("[*] جاري استخراج التصنيفات من الشريط العلوي للموقع...")
    categories = {}
    try:
        res = session.get(BASE_URL, headers=HEADERS, cookies=COOKIES, timeout=15)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = str(a.get("href", ""))
                name = a.get_text(strip=True)
                if "/category/" in href and name:
                    full_url = urljoin(BASE_URL, href)
                    categories[name] = full_url
    except Exception as e:
        print(f"[-] خطأ أثناء جلب التصنيفات: {e}")
    return categories


def item_exists(table_name: str, watch_url: str) -> bool:
    try:
        res = (
            supabase.table(table_name).select("id").eq("watch_url", watch_url).execute()
        )
        if res.data and len(res.data) > 0:
            return True
    except Exception:
        pass
    return False


def process_item(
    session: requests.Session, item_url: str, category_name: str, thumb_url: str
):
    try:
        res = session.get(item_url, headers=HEADERS, cookies=COOKIES, timeout=15)
        if res.status_code != 200:
            return

        soup = BeautifulSoup(res.text, "html.parser")

        title_tag = soup.find("h1") or soup.find("title")
        if not title_tag:
            return
        raw_title = title_tag.get_text(strip=True)
        clean_name = clean_title(raw_title)

        poster_url = thumb_url
        if poster_url.startswith("//"):
            poster_url = "https:" + poster_url

        year = None
        year_match = re.search(r"\b(19\d{2}|20\d{2})\b", raw_title)
        if not year_match:
            year_match = re.search(r"\b(19\d{2}|20\d{2})\b", res.text)
        if year_match:
            year = int(year_match.group(1))

        description = ""
        desc_tag = soup.select_one(
            ".StoryLine, .story, .entry-content, .post-story, .description"
        )
        if desc_tag:
            description = desc_tag.get_text(strip=True)

        direct_links = []
        for iframe in soup.find_all("iframe"):
            src = iframe.get("src") or iframe.get("data-src")
            if src:
                src_str = str(src)
                if (
                    "embed" in src_str
                    or src_str.endswith(".html")
                    or "cybervynx" in src_str
                ) and "facebook" not in src_str:
                    if src_str not in direct_links:
                        direct_links.append(src_str)

        if not direct_links:
            return

        primary_watch_url = direct_links[0]
        is_series = (
            "مسلسل" in category_name or "أنمي" in category_name or "الحلقة" in raw_title
        )
        is_anime = "أنمي" in category_name or "انمي" in category_name

        if is_series:
            target_table = "anime_items" if is_anime else "tv_series"
            series_id = None

            # البحث عن المسلسل بالاسم والتصنيف لمنع التكرار
            existing_series = (
                supabase.table(target_table)
                .select("id")
                .eq("title", clean_name)
                .execute()
            )

            if existing_series.data and len(existing_series.data) > 0:
                first_row = existing_series.data[0]
                if isinstance(first_row, dict) and "id" in first_row:
                    series_id = first_row["id"]
            else:
                series_payload = {
                    "title": clean_name,
                    "poster_url": poster_url,
                    "category_type": category_name,
                    "year": year,
                    "description": description,
                }
                insert_res = (
                    supabase.table(target_table).insert(series_payload).execute()
                )
                if insert_res.data and len(insert_res.data) > 0:
                    inserted_row = insert_res.data[0]
                    if isinstance(inserted_row, dict) and "id" in inserted_row:
                        series_id = inserted_row["id"]
                    print(f"[+] تمت إضافة المسلسل [{category_name}]: {clean_name}")

            if series_id:
                if not item_exists("episodes", primary_watch_url):
                    season_num = 1
                    ep_num = 1
                    s_match = re.search(r"الموسم\s+(\d+)", raw_title)
                    e_match = re.search(r"الحلقة\s+(\d+)", raw_title)
                    if s_match:
                        season_num = int(s_match.group(1))
                    if e_match:
                        ep_num = int(e_match.group(1))

                    episode_payload = {
                        "series_id": series_id,
                        "title": clean_name,
                        "watch_url": primary_watch_url,
                        "season_number": season_num,
                        "episode_number": ep_num,
                        "direct_links": direct_links,
                    }
                    supabase.table("episodes").insert(episode_payload).execute()
                    print(f"   [->] تمت إضافة الحلقة: {clean_name}")

        else:
            target_table = "anime_items" if is_anime else "movies"
            if not item_exists(target_table, primary_watch_url):
                movie_payload = {
                    "title": clean_name,
                    "watch_url": primary_watch_url,
                    "poster_url": poster_url,
                    "category_type": category_name,
                    "year": year,
                    "description": description,
                    "direct_links": direct_links,
                }
                supabase.table(target_table).insert(movie_payload).execute()
                print(f"[+] تمت إضافة الفيلم [{category_name}]: {clean_name}")

    except Exception as e:
        print(f"[-] خطأ أثناء معالجة العنصر: {e}")


def crawl_site():
    session = requests.Session()
    categories = get_all_categories(session)

    for cat_name, cat_url in categories.items():
        print(f"\n==========================================")
        print(f"[*] البدء في سحب قسم: {cat_name}")
        print(f"==========================================")

        page = 1
        while True:
            target_url = f"{cat_url}page/{page}/" if page > 1 else cat_url
            print(f"--- {cat_name} | الصفحة {page} ---")

            try:
                res = session.get(
                    target_url, headers=HEADERS, cookies=COOKIES, timeout=15
                )
                if res.status_code != 200:
                    break

                soup = BeautifulSoup(res.text, "html.parser")
                items_map = {}

                for box in soup.select(".video-grid, .BlockItem, .item"):
                    a_tag = box.find("a", href=True)
                    if a_tag:
                        href = a_tag.get("href")
                        if href and "/video/" in href:
                            full_url = urljoin(BASE_URL, str(href))
                            img_tag = box.find("img")
                            img_src = ""
                            if img_tag:
                                raw_src = (
                                    img_tag.get("data-src")
                                    or img_tag.get("data-lazy-src")
                                    or img_tag.get("src")
                                )
                                if raw_src:
                                    img_src = str(raw_src)
                            items_map[full_url] = img_src

                if not items_map:
                    break

                for link, thumb in items_map.items():
                    process_item(session, link, cat_name, thumb)

                page += 1
            except Exception as e:
                print(f"[-] خطأ في الصفحة {page}: {e}")
                break


if __name__ == "__main__":
    crawl_site()
