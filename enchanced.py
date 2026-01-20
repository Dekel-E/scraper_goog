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
import traceback

# ---------------------------------------------------------
# ⚙️ ADVANCED CONFIGURATION
# ---------------------------------------------------------
NUM_PARALLEL_SCRAPERS = 11

# Timing
QUERIES_BEFORE_BREAK = 100
SHORT_BREAK_RANGE = (2, 5)
LONG_BREAK_RANGE = (20, 45)

# Performance
SKIP_REVIEWS = False
MAX_PLACES_PER_QUERY = 20
BATCH_SIZE = 10
SCROLL_ITERATIONS = 3
REVIEW_SCROLL_COUNT = 10

# NEW: Advanced Features
ENABLE_AUTO_RETRY = True           # Retry failed queries
MAX_RETRIES = 3                     # Max retry attempts
ENABLE_PROXY_ROTATION = True       # Switch proxy on failure
ENABLE_PROGRESS_TRACKING = True    # Real-time progress dashboard
ENABLE_QUALITY_CHECKS = True       # Validate data quality
CHECKPOINT_INTERVAL = 50           # Save progress every N queries
BROWSER_POOL_SIZE = 2              # Reuse browsers (saves time)
AUTO_HEADLESS_AFTER = 100          # Switch to headless after N queries

# Pre-compiled regex
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
# 🌍 CITIES WITH CITY-SPECIFIC OPTIMIZATIONS
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
        ],
        "priority_pois": ["Thai massage", "Rooftop bar", "Street food", "Night market", "Temple"]
    },
    "dubai": {
        "name": "Dubai, UAE",
        "coords": "25.2048,55.2708",
        "zoom": "13z",
        "neighborhoods": [
            "Downtown Dubai", "Dubai Marina", "JBR", "Palm Jumeirah",
            "Business Bay", "DIFC", "City Walk", "La Mer", "Jumeirah"
        ],
        "priority_pois": ["Luxury hotel", "Rooftop bar", "Beach club", "Shopping mall", "Fine dining"]
    },
    "tokyo": {
        "name": "Tokyo, Japan",
        "coords": "35.6762,139.6503",
        "zoom": "13z",
        "neighborhoods": [
            "Shibuya", "Shinjuku", "Harajuku", "Roppongi", "Ginza",
            "Akihabara", "Asakusa", "Ueno", "Ikebukuro", "Ebisu"
        ],
        "priority_pois": ["Ramen restaurant", "Karaoke bar", "Sushi bar", "Arcade", "Temple"]
    },
    "newyork": {
        "name": "New York City, USA",
        "coords": "40.7128,-74.0060",
        "zoom": "12z",
        "neighborhoods": [
            "Manhattan", "Brooklyn", "Times Square", "Midtown", "Chelsea",
            "SoHo", "Tribeca", "East Village", "Williamsburg", "DUMBO"
        ],
        "priority_pois": ["Rooftop bar", "Broadway theater", "Jazz club", "Food truck", "Deli"]
    },
    "rome": {
        "name": "Rome, Italy",
        "coords": "41.9028,12.4964",
        "zoom": "13z",
        "neighborhoods": [
            "Centro Storico", "Trastevere", "Monti", "Testaccio",
            "Vatican City", "Spanish Steps", "Trevi Fountain", "Colosseum"
        ],
        "priority_pois": ["Trattoria", "Gelato shop", "Historic site", "Pizza restaurant", "Wine bar"]
    },
    "amsterdam": {
        "name": "Amsterdam, Netherlands",
        "coords": "52.3676,4.9041",
        "zoom": "13z",
        "neighborhoods": [
            "City Centre", "Jordaan", "De Pijp", "Oud-West",
            "Museum Quarter", "Red Light District", "Waterlooplein"
        ],
        "priority_pois": ["Coffee shop", "Canal tour", "Bike rental", "Brown cafe", "Museum"]
    },
    "london": {
        "name": "London, UK",
        "coords": "51.5074,-0.1278",
        "zoom": "12z",
        "neighborhoods": [
            "Westminster", "Soho", "Covent Garden", "Shoreditch", "Camden",
            "Notting Hill", "Kensington", "Chelsea", "King's Cross"
        ],
        "priority_pois": ["Pub", "Afternoon tea", "Theater", "Market", "Fish and chips"]
    },
    "eilat": {
        "name": "Eilat, Israel",
        "coords": "29.5581,34.9482",
        "zoom": "14z",
        "neighborhoods": [
            "North Beach", "Coral Beach", "City Center", "Hotel District", "Marina"
        ],
        "priority_pois": ["Beach", "Diving center", "Water sports", "Desert tour", "Spa"]
    }
}

