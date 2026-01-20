import asyncio
import re
import pandas as pd
import os
import random
from playwright.async_api import async_playwright
from datetime import datetime

# ---------------------------------------------------------
# ⚙️ MULTI-CITY CONFIGURATION
# ---------------------------------------------------------
NUM_PARALLEL_SCRAPERS = 8

# TIMING SETTINGS
QUERIES_BEFORE_BREAK = 100
SHORT_BREAK_RANGE = (2, 5)
LONG_BREAK_RANGE = (20, 45)

# SPEED OPTIMIZATIONS
SKIP_REVIEWS = False  # Set True for 5x speed
MAX_PLACES_PER_QUERY = 20
BATCH_SIZE = 10
SCROLL_ITERATIONS = 3
REVIEW_SCROLL_COUNT = 10

# Pre-compiled regex
COORDS_PATTERN_PLACE = re.compile(r'!3d(-?[\d\.]+)!4d(-?[\d\.]+)')
COORDS_PATTERN_VIEW = re.compile(r'@(-?[\d\.]+),(-?[\d\.]+)')

# Load proxies from config file
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
# 🌍 CITY CONFIGURATIONS
# ---------------------------------------------------------
CITIES = {
    "bangkok": {
        "name": "Bangkok, Thailand",
        "coords": "13.7563,100.5018",  # Central Bangkok
        "zoom": "13z",
        "neighborhoods": [
            "Sukhumvit", "Silom", "Siam", "Sathorn", "Ratchathewi",
            "Phrom Phong", "Thong Lo", "Ekkamai", "Asok", "Nana",
            "Ari", "Phaya Thai", "Phloen Chit", "Chit Lom", "Ratchaprasong",
            "Pratunam", "Riverside", "Charoenkrung", "Chinatown (Yaowarat)",
            "Khao San Road", "Bangrak", "Lumphini", "Wireless Road",
            "Victory Monument", "Chatuchak", "Bang Na", "Bearing",
            "On Nut", "Phra Khanong", "Lat Phrao"
        ]
    },
    "tokyo": {
        "name": "Tokyo, Japan",
        "coords": "35.6762,139.6503",  # Shibuya area
        "zoom": "13z",
        "neighborhoods": [
            "Shibuya", "Shinjuku", "Harajuku", "Roppongi", "Ginza",
            "Akihabara", "Asakusa", "Ueno", "Ikebukuro", "Ebisu",
            "Meguro", "Nakameguro", "Daikanyama", "Shimokitazawa",
            "Kichijoji", "Odaiba", "Marunouchi", "Nihonbashi",
            "Omotesando", "Yoyogi", "Kagurazaka", "Ryogoku",
            "Tsukiji", "Yurakucho", "Azabu", "Jiyugaoka",
            "Sangenjaya", "Nakano", "Koenji", "Kanda"
        ]
    },
    "newyork": {
        "name": "New York City, USA",
        "coords": "40.7128,-74.0060",  # Manhattan
        "zoom": "12z",
        "neighborhoods": [
            "Manhattan", "Brooklyn", "Queens", "Bronx",
            "Times Square", "Midtown", "Upper East Side", "Upper West Side",
            "Chelsea", "Greenwich Village", "SoHo", "Tribeca", "Lower East Side",
            "East Village", "West Village", "Financial District", "Battery Park",
            "Harlem", "Murray Hill", "Gramercy", "Flatiron", "NoMad",
            "Hell's Kitchen", "Columbus Circle", "Lincoln Center",
            "Williamsburg", "DUMBO", "Brooklyn Heights", "Park Slope",
            "Long Island City", "Astoria", "Flushing"
        ]
    },
    "rome": {
        "name": "Rome, Italy",
        "coords": "41.9028,12.4964",  # Colosseum area
        "zoom": "13z",
        "neighborhoods": [
            "Centro Storico", "Trastevere", "Monti", "Testaccio",
            "Prati", "Vatican City", "Spanish Steps", "Trevi Fountain",
            "Pantheon", "Campo de' Fiori", "Piazza Navona", "Colosseum",
            "Roman Forum", "Aventino", "Esquilino", "San Lorenzo",
            "Pigneto", "Ostiense", "EUR", "Flaminio",
            "Salario", "Trieste", "Nomentano", "Tiburtino",
            "Monteverde", "Garbatella", "San Giovanni", "Celio"
        ]
    },
    "amsterdam": {
        "name": "Amsterdam, Netherlands",
        "coords": "52.3676,4.9041",  # Dam Square
        "zoom": "13z",
        "neighborhoods": [
            "City Centre", "Jordaan", "De Pijp", "Oud-West",
            "Oud-Zuid", "Plantage", "Waterlooplein", "Red Light District",
            "Nine Streets", "Museum Quarter", "Vondelpark", "Westerpark",
            "Oost", "Noord", "Nieuw-West", "Rivierenbuurt",
            "Zuid", "Buitenveldert", "RAI", "Olympic Stadium",
            "NDSM", "Kinkerbuurt", "Hoofddorpplein", "Leidseplein",
            "Rembrandtplein", "Dam Square", "Spui", "Kalverstraat"
        ]
    },
    "london": {
        "name": "London, UK",
        "coords": "51.5074,-0.1278",  # Central London
        "zoom": "12z",
        "neighborhoods": [
            "Westminster", "Soho", "Covent Garden", "Mayfair", "Shoreditch",
            "Camden", "Islington", "Notting Hill", "Kensington", "Chelsea",
            "South Kensington", "Knightsbridge", "Belgravia", "Fitzrovia",
            "Marylebone", "King's Cross", "Clerkenwell", "Hoxton",
            "Dalston", "Hackney", "Bethnal Green", "Brick Lane",
            "Whitechapel", "Canary Wharf", "Greenwich", "Brixton",
            "Clapham", "Battersea", "Hammersmith", "Fulham"
        ]
    },
    "eilat": {
        "name": "Eilat, Israel",
        "coords": "29.5581,34.9482",  # Central Eilat
        "zoom": "14z",
        "neighborhoods": [
            "North Beach", "Coral Beach", "City Center", "Hotel District",
            "Marina", "Aquaba Border", "Eilat Mountains", "Industrial Zone",
            "Airport Area", "Shahamon", "Shalom Center", "New Tourist Center",
            "Underwater Observatory", "Dolphin Reef", "Timna Park Area"
        ]
    }
}

