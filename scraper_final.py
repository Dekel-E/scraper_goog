import asyncio
import re
import pandas as pd
import os
import random
import json
import time
from playwright.async_api import async_playwright
from datetime import datetime
from collections import defaultdict
import psutil
import aiofiles
# import fcntl
from pathlib import Path

# ---------------------------------------------------------
# ⚙️ CONFIGURATION
# ---------------------------------------------------------
NUM_PARALLEL_SCRAPERS = 8

QUERIES_BEFORE_BREAK = 100
SHORT_BREAK_RANGE = (2, 5)
LONG_BREAK_RANGE = (20, 45)

SKIP_REVIEWS = False
MAX_PLACES_PER_QUERY = 20
BATCH_SIZE = 10
SCROLL_ITERATIONS = 3
REVIEW_SCROLL_COUNT = 10

ENABLE_AUTO_RETRY = True
MAX_RETRIES = 3
ENABLE_PROXY_ROTATION = True
ENABLE_PROGRESS_TRACKING = True
ENABLE_QUALITY_CHECKS = True
CHECKPOINT_INTERVAL = 50

COORDS_PATTERN_PLACE = re.compile(r'!3d(-?[\d\.]+)!4d(-?[\d\.]+)')
COORDS_PATTERN_VIEW = re.compile(r'@(-?[\d\.]+),(-?[\d\.]+)')

def load_proxies():
    """Load proxies from proxies.txt file"""
    proxy_file = os.path.join(os.path.dirname(__file__), 'proxies.txt')
    try:
        with open(proxy_file, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"⚠️  Warning: {proxy_file} not found, using empty proxy list")
        return []