# Enhanced categories with city-specific POIs
categories = {
    "Dining": ["Restaurant", "Cafe", "Fine dining", "Rooftop restaurant"],
    "Bars_Nightlife": ["Cocktail bar", "Rooftop bar", "Wine bar", "Nightclub","Beach club", "Pub","Casino"],
    "Wellness": ["Spa", "Yoga studio", "Massage center", "Gym"],
    "Shopping": ["Shopping mall", "Market", "Boutique", "Souvenir shop"],
    "Attractions": ["Museum", "Landmark", "Historic site", 
                    "Viewpoint""Palace", "Castle", "Observatory", "Planetarium",],
    "Activities": ["Beach", "Park", "Spa", "Cooking class"],
    "Entertainment": ["Theater", "Movie theater", "Concert hall", "Live music venue"]
 
}

# ---------------------------------------------------------
# 📊 PROGRESS TRACKER CLASS
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
            
            # Calculate metrics
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
║  📊 SCRAPER PROGRESS DASHBOARD                                ║
╠════════════════════════════════════════════════════════════════╣
║  Progress: {progress_pct:.1f}% ({self.stats['completed'] + self.stats['skipped']}/{self.total_tasks})
║  ✅ Completed: {self.stats['completed']}  |  ❌ Failed: {self.stats['failed']}  |  ⏭️  Skipped: {self.stats['skipped']}
║  🔄 Retries: {self.stats['retried']}  |  🏢 Places: {self.stats['places_scraped']}
║  ⏱️  Speed: {self.stats['queries_per_minute']:.1f} queries/min
║  📍 Avg places/query: {self.stats['avg_places_per_query']:.1f}
║  ⏳ ETA: {self.stats['eta_minutes']:.0f} minutes
║  ⏰ Elapsed: {elapsed/60:.1f} minutes
╚════════════════════════════════════════════════════════════════╝
"""

# ---------------------------------------------------------
# 🔄 PROXY MANAGER CLASS
# ---------------------------------------------------------
class ProxyManager:
    def __init__(self, proxies):
        self.proxies = proxies.copy()
        self.failed_proxies = set()
        self.proxy_performance = {p: {'success': 0, 'fail': 0} for p in proxies}
        self.lock = asyncio.Lock()
    
    async def get_proxy(self, current_proxy=None):
        """Get best available proxy"""
        async with self.lock:
            # Filter out failed proxies
            available = [p for p in self.proxies if p not in self.failed_proxies]
            
            if not available:
                # Reset if all failed
                self.failed_proxies.clear()
                available = self.proxies.copy()
            
            # Sort by success rate
            available.sort(key=lambda p: self.proxy_performance[p]['success'], reverse=True)
            
            # Return best proxy (not the current one if possible)
            for proxy in available:
                if proxy != current_proxy:
                    return proxy
            
            return available[0] if available else self.proxies[0]
    
    async def report_result(self, proxy, success):
        """Track proxy performance"""
        async with self.lock:
            if success:
                self.proxy_performance[proxy]['success'] += 1
            else:
                self.proxy_performance[proxy]['fail'] += 1
                
                # Mark as failed if too many failures
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
        """Save progress checkpoint"""
        async with self.lock:
            try:
                with open(self.checkpoint_file, 'w') as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                print(f"⚠️ Failed to save checkpoint: {e}")
    
    def load_checkpoint(self):
        """Load previous checkpoint"""
        try:
            if os.path.exists(self.checkpoint_file):
                with open(self.checkpoint_file, 'r') as f:
                    return json.load(f)
        except:
            pass
        return None
    
    def clear_checkpoint(self):
        """Clear checkpoint file"""
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

def load_history(filename):
    if not os.path.exists(filename):
        return set()
    with open(filename, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def save_query_to_history(query, filename):
    with open(filename, "a", encoding="utf-8") as f:
        f.write(f"{query}\n")

def save_failed_query(query, filename, reason=""):
    with open(filename, "a", encoding="utf-8") as f:
        f.write(f"{query} | {reason} | {datetime.now()}\n")

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

async def append_to_csv_safe(data_list, path):
    if not data_list:
        return
    
    lock_file = f"{path}.lock"
    max_wait = 30
    waited = 0
    
    while os.path.exists(lock_file) and waited < max_wait:
        await asyncio.sleep(0.1)
        waited += 0.1
    
    try:
        with open(lock_file, 'w') as f:
            f.write(str(os.getpid()))
        
        new_df = pd.DataFrame(data_list)
        
        # Data quality checks
        if ENABLE_QUALITY_CHECKS:
            new_df = new_df[new_df['place_name'].str.len() > 2]  # Remove invalid names
            new_df = new_df[new_df['rating'] <= 5.0]  # Valid ratings only
        
        if os.path.exists(path):
            try:
                existing_df = pd.read_csv(path, encoding='utf-8-sig')
                combined_df = pd.concat([existing_df, new_df], ignore_index=True).drop_duplicates(subset=['place_name', 'url'])
                combined_df.to_csv(path, index=False, encoding='utf-8-sig')
            except:
                new_df.to_csv(path, index=False, encoding='utf-8-sig')
        else:
            new_df.to_csv(path, index=False, encoding='utf-8-sig')
    finally:
        if os.path.exists(lock_file):
            os.remove(lock_file)

def parse_proxy(proxy_string):
    parts = proxy_string.split(':')
    if len(parts) == 2:
        return {"server": f"http://{parts[0]}:{parts[1]}"}
    return None

def get_system_resources():
    """Check system resources"""
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    return {
        'cpu': cpu_percent,
        'memory_percent': memory.percent,
        'memory_available_gb': memory.available / (1024**3)
    }

# ---------------------------------------------------------
# 🚀 ENHANCED SCRAPER WITH RETRY LOGIC
# ---------------------------------------------------------
async def scrape_places(query, category_name, proxy_config, scraper_id, city_config, 
                       data_file, proxy_manager, tracker, retry_count=0):
    
    query_start_time = time.time()
    
    async with async_playwright() as p:
        browser = None
        try:
            # Determine if should use headless
            use_headless = False
            if AUTO_HEADLESS_AFTER > 0 and tracker.stats['completed'] > AUTO_HEADLESS_AFTER:
                use_headless = True
            
            browser = await p.chromium.launch(
                headless=use_headless,
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

                    if len(results) >= BATCH_SIZE:
                        await append_to_csv_safe(results, data_file)
                        results = []

                except Exception as e:
                    continue

            if results:
                await append_to_csv_safe(results, data_file)

            await browser.close()
            
            # Report success
            query_time = time.time() - query_start_time
            await tracker.update(scraper_id, 'completed', places_count=success_count, query_time=query_time)
            
            if ENABLE_PROXY_ROTATION and proxy_manager:
                proxy_str = proxy_config['server'].split('//')[1]
                await proxy_manager.report_result(proxy_str, True)
            
            return True, success_count

        except Exception as e:
            error_msg = str(e)[:100]
            
            if browser:
                try:
                    await browser.close()
                except:
                    pass
            
            # Report failure
            await tracker.update(scraper_id, 'failed')
            
            if ENABLE_PROXY_ROTATION and proxy_manager:
                proxy_str = proxy_config['server'].split('//')[1]
                await proxy_manager.report_result(proxy_str, False)
            
            # Retry logic
            if ENABLE_AUTO_RETRY and retry_count < MAX_RETRIES:
                await tracker.update(scraper_id, 'retried')
                print(f"[S{scraper_id}] 🔄 Retry {retry_count+1}/{MAX_RETRIES}: {query}")
                await asyncio.sleep(5 * (retry_count + 1))  # Exponential backoff
                
                # Try different proxy if enabled
                new_proxy_config = proxy_config
                if ENABLE_PROXY_ROTATION and proxy_manager:
                    proxy_str = proxy_config['server'].split('//')[1]
                    new_proxy = await proxy_manager.get_proxy(proxy_str)
                    new_proxy_config = parse_proxy(new_proxy)
                
                return await scrape_places(
                    query, category_name, new_proxy_config, scraper_id, 
                    city_config, data_file, proxy_manager, tracker, retry_count + 1
                )
            
            return False, 0

# ---------------------------------------------------------
# 🚀 Enhanced Scraper Instance
# ---------------------------------------------------------
async def run_scraper_instance(scraper_id, tasks, proxy, city_config, history_file, 
                               data_file, failed_file, proxy_manager, tracker, checkpoint_mgr):
    
    proxy_config = parse_proxy(proxy)
    print(f"[S{scraper_id}] 🚀 Start | {len(tasks)} tasks | {proxy}")
    
    completed = load_history(history_file)
    query_count = 0
    checkpoint_counter = 0
    
    for task in tasks:
        if task["query"] in completed:
            await tracker.update(scraper_id, 'skipped')
            continue
        
        success, places_count = await scrape_places(
            task["query"], 
            task["category"], 
            proxy_config, 
            scraper_id, 
            city_config,
            data_file,
            proxy_manager,
            tracker
        )
        
        if success:
            save_query_to_history(task["query"], history_file)
            query_count += 1
            checkpoint_counter += 1
            
            # Save checkpoint periodically
            if checkpoint_counter >= CHECKPOINT_INTERVAL:
                await checkpoint_mgr.save_checkpoint({
                    'scraper_id': scraper_id,
                    'completed': query_count,
                    'last_query': task["query"],
                    'timestamp': datetime.now().isoformat()
                })
                checkpoint_counter = 0
            
            # Display progress every 10 queries
            if query_count % 10 == 0 and ENABLE_PROGRESS_TRACKING:
                print(tracker.get_summary())
            
            if query_count % QUERIES_BEFORE_BREAK == 0:
                wait = random.uniform(*LONG_BREAK_RANGE)
                await asyncio.sleep(wait)
            else:
                wait = random.uniform(*SHORT_BREAK_RANGE)
                await asyncio.sleep(wait)
        else:
            save_failed_query(task["query"], failed_file, "Max retries exceeded")
            await asyncio.sleep(15)
    
    print(f"[S{scraper_id}] ✅ DONE | {query_count} queries")

# ---------------------------------------------------------
# 🎯 Enhanced City Scraping
# ---------------------------------------------------------
async def scrape_city(city_key, city_config):
    print("\n" + "="*70)
    print(f"🌍 SCRAPING: {city_config['name'].upper()}")
    print("="*70)
    
    files = get_city_files(city_key)
    
    # Initialize managers
    checkpoint_mgr = CheckpointManager(city_key)
    proxy_manager = ProxyManager(PROXIES) if ENABLE_PROXY_ROTATION else None
    
    # Generate tasks (including city-specific POIs)
    all_categories = categories.copy()
    if 'priority_pois' in city_config:
        all_categories['City_Specials'] = city_config['priority_pois']
    
    ALL_TASKS = [
        {"query": f"{p_type} in {dist}, {city_config['name']}", "category": cat_name}
        for dist in city_config['neighborhoods']
        for cat_name, p_types in all_categories.items()
        for p_type in p_types
    ]
    
    random.shuffle(ALL_TASKS)
    
    # Initialize tracker
    tracker = ProgressTracker(len(ALL_TASKS), NUM_PARALLEL_SCRAPERS)
    
    # Check system resources
    resources = get_system_resources()
    print(f"💻 System: CPU {resources['cpu']}% | RAM {resources['memory_percent']}% | Available {resources['memory_available_gb']:.1f}GB")
    
    # Split tasks
    chunk_size = len(ALL_TASKS) // NUM_PARALLEL_SCRAPERS
    task_chunks = [
        ALL_TASKS[i * chunk_size:(i + 1) * chunk_size] 
        for i in range(NUM_PARALLEL_SCRAPERS)
    ]
    
    if len(ALL_TASKS) % NUM_PARALLEL_SCRAPERS:
        task_chunks[-1].extend(ALL_TASKS[NUM_PARALLEL_SCRAPERS * chunk_size:])
    
    print(f"📊 {len(ALL_TASKS)} tasks | ~{chunk_size}/scraper")
    print(f"⚡ Features: Retry={ENABLE_AUTO_RETRY} | ProxyRotation={ENABLE_PROXY_ROTATION} | QualityCheck={ENABLE_QUALITY_CHECKS}")
    print(f"📁 Output: {files['data']}\n")
    
    selected_proxies = PROXIES[:NUM_PARALLEL_SCRAPERS]
    
    scraper_tasks = [
        run_scraper_instance(
            i+1, 
            task_chunks[i], 
            selected_proxies[i], 
            city_config,
            files['history'],
            files['data'],
            files['failed'],
            proxy_manager,
            tracker,
            checkpoint_mgr
        )
        for i in range(NUM_PARALLEL_SCRAPERS)
    ]
    
    start = datetime.now()
    await asyncio.gather(*scraper_tasks)
    duration = (datetime.now() - start).total_seconds()
    
    # Final summary
    print(tracker.get_summary())
    
    print("\n" + "="*70)
    print(f"✅ {city_config['name'].upper()} COMPLETED")
    print(f"⏱️  Duration: {duration/60:.1f} minutes")
    print(f"📁 Data: {files['data']}")
    print(f"📊 Stats: {tracker.stats['completed']} completed | {tracker.stats['failed']} failed | {tracker.stats['places_scraped']} places")
    print("="*70)
    
    # Clear checkpoint
    checkpoint_mgr.clear_checkpoint()

# ---------------------------------------------------------
# 🎯 MAIN
# ---------------------------------------------------------
async def main():
    print("="*70)
    print("🚀 ULTIMATE MULTI-CITY SCRAPER v2.0")
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