categories = {
    "Dining": ["Restaurant", "Cafe", "Seafood restaurant"],
    "Nightlife": ["Cocktail bar", "Wine bar", "Beach club", "Nightclub"],
    "Parks_Recreation": ["Beach", "Park", "Viewpoint"],
    "Wellness_Lifestyle": ["Gym", "Yoga studio", "Spa"],
       "Culture": [
        "Museum", "Art Gallery", "Historic site", "Monument",
        "Landmark", "Church", "Temple", "Mosque", "Synagogue",
        "Palace", "Castle", "Observatory", "Planetarium",
        "Cultural center", "Library", "Exhibition center"
    ],
    "Shopping": ["Shopping mall", "Market", "Souvenir shop"],
    "Work_Infrastructure": ["Cafe with wifi", "Coworking space"],
       "Experiences": [
        "Cooking class", "Wine tasting", "Brewery tour", "Distillery tour",
        "Walking tour", "Bike tour", "Food tour", 
        "Photography tour", "Surfing school"
    ]
}

# ---------------------------------------------------------
# 🛠️ HELPER FUNCTIONS
# ---------------------------------------------------------
def get_city_files(city_key):
    """Get file paths for a specific city"""
    return {
        "history": f"search_history_{city_key}.txt",
        "data": f"{city_key}_final.csv"
    }