PROXIES = load_proxies()
# ---------------------------------------------------------
# 🗂️ HIERARCHICAL CATEGORIES WITH SUBCATEGORIES
HIERARCHICAL_CATEGORIES = {
    "Dining": {
        "Restaurant": ["Restaurant", "Fine dining", "Rooftop restaurant"],
        "Cafe": ["Cafe", "Coffee shop", "Specialty coffee"],
        "Fast_Food": ["Fast food", "Burger joint", "Pizza place"]
    },
    
    "Food-Sweet": {
        "Ice_Cream": ["Ice cream shop", "Gelato shop", "Frozen yogurt"],
    },
    
    "Nightlife-Bars": {
        "Cocktail": ["Cocktail bar"],
        "Wine": ["Wine bar", "Wine tasting"],
        "Specialty": ["Rooftop bar", "Beach bar", "Sports bar"],
        "Pub": ["Pub"]
    },
    
    "Nightlife-Clubs": {
        "Dance": ["Nightclub", "Dance club"],
        "Entertainment": ["Karaoke bar", "Comedy club"]
    },
    
    "Shopping-General": {
        "Malls": ["Shopping mall",  "Outlet mall"],
        "Markets": ["Market", "Flea market", "Night market", "Farmers market"]
    },
    
    
    "Entertainment-Culture": {
        "Museums": ["Museum", "Art museum", "History museum", "Science museum"],
        "Galleries": ["Art gallery", "Photography gallery"],
        "Landmarks": ["Landmark", "Monument", "Historic site"],

    },
    
    "Entertainment-Activities": {
        "Theater": ["Theater", "Movie theater", "IMAX"],
        "Performance": ["Concert hall", "Opera house", "Ballet"],
        "Games": ["Arcade", "Bowling", "Escape room", "Board game cafe"],
        "Amusement": ["Amusement park", "Theme park", "Water park"]
    },
    
    "Parks-Recreation": {
        "Nature": ["Park", "Botanical garden", "Nature reserve"],
        "Beach": ["Beach", "Beach club", "Private beach"],
        "Views": ["Viewpoint", "Observation deck", "Scenic spot"],
    },
    
    "Wellness-Fitness": {
        "Gym": ["Gym"],
        "Yoga": ["Yoga studio"],
    },
    
    "Wellness-Spa": {
        "Spa": ["Spa", "Day spa", "Luxury spa"],
        "Bath": ["Hammam", "Turkish bath", "Onsen", "Sauna"],
    },
    
    
    "Work-Remote": {
        "Coworking": ["Coworking space", "Hot desk", "Private office"],
        "Cafes": ["Cafe with wifi", "Work-friendly cafe", "Quiet cafe"],
        "Business": ["Business center", "Meeting room"]
    },
    
    "Experiences-Tours": {
        "Walking": ["Walking tour", "Food tour", "Historical tour"],
        "Adventure": ["Bike tour", "Segway tour", "Boat tour"],
        "Classes": ["Cooking class", "Wine tasting", "Art workshop"]
    },
    
    "Experiences-Activities": {
        "Water": ["Diving center", "Surf school", "Kayaking", "Snorkeling"],
        "Adventure": ["Zip lining", "Rock climbing", "Parasailing"],
        "Indoor": ["Escape room",  "Trampoline park"]
    },
    
    "Family-Kids": {
        "Play": ["Playground", "Indoor playground", "Kids club"],
        "Entertainment": ["Kids museum", "Petting zoo", "Toy store"],
        "Activities": ["Mini golf", "Laser tag", "Bowling"]
    },

}
# ---------------------------------------------------------
# 🌍 CITIES
# ---------------------------------------------------------
CITIES = {
    "bangkok": {
        "name": "Bangkok, Thailand",
        "coords": "13.7563,100.5018",
        "zoom": "13z",
        "neighborhoods": [
            "Sukhumvit", "Silom", "Siam", "Sathorn", "Ratchathewi",
            "Phrom Phong", "Thong Lo", "Ekkamai", "Asok", "Nana",
            "Ari", "Phaya Thai", "Riverside", "Chinatown", "Khao San Road"
        ]
    },
    "dubai": {
        "name": "Dubai, UAE",
        "coords": "25.2048,55.2708",
        "zoom": "13z",
        "neighborhoods": [
            "Downtown Dubai", "Dubai Marina", "JBR", "Palm Jumeirah",
            "Business Bay", "DIFC", "City Walk", "La Mer", "Jumeirah"
        ]
    },
    "tokyo": {
        "name": "Tokyo, Japan",
        "coords": "35.6762,139.6503",
        "zoom": "13z",
        "neighborhoods": [
            "Shibuya", "Shinjuku", "Harajuku", "Roppongi", "Ginza",
            "Akihabara", "Asakusa", "Ueno", "Ikebukuro", "Ebisu"
        ]
    },
    "newyork": {
        "name": "New York City, USA",
        "coords": "40.7128,-74.0060",
        "zoom": "12z",
        "neighborhoods": [
            "Manhattan", "Brooklyn", "Times Square", "Midtown", "Chelsea",
            "SoHo", "Tribeca", "East Village", "Williamsburg", "DUMBO"
        ]
    },
    "rome": {
        "name": "Rome, Italy",
        "coords": "41.9028,12.4964",
        "zoom": "13z",
        "neighborhoods": [
            "Centro Storico", "Trastevere", "Monti", "Testaccio",
            "Vatican City", "Spanish Steps", "Trevi Fountain", "Colosseum"
        ]
    },
    "amsterdam": {
        "name": "Amsterdam, Netherlands",
        "coords": "52.3676,4.9041",
        "zoom": "13z",
        "neighborhoods": [
            "City Centre", "Jordaan", "De Pijp", "Oud-West",
            "Museum Quarter", "Red Light District", "Waterlooplein"
        ]
    },
    "london": {
        "name": "London, UK",
        "coords": "51.5074,-0.1278",
        "zoom": "12z",
        "neighborhoods": [
            "Westminster", "Soho", "Covent Garden", "Shoreditch", "Camden",
            "Notting Hill", "Kensington", "Chelsea", "King's Cross"
        ]
    },
    "eilat": {
        "name": "Eilat, Israel",
        "coords": "29.5581,34.9482",
        "zoom": "14z",
        "neighborhoods": [
            "North Beach", "Coral Beach", "City Center", "Hotel District", "Marina"
        ]
    }
}

