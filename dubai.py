import asyncio
import re
import pandas as pd
import os
import random
from playwright.async_api import async_playwright
from datetime import datetime

# ---------------------------------------------------------
# ⚙️ Settings - 8 PARALLEL SCRAPERS FOR DUBAI
# ---------------------------------------------------------
HISTORY_FILE = "search_history_dubai.txt"
FINAL_DATA_CHECKPOINT = "dubai_final.csv"
NUM_PARALLEL_SCRAPERS = 12  # Run 12 scrapers in parallel

# Timing settings
QUERIES_BEFORE_BREAK = 50
SHORT_BREAK_RANGE = (3, 8)
LONG_BREAK_RANGE = (30, 90)

# Your working proxies
PROXIES = [
    "35.172.109.143:80",
    "54.90.159.174:22229",
    "52.188.28.218:3128",
    "34.194.110.189:80",
    "3.216.111.113:80",
    "192.99.62.192:8888",
    "154.3.236.202:3128",
    "62.113.119.14:8080",
    "68.235.35.171:3128",
    "34.56.128.52:80",
    "192.145.31.160:4145",
    "178.130.47.129:1082",
    "78.12.223.246:2724",
    "176.126.103.194:44214",
    "190.242.157.215:8080",
    "208.67.28.27:58090",
    "62.133.62.12:1081",
    "115.114.77.133:9090",
    "212.34.144.253:80",
    "180.148.4.74:8080",
    "41.223.119.156:3128",
    "59.6.25.118:3128",
    "211.230.49.122:3128",
    "39.185.41.193:5911",
    "103.153.38.105:8083",
    "103.119.101.59:8080",
    "200.201.134.184:8787",
    "116.203.139.209:5678",
    "200.174.198.32:8888",
    "220.197.44.36:3128",
    "200.59.191.232:999",
    "164.163.42.26:10000",
    "111.79.111.126:3128"
]

# Major neighborhoods/districts in Dubai (broad coverage)
DUBAI_NEIGHBORHOODS = [
    "Downtown Dubai",
    "Dubai Marina",
    "Jumeirah Beach Residence (JBR)",
    "Palm Jumeirah",
    "Business Bay",
    "DIFC (Dubai International Financial Centre)",
    "Dubai Mall",
    "City Walk",
    "La Mer",
    "Jumeirah",
    "Umm Suqeim",
    "Al Barsha",
    "Dubai Sports City",
    "Dubai Silicon Oasis",
    "Dubai Media City",
    "Dubai Internet City",
    "Dubai Knowledge Park",
    "Deira",
    "Bur Dubai",
    "Al Karama",
    "Satwa",
    "Al Quoz",
    "Bluewaters Island",
    "Dubai Design District (d3)",
    "Al Wasl",
    "Arabian Ranches",
    "Motor City",
    "Discovery Gardens",
    "International City",
    "Dubai Festival City",
    "Dubai Creek Harbour",
    "Mirdif",
    "Jebel Ali",
    "Dubai Production City"
]

categories = {
    "Dining": ["Restaurant", "Tapas bar", "Seafood restaurant", "Vermuteria", "Cafe"],
    "Nightlife": ["Cocktail bar", "Wine bar", "Beach club", "Nightclub", "Beer hall"],
    "Parks_Recreation": ["Beach", "Park", "lake", "Viewpoint", "Promenade"],
    "Wellness_Lifestyle": ["Gym", "Yoga studio", "Pilates studio", "Spa", "Bakery", "Surf school"],
    "Culture": ["things to do", "Museum", "Art Gallery", "Basilica", "Historic site", "Food Market"],
    "Work_Infrastructure": ["Cafe with wifi", "Coworking space"]
}

# ---------------------------------------------------------
# 🛠️ Helper Functions
# ---------------------------------------------------------
def load_history():
    if not os.path.exists(HISTORY_FILE):
        return set()
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def save_query_to_history(query):
    """Thread-safe history saving"""
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(f"{query}\n")