def load_history(filename):
    if not os.path.exists(filename):
        return set()
    with open(filename, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def save_query_to_history(query, filename):
    with open(filename, "a", encoding="utf-8") as f:
        f.write(f"{query}\n")

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
        if os.path.exists(lock_file):
            os.remove(lock_file)

def parse_proxy(proxy_string):
    parts = proxy_string.split(':')
    if len(parts) == 2:
        return {"server": f"http://{parts[0]}:{parts[1]}"}
    return None

# ---------------------------------------------------------
# 🚀 OPTIMIZED SCRAPER
# ---------------------------------------------------------
async def scrape_places(query, category_name, proxy_config, scraper_id, city_config, data_file):
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

            print(f"[S{scraper_id}] 🔎 {query}")

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
            print(f"[S{scraper_id}] ✨ {total_found} places")

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

                    print(f"[S{scraper_id}] ✅ {success_count}. {name} | {rating}★")

                    if len(results) >= BATCH_SIZE:
                        await append_to_csv_safe(results, data_file)
                        results = []

                except Exception as e:
                    continue

            if results:
                await append_to_csv_safe(results, data_file)

            await browser.close()
            return True

        except Exception as e:
            print(f"[S{scraper_id}] ❌ Fatal: {str(e)[:100]}")
            if browser:
                try:
                    await browser.close()
                except:
                    pass
            return False

# ---------------------------------------------------------
# 🚀 Parallel Manager
# ---------------------------------------------------------
async def run_scraper_instance(scraper_id, tasks, proxy, city_config, history_file, data_file):
    proxy_config = parse_proxy(proxy)
    print(f"[S{scraper_id}] 🚀 Start | {len(tasks)} tasks | {proxy}")
    
    completed = load_history(history_file)
    query_count = 0
    
    for task in tasks:
        if task["query"] in completed:
            continue
        
        success = await scrape_places(
            task["query"], 
            task["category"], 
            proxy_config, 
            scraper_id, 
            city_config,
            data_file
        )
        
        if success:
            save_query_to_history(task["query"], history_file)
            query_count += 1
            
            if query_count % QUERIES_BEFORE_BREAK == 0:
                wait = random.uniform(*LONG_BREAK_RANGE)
                print(f"[S{scraper_id}] 🛌 {wait:.0f}s break")
                await asyncio.sleep(wait)
            else:
                wait = random.uniform(*SHORT_BREAK_RANGE)
                await asyncio.sleep(wait)
        else:
            await asyncio.sleep(15)
    
    print(f"[S{scraper_id}] ✅ DONE | {query_count} queries")

async def scrape_city(city_key, city_config):
    """Scrape a single city with 8 parallel scrapers"""
    print("\n" + "="*70)
    print(f"🌍 SCRAPING: {city_config['name'].upper()}")
    print("="*70)
    
    files = get_city_files(city_key)
    
    # Generate tasks for this city
    ALL_TASKS = [
        {"query": f"{p_type} in {dist}, {city_config['name']}", "category": cat_name}
        for dist in city_config['neighborhoods']
        for cat_name, p_types in categories.items()
        for p_type in p_types
    ]
    
    random.shuffle(ALL_TASKS)
    
    # Split tasks
    chunk_size = len(ALL_TASKS) // NUM_PARALLEL_SCRAPERS
    task_chunks = [
        ALL_TASKS[i * chunk_size:(i + 1) * chunk_size] 
        for i in range(NUM_PARALLEL_SCRAPERS)
    ]
    
    if len(ALL_TASKS) % NUM_PARALLEL_SCRAPERS:
        task_chunks[-1].extend(ALL_TASKS[NUM_PARALLEL_SCRAPERS * chunk_size:])
    
    print(f"📊 {len(ALL_TASKS)} tasks | ~{chunk_size}/scraper")
    print(f"⚡ Reviews: {'DISABLED' if SKIP_REVIEWS else 'ENABLED'}")
    print(f"🎯 {MAX_PLACES_PER_QUERY} places/query")
    print(f"📁 Output: {files['data']}\n")
    
    selected_proxies = PROXIES[:NUM_PARALLEL_SCRAPERS]
    
    scraper_tasks = [
        run_scraper_instance(
            i+1, 
            task_chunks[i], 
            selected_proxies[i], 
            city_config,
            files['history'],
            files['data']
        )
        for i in range(NUM_PARALLEL_SCRAPERS)
    ]
    
    start = datetime.now()
    await asyncio.gather(*scraper_tasks)
    duration = (datetime.now() - start).total_seconds()
    
    print("\n" + "="*70)
    print(f"✅ {city_config['name'].upper()} COMPLETED")
    print(f"⏱️  Duration: {duration/60:.1f} minutes")
    print(f"📁 Data: {files['data']}")
    print("="*70)

# ---------------------------------------------------------
# 🎯 MAIN - SELECT CITY
# ---------------------------------------------------------
async def main():
    print("="*70)
    print("🌍 MULTI-CITY SCRAPER - SELECT A CITY")
    print("="*70)
    
    # Display menu
    city_keys = list(CITIES.keys())
    for i, key in enumerate(city_keys, 1):
        print(f"{i}. {CITIES[key]['name']}")
    
    print("="*70)
    
    # Get user selection
    while True:
        try:
            selection = input("\nEnter city number (1-8) or 'all' to run all cities: ").strip().lower()
            
            if selection == 'all':
                # Run all cities sequentially
                print("\n🚀 Running ALL cities sequentially...\n")
                total_start = datetime.now()
                
                for city_key, city_config in CITIES.items():
                    await scrape_city(city_key, city_config)
                    print("\n⏸️  5 minute break before next city...\n")
                    await asyncio.sleep(300)  # 5 min break between cities
                
                total_duration = (datetime.now() - total_start).total_seconds()
                print("\n" + "="*70)
                print("🎉 ALL CITIES COMPLETED!")
                print(f"⏱️  Total time: {total_duration/60:.1f} minutes ({total_duration/3600:.1f} hours)")
                print("="*70)
                break
            
            else:
                choice = int(selection)
                if 1 <= choice <= len(city_keys):
                    city_key = city_keys[choice - 1]
                    city_config = CITIES[city_key]
                    await scrape_city(city_key, city_config)
                    break
                else:
                    print(f"❌ Please enter a number between 1 and {len(city_keys)}")
        
        except ValueError:
            print("❌ Invalid input. Please enter a number or 'all'")
        except KeyboardInterrupt:
            print("\n\n❌ Cancelled by user")
            break

if __name__ == "__main__":
    asyncio.run(main())