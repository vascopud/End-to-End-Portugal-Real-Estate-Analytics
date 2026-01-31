import os
import psycopg2
import requests
import re
import time
import random
import json
from bs4 import BeautifulSoup
from urllib.parse import unquote
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
FREGUESIAS_FILE = 'scraper/freguesias_list.txt'
PROGRESS_FILE = 'scraper/progress.json'
BASE_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'

# Cooldown Settings
LONG_SLEEP_INTERVAL = 100 # Every 100 pages
LONG_SLEEP_DURATION = 180 # 3 minutes

def get_db_connection():
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            database=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD')
        )
        return conn
    except Exception as e:
        print(f"Error connecting to database: {e}")
        return None

def extract_location_from_url(url):
    """
    Parses the URL to extract (Distrito, Concelho, Freguesia) from URL segments.
    Expected format: .../resultados/comprar/apartamento/distrito/concelho/freguesia
    Example: .../apartamento/lisboa/sintra/agualva-e-mira-sintra -> (Lisboa, Sintra, Agualva E Mira Sintra)
    """
    try:
        # Strip query parameters (?limit=72 etc)
        base = url.split('?')[0]
        # Remove empty strings from split
        segments = [s for s in base.split('/') if s]
        
        # We strictly look for 'apartamento' segment
        if 'apartamento' not in segments:
            return None
            
        idx = segments.index('apartamento')
        remaining = segments[idx+1:]
        
        # Helper to clean slug (e.g. 'sao-jose' -> 'Sao Jose')
        def clean_slug(s):
            return unquote(s).replace('-', ' ').title()

        if len(remaining) >= 3:
            return clean_slug(remaining[0]), clean_slug(remaining[1]), clean_slug(remaining[2])
        elif len(remaining) == 2:
            return clean_slug(remaining[0]), clean_slug(remaining[1]), "Todos"
        
        return None
    except Exception:
        return None