def extract_coords(url):
    if pd.isna(url) or url == '':
        return None, None
    try:
        match_place = re.search(r'!3d(-?[\d\.]+)!4d(-?[\d\.]+)', url)
        if match_place:
            return float(match_place.group(1)), float(match_place.group(2))

        match_view = re.search(r'@(-?[\d\.]+),(-?[\d\.]+)', url)
        if match_view:
            return float(match_view.group(1)), float(match_view.group(2))

        return None, None
    except Exception:
        return None, None

async def append_to_csv_safe(data_list, path):
    """Thread-safe CSV appending with file locking"""
    if not data_list:
        return
    
    new_df = pd.DataFrame(data_list)
    
    # Simple file locking mechanism
    lock_file = f"{path}.lock"
    max_wait = 30
    waited = 0
    
    while os.path.exists(lock_file) and waited < max_wait:
        await asyncio.sleep(0.1)
        waited += 0.1
    
    try:
        # Create lock
        with open(lock_file, 'w') as f:
            f.write(str(os.getpid()))
        
        if os.path.exists(path):
            try:
                existing_df = pd.read_csv(path, encoding='utf-8-sig')
                combined_df = pd.concat([existing_df, new_df], ignore_index=True).drop_duplicates(subset=['place_name'])
                combined_df.to_csv(path, index=False, encoding='utf-8-sig')
            except:
                new_df.to_csv(path, index=False, encoding='utf-8-sig')
        else:
            new_df.to_csv(path, index=False, encoding='utf-8-sig')
    finally:
        # Remove lock
        if os.path.exists(lock_file):
            os.remove(lock_file)

def parse_proxy(proxy_string):
    """Convert proxy string to Playwright format"""
    parts = proxy_string.split(':')
    if len(parts) == 2:
        return {
            "server": f"http://{parts[0]}:{parts[1]}"
        }
    return None