# ---------------------------------------------------------
# 🔒 THREAD-SAFE FILE OPERATIONS
# ---------------------------------------------------------
class ThreadSafeFileManager:
    """Manages all file operations with proper locking"""
    
    def __init__(self):
        self.locks = defaultdict(asyncio.Lock)
    
    async def append_line(self, filename, content):
        """Thread-safe line append with file locking"""
        async with self.locks[filename]:
            try:
                # Use aiofiles for async file operations
                async with aiofiles.open(filename, 'a', encoding='utf-8') as f:
                    await f.write(f"{content}\n")
                    await f.flush()
                    os.fsync(f.fileno())
            except Exception as e:
                print(f"⚠️ File write error ({filename}): {e}")
    
    async def read_lines(self, filename):
        """Thread-safe file reading"""
        async with self.locks[filename]:
            try:
                if not os.path.exists(filename):
                    return set()
                
                async with aiofiles.open(filename, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    return set(line.strip() for line in content.split('\n') if line.strip())
            except Exception as e:
                print(f"⚠️ File read error ({filename}): {e}")
                return set()
    
    async def append_to_csv(self, data_list, filepath):
        """Thread-safe CSV appending with proper locking"""
        if not data_list:
            return
        
        async with self.locks[filepath]:
            try:
                new_df = pd.DataFrame(data_list)
                
                # Data quality checks
                if ENABLE_QUALITY_CHECKS:
                    new_df = new_df[new_df['place_name'].str.len() > 2]
                    new_df = new_df[new_df['rating'] <= 5.0]
                
                # Use file locking for CSV operations
                if os.path.exists(filepath):
                    try:
                        existing_df = pd.read_csv(filepath, encoding='utf-8-sig')
                        combined_df = pd.concat([existing_df, new_df], ignore_index=True)
                        combined_df = combined_df.drop_duplicates(subset=['place_name', 'url'])
                        combined_df.to_csv(filepath, index=False, encoding='utf-8-sig')
                    except Exception as e:
                        print(f"⚠️ CSV merge error: {e}")
                        new_df.to_csv(filepath, index=False, encoding='utf-8-sig')
                else:
                    new_df.to_csv(filepath, index=False, encoding='utf-8-sig')
                    
            except Exception as e:
                print(f"⚠️ CSV append error: {e}")

# Global file manager instance
file_manager = ThreadSafeFileManager()

# ---------------------------------------------------------
# 📊 THREAD-SAFE PROGRESS TRACKER
# ---------------------------------------------------------
class ProgressTracker:
    def __init__(self, total_tasks, num_scrapers):
        self.total_tasks = total_tasks
        self.num_scrapers = num_scrapers
        self.start_time = time.time()
        
        self.stats = {
            'completed': 0,
            'failed': 0,
            'skipped': 0,
            'retried': 0,
            'places_scraped': 0,
            'avg_places_per_query': 0,
            'queries_per_minute': 0,
            'eta_minutes': 0,
            'scraper_stats': defaultdict(lambda: {'completed': 0, 'failed': 0, 'speed': []})
        }
        
        self.lock = asyncio.Lock()
    
    async def update(self, scraper_id, status, places_count=0, query_time=0):
        async with self.lock:
            if status == 'completed':
                self.stats['completed'] += 1
                self.stats['places_scraped'] += places_count
                self.stats['scraper_stats'][scraper_id]['completed'] += 1
                if query_time > 0:
                    self.stats['scraper_stats'][scraper_id]['speed'].append(query_time)
            elif status == 'failed':
                self.stats['failed'] += 1
                self.stats['scraper_stats'][scraper_id]['failed'] += 1
            elif status == 'skipped':
                self.stats['skipped'] += 1
            elif status == 'retried':
                self.stats['retried'] += 1
            
            elapsed = time.time() - self.start_time
            if self.stats['completed'] > 0:
                self.stats['avg_places_per_query'] = self.stats['places_scraped'] / self.stats['completed']
                self.stats['queries_per_minute'] = (self.stats['completed'] / elapsed) * 60
                
                remaining = self.total_tasks - (self.stats['completed'] + self.stats['skipped'])
                if self.stats['queries_per_minute'] > 0:
                    self.stats['eta_minutes'] = remaining / self.stats['queries_per_minute']
    
    def get_summary(self):
        elapsed = time.time() - self.start_time
        progress_pct = ((self.stats['completed'] + self.stats['skipped']) / self.total_tasks) * 100
        
        return f"""
╔════════════════════════════════════════════════════════════════╗
║  📊 SCRAPER PROGRESS                                          ║
╠════════════════════════════════════════════════════════════════╣
║  Progress: {progress_pct:.1f}% ({self.stats['completed'] + self.stats['skipped']}/{self.total_tasks})
║  ✅ Done: {self.stats['completed']}  |  ❌ Failed: {self.stats['failed']}  |  ⏭️  Skip: {self.stats['skipped']}
║  🔄 Retries: {self.stats['retried']}  |  🏢 Places: {self.stats['places_scraped']}
║  ⏱️  Speed: {self.stats['queries_per_minute']:.1f}/min
║  📍 Avg: {self.stats['avg_places_per_query']:.1f} places/query
║  ⏳ ETA: {self.stats['eta_minutes']:.0f} min  |  ⏰ Elapsed: {elapsed/60:.1f} min
╚════════════════════════════════════════════════════════════════╝
"""

# ---------------------------------------------------------
# 🔄 PROXY MANAGER
# ---------------------------------------------------------
class ProxyManager:
    def __init__(self, proxies):
        self.proxies = proxies.copy()
        self.failed_proxies = set()
        self.proxy_performance = {p: {'success': 0, 'fail': 0} for p in proxies}
        self.lock = asyncio.Lock()
    
    async def get_proxy(self, current_proxy=None):
        async with self.lock:
            available = [p for p in self.proxies if p not in self.failed_proxies]
            
            if not available:
                self.failed_proxies.clear()
                available = self.proxies.copy()
            
            available.sort(key=lambda p: self.proxy_performance[p]['success'], reverse=True)
            
            for proxy in available:
                if proxy != current_proxy:
                    return proxy
            
            return available[0] if available else self.proxies[0]
    
    async def report_result(self, proxy, success):
        async with self.lock:
            if success:
                self.proxy_performance[proxy]['success'] += 1
            else:
                self.proxy_performance[proxy]['fail'] += 1
                
                if self.proxy_performance[proxy]['fail'] > 5:
                    self.failed_proxies.add(proxy)

# ---------------------------------------------------------
# 💾 CHECKPOINT MANAGER
# ---------------------------------------------------------
class CheckpointManager:
    def __init__(self, city_key):
        self.checkpoint_file = f"checkpoint_{city_key}.json"
        self.lock = asyncio.Lock()
    
    async def save_checkpoint(self, data):
        async with self.lock:
            try:
                async with aiofiles.open(self.checkpoint_file, 'w') as f:
                    await f.write(json.dumps(data, indent=2))
            except Exception as e:
                print(f"⚠️ Checkpoint save error: {e}")
    
    async def load_checkpoint(self):
        async with self.lock:
            try:
                if os.path.exists(self.checkpoint_file):
                    async with aiofiles.open(self.checkpoint_file, 'r') as f:
                        content = await f.read()
                        return json.loads(content)
            except:
                pass
            return None
    
    def clear_checkpoint(self):
        if os.path.exists(self.checkpoint_file):
            os.remove(self.checkpoint_file)

# ---------------------------------------------------------
# 🛠️ HELPER FUNCTIONS
# ---------------------------------------------------------
def get_city_files(city_key):
    return {
        "history": f"search_history_{city_key}.txt",
        "data": f"{city_key}_final.csv",
        "failed": f"{city_key}_failed.txt"
    }

def extract_coords(url):
    if not url or pd.isna(url):
        return None, None
    try:
        match = COORDS_PATTERN_PLACE.search(url)
        if match:
            return float(match.group(1)), float(match.group(2))
        
        match = COORDS_PATTERN_VIEW.search(url)
        if match:
            return float(match.group(1)), float(match.group(2))
        
        return None, None
    except:
        return None, None

def parse_proxy(proxy_string):
    parts = proxy_string.split(':')
    if len(parts) == 2:
        return {"server": f"http://{parts[0]}:{parts[1]}"}
    return None

def generate_tasks_with_subcategories(neighborhoods, city_name):
    """Generate tasks with hierarchical categories"""
    tasks = []
    
    for neighborhood in neighborhoods:
        for main_category, subcategories in HIERARCHICAL_CATEGORIES.items():
            for subcategory, poi_types in subcategories.items():
                for poi_type in poi_types:
                    # Full category path: "Entertainment-Culture-Museums"
                    full_category = f"{main_category}-{subcategory}"
                    
                    tasks.append({
                        "query": f"{poi_type} in {neighborhood}, {city_name}",
                        "category": full_category,
                        "main_category": main_category,
                        "subcategory": subcategory,
                        "poi_type": poi_type
                    })
    
    return tasks

# ---------------------------------------------------------
# 🚀 SCRAPER
# ---------------------------------------------------------
async def scrape_places(query, category_info, proxy_config, scraper_id, city_config, 
                       data_file, proxy_manager, tracker, retry_count=0):
    
    query_start_time = time.time()
    
    async with async_playwright() as p:
        browser = None
        try:
            browser = await p.chromium.launch(
                headless=False,
                channel="chrome",
                proxy=proxy_config,
                args=['--disable-blink-features=AutomationControlled']
            )
            
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = await context.new_page()

            await page.goto(
                f"https://www.google.com/maps/search/{query.replace(' ', '+')}/@{city_config['coords']},{city_config['zoom']}?hl=en",
                timeout=30000
            )

            try:
                await page.click('button:has-text("Accept all")', timeout=3000)
            except:
                pass

            await page.mouse.move(100, 400)
            for _ in range(SCROLL_ITERATIONS):
                await page.mouse.wheel(0, 3000)
                await asyncio.sleep(random.uniform(0.8, 1.5))

            place_elements = await page.locator('a.hfpxzc').all()
            total_found = len(place_elements)

            results = []
            success_count = 0

            for i in range(min(total_found, MAX_PLACES_PER_QUERY)):
                try:
                    el = page.locator('a.hfpxzc').nth(i)

                    try:
                        await el.scroll_into_view_if_needed(timeout=2000)
                    except:
                        await page.mouse.wheel(0, 500)
                        await asyncio.sleep(0.5)

                    if await el.count() == 0:
                        continue

                    try:
                        await el.click(timeout=3000)
                    except Exception as e:
                        if "intercepts pointer" in str(e):
                            await page.keyboard.press("Escape")
                            await asyncio.sleep(0.5)
                            await el.click(timeout=3000)
                        else:
                            continue

                    await asyncio.sleep(random.uniform(1.5, 2.5))

                    name = ""
                    try:
                        name_loc = page.locator('div[role="main"] h1.DUwDvf').first
                        if await name_loc.is_visible(timeout=2000):
                            name = await name_loc.inner_text()
                    except:
                        pass

                    if not name or "Results" in name:
                        continue

                    success_count += 1
                    place_url = page.url
                    lat, lon = extract_coords(place_url)

                    rating = 0.0
                    try:
                        rating_text = await page.locator('div.F7nice span').first.inner_text(timeout=1000)
                        rating = float(rating_text.split()[0].replace(',', '.'))
                    except:
                        pass

                    reviews_content = ""
                    num_reviews = 0

                    if not SKIP_REVIEWS:
                        try:
                            review_tab = page.locator('button[aria-label*="Reviews"]').first
                            if await review_tab.is_visible(timeout=1000):
                                await review_tab.click()
                                await asyncio.sleep(random.uniform(0.8, 1.2))

                                for _ in range(REVIEW_SCROLL_COUNT):
                                    await page.keyboard.press("PageDown")
                                    await asyncio.sleep(0.2)

                                await asyncio.sleep(0.5)

                                await page.evaluate("""() => {
                                    document.querySelectorAll('button.w8nwRe').forEach(btn => btn.click());
                                }""")
                                await asyncio.sleep(0.8)

                                review_texts = await page.locator('.wiI7pd').all()
                                texts = []
                                for rt in review_texts[:30]:
                                    txt = await rt.inner_text()
                                    if txt and len(txt.strip()) > 20:
                                        texts.append(txt.replace('\n', ' ').strip())

                                reviews_content = " || ".join(texts)
                                num_reviews = len(texts)
                                await page.keyboard.press("Escape")
                        except:
                            pass

                    # Include hierarchical category information
                    results.append({
                        "place_name": name,
                        "url": place_url,
                        "category": category_info["category"],  # "Entertainment-Culture-Museums"
                        "main_category": category_info["main_category"],  # "Entertainment"
                        "subcategory": category_info["subcategory"],  # "Culture"
                        "poi_type": category_info["poi_type"],  # "Museum"
                        "rating": rating,
                        "num_of_reviews": num_reviews,
                        "reviews_content": reviews_content,
                        "latitude": lat,
                        "longitude": lon
                    })

                    if len(results) >= BATCH_SIZE:
                        await file_manager.append_to_csv(results, data_file)
                        results = []

                except Exception as e:
                    continue

            if results:
                await file_manager.append_to_csv(results, data_file)

            await browser.close()
            
            query_time = time.time() - query_start_time
            await tracker.update(scraper_id, 'completed', places_count=success_count, query_time=query_time)
            
            if ENABLE_PROXY_ROTATION and proxy_manager:
                proxy_str = proxy_config['server'].split('//')[1]
                await proxy_manager.report_result(proxy_str, True)
            
            return True, success_count

        except Exception as e:
            if browser:
                try:
                    await browser.close()
                except:
                    pass
            
            await tracker.update(scraper_id, 'failed')
            
            if ENABLE_PROXY_ROTATION and proxy_manager:
                proxy_str = proxy_config['server'].split('//')[1]
                await proxy_manager.report_result(proxy_str, False)
            
            if ENABLE_AUTO_RETRY and retry_count < MAX_RETRIES:
                await tracker.update(scraper_id, 'retried')
                print(f"[S{scraper_id}] 🔄 Retry {retry_count+1}/{MAX_RETRIES}")
                await asyncio.sleep(5 * (retry_count + 1))
                
                new_proxy_config = proxy_config
                if ENABLE_PROXY_ROTATION and proxy_manager:
                    proxy_str = proxy_config['server'].split('//')[1]
                    new_proxy = await proxy_manager.get_proxy(proxy_str)
                    new_proxy_config = parse_proxy(new_proxy)
                
                return await scrape_places(
                    query, category_info, new_proxy_config, scraper_id, 
                    city_config, data_file, proxy_manager, tracker, retry_count + 1
                )
            
            return False, 0

# ---------------------------------------------------------
# 🚀 Scraper Instance
# ---------------------------------------------------------
async def run_scraper_instance(scraper_id, tasks, proxy, city_config, files, 
                               proxy_manager, tracker, checkpoint_mgr):
    
    proxy_config = parse_proxy(proxy)
    print(f"[S{scraper_id}] 🚀 Start | {len(tasks)} tasks | {proxy}")
    
    completed = await file_manager.read_lines(files['history'])
    query_count = 0
    checkpoint_counter = 0
    
    for task in tasks:
        if task["query"] in completed:
            await tracker.update(scraper_id, 'skipped')
            continue
        
        # Pass full category info
        category_info = {
            "category": task["category"],
            "main_category": task["main_category"],
            "subcategory": task["subcategory"],
            "poi_type": task["poi_type"]
        }
        
        success, places_count = await scrape_places(
            task["query"], 
            category_info, 
            proxy_config, 
            scraper_id, 
            city_config,
            files['data'],
            proxy_manager,
            tracker
        )
        
        if success:
            await file_manager.append_line(files['history'], task["query"])
            query_count += 1
            checkpoint_counter += 1
            
            if checkpoint_counter >= CHECKPOINT_INTERVAL:
                await checkpoint_mgr.save_checkpoint({
                    'scraper_id': scraper_id,
                    'completed': query_count,
                    'last_query': task["query"],
                    'timestamp': datetime.now().isoformat()
                })
                checkpoint_counter = 0
            
            if query_count % 10 == 0 and ENABLE_PROGRESS_TRACKING:
                print(tracker.get_summary())
            
            if query_count % QUERIES_BEFORE_BREAK == 0:
                wait = random.uniform(*LONG_BREAK_RANGE)
                await asyncio.sleep(wait)
            else:
                wait = random.uniform(*SHORT_BREAK_RANGE)
                await asyncio.sleep(wait)
        else:
            await file_manager.append_line(files['failed'], f"{task['query']} | Max retries | {datetime.now()}")
            await asyncio.sleep(15)
    
    print(f"[S{scraper_id}] ✅ DONE | {query_count} queries")

# ---------------------------------------------------------
# 🎯 City Scraping
# ---------------------------------------------------------
async def scrape_city(city_key, city_config):
    print("\n" + "="*70)
    print(f"🌍 SCRAPING: {city_config['name'].upper()}")
    print("="*70)
    
    files = get_city_files(city_key)
    
    checkpoint_mgr = CheckpointManager(city_key)
    proxy_manager = ProxyManager(PROXIES) if ENABLE_PROXY_ROTATION else None
    
    # Generate hierarchical tasks
    ALL_TASKS = generate_tasks_with_subcategories(
        city_config['neighborhoods'],
        city_config['name']
    )
    
    random.shuffle(ALL_TASKS)
    
    tracker = ProgressTracker(len(ALL_TASKS), NUM_PARALLEL_SCRAPERS)
    
    chunk_size = len(ALL_TASKS) // NUM_PARALLEL_SCRAPERS
    task_chunks = [
        ALL_TASKS[i * chunk_size:(i + 1) * chunk_size] 
        for i in range(NUM_PARALLEL_SCRAPERS)
    ]
    
    if len(ALL_TASKS) % NUM_PARALLEL_SCRAPERS:
        task_chunks[-1].extend(ALL_TASKS[NUM_PARALLEL_SCRAPERS * chunk_size:])
    
    print(f"📊 {len(ALL_TASKS)} tasks | ~{chunk_size}/scraper")
    print(f"🗂️  Hierarchical categories enabled")
    print(f"📁 Output: {files['data']}\n")
    
    selected_proxies = PROXIES[:NUM_PARALLEL_SCRAPERS]
    
    scraper_tasks = [
        run_scraper_instance(
            i+1, 
            task_chunks[i], 
            selected_proxies[i], 
            city_config,
            files,
            proxy_manager,
            tracker,
            checkpoint_mgr
        )
        for i in range(NUM_PARALLEL_SCRAPERS)
    ]
    
    start = datetime.now()
    await asyncio.gather(*scraper_tasks)
    duration = (datetime.now() - start).total_seconds()
    
    print(tracker.get_summary())
    
    print("\n" + "="*70)
    print(f"✅ {city_config['name'].upper()} COMPLETED")
    print(f"⏱️  Duration: {duration/60:.1f} minutes")
    print(f"📁 Data: {files['data']}")
    print("="*70)
    
    checkpoint_mgr.clear_checkpoint()

# ---------------------------------------------------------
# 🎯 MAIN
# ---------------------------------------------------------
async def main():
    print("="*70)
    print("🚀 THREAD-SAFE MULTI-CITY SCRAPER WITH SUBCATEGORIES")
    print("="*70)
    
    city_keys = list(CITIES.keys())
    for i, key in enumerate(city_keys, 1):
        print(f"{i}. {CITIES[key]['name']}")
    
    print("="*70)
    
    while True:
        try:
            selection = input("\nEnter city number (1-8) or 'all': ").strip().lower()
            
            if selection == 'all':
                print("\n🚀 Running ALL cities...\n")
                total_start = datetime.now()
                
                for city_key, city_config in CITIES.items():
                    await scrape_city(city_key, city_config)
                    print("\n⏸️  5 min break...\n")
                    await asyncio.sleep(300)
                
                total_duration = (datetime.now() - total_start).total_seconds()
                print("\n" + "="*70)
                print("🎉 ALL CITIES COMPLETED!")
                print(f"⏱️  Total: {total_duration/3600:.1f} hours")
                print("="*70)
                break
            
            else:
                choice = int(selection)
                if 1 <= choice <= len(city_keys):
                    city_key = city_keys[choice - 1]
                    await scrape_city(city_key, CITIES[city_key])
                    break
                else:
                    print(f"❌ Enter 1-{len(city_keys)}")
        
        except ValueError:
            print("❌ Invalid input")
        except KeyboardInterrupt:
            print("\n\n❌ Cancelled")
            break

if __name__ == "__main__": 
    asyncio.run(main())