def load_freguesias_urls():
    """
    Reads freguesias_list.txt and returns a flat list of scrape tasks.
    Each line in the file is a URL for apartment purchases in a specific freguesia.
    Parses location (Distrito, Concelho, Freguesia) directly from URL segments.
    """
    tasks = []
    if not os.path.exists(FREGUESIAS_FILE):
        print(f"Error: {FREGUESIAS_FILE} not found.")
        return []
    
    with open(FREGUESIAS_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            url = line.strip()
            
            # Parse location from URL
            loc = extract_location_from_url(url)
            if loc:
                dist, conc, freg = loc
            else:
                # If parsing fails, use placeholder values
                dist, conc, freg = "Unknown", "Unknown", "Unknown"
            
            tasks.append({
                'distrito': dist,
                'concelho': conc,
                'freguesia': freg,
                'url': url
            })
    
    return tasks

def save_properties(conn, properties, context):
    """Upserts properties into the database with hierarchy info."""
    if not conn or not properties:
        return

    query = """
    INSERT INTO properties (title, price, raw_location, distrito, concelho, freguesia, area_m2, room_count, url)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (url) DO UPDATE 
    SET price = EXCLUDED.price,
        scraped_at = CURRENT_TIMESTAMP;
    """
    
    try:
        cur = conn.cursor()
        for prop in properties:
            if not prop.get('url'):
                continue
                
            cur.execute(query, (
                prop['title'],
                prop['price'],
                prop['location'], # raw_location
                context['distrito'],
                context['concelho'],
                context['freguesia'],
                prop['area_m2'],
                prop['rooms'],
                prop['url']
            ))
        
        conn.commit()
        cur.close()
    except Exception as e:
        print(f"Error saving to database: {e}")
        conn.rollback()

def load_progress():
    """Loads state: {'task_index': int, 'page_num': int, 'url': str, 'line_number': int}"""
    if not os.path.exists(PROGRESS_FILE):
        return {'task_index': 0, 'page_num': 1, 'url': '', 'line_number': 1}
    try:
        with open(PROGRESS_FILE, 'r') as f:
            data = json.load(f)
            # Ensure backwards compatibility with old progress files
            if 'url' not in data:
                data['url'] = ''
            if 'line_number' not in data:
                data['line_number'] = data.get('task_index', 0) + 1
            return data
    except Exception:
        return {'task_index': 0, 'page_num': 1, 'url': '', 'line_number': 1}

def save_progress(task_idx, page_num, url='', line_number=None):
    """Saves state with task index, page number, URL, and line number (1-indexed)."""
    try:
        os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)
        if line_number is None:
            line_number = task_idx + 1 
        with open(PROGRESS_FILE, 'w') as f:
            json.dump({
                'task_index': task_idx, 
                'page_num': page_num,
                'url': url,
                'line_number': line_number
            }, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save progress: {e}")

def scrape_page(base_url, page_num):
    """
    Scrapes a single page with robust error handling and retries.
    Returns:
      - list of items (if success)
      - [] (if empty page / end of pagination)
      - raises Exception (if persistent failure that shouldn't stop the loop logic from retrying)
    """
    separator = '&' if '?' in base_url else '?'
    url = f"{base_url}{separator}limit=72&page={page_num}"
    
    headers = {
        'User-Agent': BASE_USER_AGENT,
        'Accept-Language': 'pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7',
        'Referer': 'https://www.imovirtual.com/'
    }

    # Retry loop for 404/5xx errors or connection drops
    while True:
        try:
            response = requests.get(url, headers=headers, timeout=20)
            
            # Handle 404: Usually means end of pagination on Imovirtual
            if response.status_code == 404:
                return [] 
            
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            
            # Step 1: Extract Metadata from __NEXT_DATA__ (Prioritize for robust pagination)
            nd = soup.find('script', id='__NEXT_DATA__')
            metadata = {}
            if nd:
                try:
                    data = json.loads(nd.string)
                    search_data = data.get('props', {}).get('pageProps', {}).get('data', {}).get('searchAds', {})
                    if not search_data:
                         search_data = data.get('props', {}).get('pageProps', {}).get('data', {})
                    
                    total_hits = int(search_data.get('totalHits', 0))
                    pagination = search_data.get('pagination', {})
                    actual_page = pagination.get('currentPage', 1)
                    
                    metadata = {
                        'total_hits': total_hits,
                        'actual_page': actual_page,
                        'items_in_json': search_data.get('items', []) or search_data.get('results', [])
                    }

                    # CRITICAL: Termination check
                    # If page > 1 but server returns page 1 or explicitly says 0 hits, it's a fallback.
                    if page_num > 1 and (actual_page != page_num or total_hits == 0):
                        print(f"    End of results detected via metadata (Req: {page_num}, Actual: {actual_page}, Hits: {total_hits})")
                        return []
                except: pass

            # Step 2: Extract Items (Strategy 1: __NEXT_DATA__ - preferred)
            if metadata.get('items_in_json'):
                for item in metadata['items_in_json']:
                    try:
                        # Skip promoted/recommended items if we are past page 1 and hits are 0
                        if item.get('isPromoted') and page_num > 1 and metadata.get('total_hits', 0) == 0:
                            continue
                        
                        res_data = {
                            'title': item.get('title', 'N/A'),
                            'price': int(item.get('totalPrice', {}).get('value', 0)) if item.get('totalPrice') else 0,
                            'location': f"{item.get('location',{}).get('city',{}).get('name','')}, {item.get('location',{}).get('district',{}).get('name','')}",
                            'area_m2': float(item.get('areaInSquareMeters', 0)) if item.get('areaInSquareMeters') else None,
                            'rooms': int(item.get('numberOfRooms', 0)) if item.get('numberOfRooms') else None,
                            'url': f"https://www.imovirtual.com/pt/anuncio/{item.get('slug')}" if item.get('slug') else None
                        }
                        if res_data['url']:
                            results.append(res_data)
                    except: continue

            # Step 3: Extract Items (Strategy 2: JSON-LD - fallback)
            if not results:
                script_tag = soup.find('script', type='application/ld+json')
                if script_tag:
                    try:
                        data = json.loads(script_tag.string)
                        items = []
                        if isinstance(data, dict) and '@graph' in data:
                             for g in data['@graph']:
                                 if 'offers' in g and 'offers' in g['offers']:
                                     items = g['offers']['offers']
                                     break
                        elif isinstance(data, dict) and 'offers' in data:
                             items = data['offers']['offers'] if 'offers' in data['offers'] else [data['offers']]
                        
                        for item in items:
                            try:
                                addr = item.get('itemOffered', {}).get('address', {})
                                loc_str = f"{addr.get('addressLocality','')}, {addr.get('addressRegion','')}".strip(', ')
                                res_data = {
                                    'title': item.get('name', 'N/A'),
                                    'price': int(item.get('price', 0)) if item.get('price') else 0,
                                    'location': loc_str,
                                    'area_m2': float(item.get('itemOffered', {}).get('floorSize', {}).get('value', 0)) if item.get('itemOffered', {}).get('floorSize') else None,
                                    'rooms': int(item.get('itemOffered', {}).get('numberOfRooms', 0)) if item.get('itemOffered', {}).get('numberOfRooms') else None,
                                    'url': item.get('url')
                                }
                                if res_data['url']:
                                    results.append(res_data)
                            except: continue
                    except: pass
            
            # Final safeguard: if page_num > 1 but we only find a tiny number of items 
            # and metadata isn't clear, it might still be a "recommendations" page.
            if page_num > 1 and len(results) < 5 and metadata.get('total_hits', 1) == 0:
                print(f"    Possible recommendation page with 0 hits. Stopping.")
                return []

            return results

        except requests.RequestException as e:
            print(f"    Error fetching {url}: {e}")
            print(f"    Waiting {LONG_SLEEP_DURATION}s before retrying SAME link...")
            time.sleep(LONG_SLEEP_DURATION)
            # Continue loop -> retry
        except Exception as e:
            print(f"    Unexpected error: {e}")
            print(f"    Waiting {LONG_SLEEP_DURATION}s before retrying SAME link...")
            time.sleep(LONG_SLEEP_DURATION)
            # Continue loop -> retry


def main():
    print("Initializing Real Estate Scraper...")
    
    # Load Workload from freguesias_list.txt
    all_tasks = load_freguesias_urls()
    print(f"Loaded {len(all_tasks)} freguesias to scrape (Apartment Sales Only).")
    if not all_tasks:
        return

    # Load Progress
    progress = load_progress()
    start_task_idx = progress['task_index']
    start_page_num = progress['page_num']
    
    print(f"\nResuming from Line {progress.get('line_number', start_task_idx + 1)} of freguesias_list.txt")
    if progress.get('url'):
        print(f"Last URL: {progress['url']}")
    
    conn = get_db_connection()
    if not conn:
        print("Warning: DB connection failed initially. Will retry later in loop.")

    # Counters
    total_scraped_session = 0
    pages_session = 0

    try:
        for i in range(start_task_idx, len(all_tasks)):
            task = all_tasks[i]
            line_number = i + 1  # Lines are 1-indexed
            
            # Determine start page
            current_page = start_page_num if i == start_task_idx else 1
            
            print(f"\n[Line {line_number}/{len(all_tasks)}] {task['distrito']} > {task['concelho']} > {task['freguesia']}")
            print(f"  URL: {task['url']}")
            
            while True:
                # Cooldown
                if pages_session > 0 and pages_session % LONG_SLEEP_INTERVAL == 0:
                    print(f"--- LONG SLEEP ({LONG_SLEEP_DURATION}s) ---")
                    if conn: 
                        try: conn.close()
                        except: pass
                    time.sleep(LONG_SLEEP_DURATION)
                    conn = get_db_connection()
                
                print(f"  Page {current_page}...", end='\r')
                listings = scrape_page(task['url'], current_page)
                
                if listings:
                    if not conn or conn.closed:
                         conn = get_db_connection()
                    
                    save_properties(conn, listings, task)
                    save_progress(i, current_page, task['url'], line_number)
                    
                    count = len(listings)
                    total_scraped_session += count
                    pages_session += 1
                    
                    print(f"  Page {current_page}: +{count} items (Total: {total_scraped_session})")
                    current_page += 1
                else:
                    # End of pagination for this task
                    print(f"  Page {current_page}: No items. Moving to next freguesia.")
                    break
                
                # Small nice sleep
                time.sleep(random.uniform(2, 5))
            
            # Task Completed - move to next line
            next_line = line_number + 1
            next_url = all_tasks[i + 1]['url'] if (i + 1) < len(all_tasks) else ''
            save_progress(i + 1, 1, next_url, next_line)

    except KeyboardInterrupt:
        print("\nStopped by user.")
    except Exception as e:
        print(f"\nCritical Error: {e}")
    finally:
        if conn: 
            try: conn.close()
            except: pass
        print("Scraper Stopped.")

if __name__ == "__main__":
    main()