# ---------------------------------------------------------
# 🔍 The Scraper - WITH PROXY SUPPORT
# ---------------------------------------------------------
async def scrape_places(query, category_name, proxy_config, scraper_id):
    async with async_playwright() as p:
        try:
            # Launch browser with proxy
            browser = await p.chromium.launch(
                headless=False, 
                channel="chrome",
                proxy=proxy_config
            )
            context = await browser.new_context(viewport={"width": 1920, "height": 1080})
            page = await context.new_page()

            print(f"[Scraper {scraper_id}] 🔎 Searching: {query}")

            # Dubai: center point (Downtown Dubai) + zoom
            await page.goto(
                f"https://www.google.com/maps/search/{query.replace(' ', '+')}/@25.2048,55.2708,13z?hl=en"
            )

            try:
                await page.click('button:has-text("Accept all")', timeout=5000)
            except:
                pass

            # Fast scrolling
            await page.mouse.move(100, 400)
            for _ in range(4):
                await page.mouse.wheel(0, 3000)
                await asyncio.sleep(random.uniform(1, 2))

            place_elements = await page.locator('a.hfpxzc').all()
            print(f"[Scraper {scraper_id}] ✨ Found {len(place_elements)} places")

            success_count = 0
            results = []

            for i, _ in enumerate(place_elements[:30]):
                try:
                    el = page.locator('a.hfpxzc').nth(i)

                    try:
                        await el.scroll_into_view_if_needed(timeout=3000)
                    except:
                        await page.mouse.move(100, 400)
                        await page.mouse.wheel(0, 500)
                        await asyncio.sleep(random.uniform(0.5, 1))
                        el = page.locator('a.hfpxzc').nth(i)

                    if await el.count() == 0:
                        continue

                    try:
                        await el.click(timeout=5000)
                    except Exception as e:
                        if "intercepts pointer" in str(e):
                            await page.keyboard.press("Escape")
                            await asyncio.sleep(random.uniform(0.5, 1))
                            await el.click(timeout=5000)
                        else:
                            raise e

                    await asyncio.sleep(random.uniform(2, 3))

                    # Extract business name
                    name_selectors = [
                        'div[role="main"] h1.DUwDvf',
                        'h1.fontHeadlineLarge',
                        'div.lS67m h1'
                    ]

                    name = ""
                    for sel in name_selectors:
                        locator = page.locator(sel).first
                        if await locator.is_visible():
                            name = await locator.inner_text()
                            if name and "Results" not in name:
                                break

                    if not name or "Results" in name:
                        continue

                    success_count += 1

                    place_url = page.url
                    lat, lon = extract_coords(place_url)

                    rating = 0.0
                    try:
                        rating_text = await page.locator('div.F7nice span').first.inner_text()
                        rating = float(rating_text.split()[0].replace(',', '.'))
                    except:
                        pass

                    # Reviews
                    reviews_content = ""
                    num_reviews = 0
                    try:
                        review_tab = page.locator('button[aria-label*="Reviews for"], button:has-text("Reviews")').first
                        if await review_tab.is_visible():
                            await review_tab.click()
                            await asyncio.sleep(random.uniform(1, 1.5))

                            try:
                                sort_btn = page.locator('button[aria-label*="Sort reviews"]')
                                if await sort_btn.is_visible():
                                    await sort_btn.click()
                                    await page.keyboard.press("Escape")

                                for _ in range(15):
                                    await page.keyboard.press("PageDown")
                                    await asyncio.sleep(random.uniform(0.2, 0.4))

                                await asyncio.sleep(random.uniform(0.5, 1))
                            except Exception as e:
                                print(f"[Scraper {scraper_id}] ⚠️ Scroll failed: {e}")

                            try:
                                for _ in range(2):
                                    await page.evaluate("""() => {
                                        document.querySelectorAll('button').forEach(btn => {
                                            const txt = (btn.innerText || '').toLowerCase();
                                            const label = (btn.getAttribute('aria-label') || '').toLowerCase();

                                            const safe_words = ['more', 'see more', 'read more', 'más', 'ver más', 'leer más'];
                                            const isGoogleExpandBtn = btn.classList.contains('w8nwRe') || btn.classList.contains('Ky2Syb');
                                            const textMatch = safe_words.some(w => txt.includes(w) || label.includes(w));
                                            const isNotShare = !label.includes('share') && !label.includes('compartir') && !label.includes('options');

                                            if ((isGoogleExpandBtn || textMatch) && isNotShare) {
                                                btn.click();
                                            }
                                        });
                                    }""")
                                    await asyncio.sleep(random.uniform(0.8, 1.2))
                            except:
                                pass

                            review_texts = await page.locator('.wiI7pd').all()
                            texts = []
                            for rt in review_texts[:50]:
                                txt = await rt.inner_text()
                                if txt:
                                    clean_txt = txt.replace('\n', ' ').strip()
                                    if len(clean_txt) > 20:
                                        texts.append(clean_txt)

                            reviews_content = " || ".join(texts)
                            num_reviews = len(texts)

                            await page.keyboard.press("Escape")
                    except Exception as e:
                        print(f"[Scraper {scraper_id}] ⚠️ Error extracting reviews: {e}")

                    results.append({
                        "place_name": name,
                        "url": place_url,
                        "category": category_name,
                        "rating": rating,
                        "num_of_reviews": num_reviews,
                        "reviews_content": reviews_content,
                        "latitude": lat,
                        "longitude": lon
                    })

                    print(f"[Scraper {scraper_id}] ✅ {success_count}. {name} | {rating}★ | {num_reviews} reviews")

                    if len(results) >= 5:
                        await append_to_csv_safe(results, FINAL_DATA_CHECKPOINT)
                        results = []

                except Exception as e:
                    print(f"[Scraper {scraper_id}] ❌ Error at index {i}: {e}")

            await append_to_csv_safe(results, FINAL_DATA_CHECKPOINT)
            await browser.close()
            return True
            
        except Exception as e:
            print(f"[Scraper {scraper_id}] ❌ Fatal error: {e}")
            try:
                await browser.close()
            except:
                pass
            return False

