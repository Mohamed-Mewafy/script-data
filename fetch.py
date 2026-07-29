async def extract_media_details(page, media_url):
    data = {
        "title": "Unknown",
        "page_url": media_url,
        "watch_url": media_url.rstrip("/") + "/watch/",
        "poster_url": "",
        "rating": "",
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
    
    # فلتر صارم يلتقط الروابط التي تنتهي بامتدادات فيديو حقيقية فقط
    def handle_request(request):
        url = request.url
        # التركيز على الامتدادات المباشرة وتجنب الـ tokens المشفرة أو الـ iframes
        if any(ext in url for ext in [".mp4", ".m3u8", ".ts", "playlist.m3u8"]) \
           and not any(excl in url for excl in ["analytics", "googlesyndication", "facebook", "twitter", "ads", "asdplay.cam"]):
            media_links.add(url)

    page.on("request", handle_request)
    
    try:
        # 1. زيارة صفحة التفاصيل واستخراج المعلومات النصية والبستر
        await page.goto(media_url, timeout=45000)
        await asyncio.sleep(2)
        
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

        try:
            rating_el = await page.locator(".rating, [class*='rate'], span:has-text('10/')").first.inner_text()
            if rating_el:
                data["rating"] = rating_el.strip().split("\n")[0]
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

        # 2. الانتقال لصفحة المشاهدة
        await page.goto(data["watch_url"], timeout=30000)
        
        # محاكاة تفاعل بشري: الضغط على زر التشغيل أو واجهة المداعبة لإجبار السيرفر على جلب ملف الـ MP4
        try:
            # الانتظار حتى يظهر مشغل الفيديو أو أزرار السيرفرات
            await page.wait_for_selector("video, .play-btn, [class*='play'], iframe", timeout=7000)
            
            # محاولة النقر على أي زر تشغيل ظاهر لإيقاظ الـ Player
            play_buttons = page.locator("video, .play-btn, div[class*='play'], .servers-list li, .watch-servers a")
            if await play_buttons.count() > 0:
                await play_buttons.first.click(timeout=3000)
        except:
            pass

        # 3. الصبر الانتظاري: إعطاء فرصة كافية (8 إلى 10 ثواني) لظهور رابط الـ MP4 الفعلي في الـ Network
        for _ in range(5):
            if len(media_links) > 0:
                break # أول ما يلقط رابط فيديو مباشر، يخرج فوراً
            await asyncio.sleep(2)
            
        # 4. فحص إضافي لعناصر الـ HTML المباشرة (مثل tag الـ video أو source) لو لم يظهر عبر الشبكة
        if len(media_links) == 0:
            try:
                sources = await page.locator("video, video source").all()
                for src_el in sources:
                    src = await src_el.get_attribute("src") or await src_el.get_attribute("data-src")
                    if src and (".mp4" in src or ".m3u8" in src):
                        media_links.add(src)
            except:
                pass

        data["direct_links"] = list(media_links)
        
    except Exception as e:
        print(f"[-] Error parsing {media_url}: {e}")
        
    return data