# ---------------------------------------------------------
# 🚀 Parallel Scraper Manager
# ---------------------------------------------------------
async def run_scraper_instance(scraper_id, tasks, proxy):
    """Run a single scraper instance with its own task queue"""
    proxy_config = parse_proxy(proxy)
    print(f"\n[Scraper {scraper_id}] 🚀 Starting with proxy {proxy}")
    print(f"[Scraper {scraper_id}] 📋 Assigned {len(tasks)} tasks\n")
    
    completed_queries = load_history()
    query_count = 0
    
    for task in tasks:
        if task["query"] in completed_queries:
            print(f"[Scraper {scraper_id}] ⏩ Skipping: {task['query']}")
            continue
        
        success = await scrape_places(task["query"], task["category"], proxy_config, scraper_id)
        
        if success:
            save_query_to_history(task["query"])
            query_count += 1
            
            # Smart waiting
            if query_count % QUERIES_BEFORE_BREAK == 0:
                wait_time = random.uniform(*LONG_BREAK_RANGE)
                print(f"[Scraper {scraper_id}] 🛌 BREAK: {wait_time:.1f}s...")
                await asyncio.sleep(wait_time)
            else:
                wait_time = random.uniform(*SHORT_BREAK_RANGE)
                print(f"[Scraper {scraper_id}] 💤 {wait_time:.1f}s...")
                await asyncio.sleep(wait_time)
        else:
            # If scraper fails, wait a bit longer
            print(f"[Scraper {scraper_id}] ⚠️ Failed, waiting 30s...")
            await asyncio.sleep(30)
    
    print(f"\n[Scraper {scraper_id}] ✅ COMPLETED! Processed {query_count} queries\n")

async def main():
    print("="*60)
    print("🏙️  DUBAI PARALLEL SCRAPER - 8 INSTANCES")
    print("="*60)
    
    # Generate all tasks
    ALL_TASKS = [
        {"query": f"{p_type} in {dist}, Dubai, UAE", "category": cat_name}
        for dist in DUBAI_NEIGHBORHOODS
        for cat_name, p_types in categories.items()
        for p_type in p_types
    ]
    
    random.shuffle(ALL_TASKS)
    
    # Split tasks into chunks for each scraper
    chunk_size = len(ALL_TASKS) // NUM_PARALLEL_SCRAPERS
    task_chunks = [
        ALL_TASKS[i * chunk_size:(i + 1) * chunk_size] 
        for i in range(NUM_PARALLEL_SCRAPERS)
    ]
    
    # Add remaining tasks to the last chunk
    remainder = len(ALL_TASKS) % NUM_PARALLEL_SCRAPERS
    if remainder > 0:
        task_chunks[-1].extend(ALL_TASKS[-remainder:])
    
    print(f"\n📊 Total tasks: {len(ALL_TASKS)}")
    print(f"🔢 Tasks per scraper: ~{chunk_size}")
    print(f"🌐 Using {NUM_PARALLEL_SCRAPERS} proxies\n")
    
    # Select best proxies (fastest ones)
    selected_proxies = PROXIES[:NUM_PARALLEL_SCRAPERS]
    
    print("🌍 Proxy assignments:")
    for i, proxy in enumerate(selected_proxies, 1):
        print(f"   Scraper {i}: {proxy}")
    print()
    
    # Create scraper tasks
    scraper_tasks = [
        run_scraper_instance(i+1, task_chunks[i], selected_proxies[i])
        for i in range(NUM_PARALLEL_SCRAPERS)
    ]
    
    # Run all scrapers in parallel
    start_time = datetime.now()
    await asyncio.gather(*scraper_tasks)
    end_time = datetime.now()
    
    duration = (end_time - start_time).total_seconds()
    print("\n" + "="*60)
    print(f"🎉 ALL SCRAPERS COMPLETED!")
    print(f"⏱️  Total time: {duration/60:.1f} minutes")
    print(f"📁 Data saved to: {FINAL_DATA_CHECKPOINT}")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())