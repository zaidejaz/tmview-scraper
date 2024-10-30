import random
import subprocess
import requests
import os
import json
from pathlib import Path
import itertools
from colorama import init, Fore, Style
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys
import hashlib
import sqlite3

# Initialize colorama
init(autoreset=True)

class ImageScraper:
    def __init__(self, api_url, save_dir, max_workers=100):
        self.api_url = api_url
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.max_workers = max_workers
        self.session = requests.Session()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Content-Type": "application/json",
            "Origin": "https://www.tmdn.org",
            "Referer": "https://www.tmdn.org/tmview/"
        }
        self.session.headers.update(self.headers)
        self.requests = self.generate_trademark_requests()
        self.nordvpn_countries = self.get_nordvpn_countries()
        self.state = self.load_state()
        self.db_path = self.save_dir / "image_index.db"
        self.init_db()
        self.index_existing_images()
        self.log(f"{Fore.GREEN}Initialized ImageScraper with {len(self.requests)} requests and {len(self.nordvpn_countries)} VPN countries")

    def log(self, message):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"{Fore.CYAN}[{timestamp}] {message}")

    def generate_trademark_requests(self):
        base_request = {
            "page": "1",
            "pageSize": "100",
            "criteria": "W",
            "basicSearch": None,
            "fOffices": ["US"],
            "fields": ["ST13", "markImageURI", "tmName", "tmOffice", "applicationNumber", "applicationDate", "tradeMarkStatus", "niceClass"]
        }

        tm_statuses = ["Filed", "Registered"]
        nice_classes = list(range(1, 46))  # 1 to 45
        tm_types = ["3-D", "Colour", "Combined", "Figurative", "Other", "Position", "Word"]

        requests = []

        for status, nice_class, tm_type in itertools.product(tm_statuses, nice_classes, tm_types):
            request = base_request.copy()
            request["fTMStatus"] = [status]
            request["fNiceClass"] = [str(nice_class)]
            request["fTMType"] = [tm_type]
            requests.append(request)

        self.log(f"{Fore.YELLOW}Generated {len(requests)} trademark requests")
        return requests

    def load_state(self):
        state_file = self.save_dir / "state.json"
        if state_file.exists():
            with open(state_file, "r") as f:
                state = json.load(f)
            self.log(f"{Fore.MAGENTA}Loaded state: current request {state['current_request_index']}, last page {state['last_page']}")
        else:
            state = {
                "current_request_index": 0,
                "last_page": 0
            }
            self.log(f"{Fore.YELLOW}No previous state found, starting fresh")
        return state

    def save_state(self):
        with open(self.save_dir / "state.json", "w") as f:
            json.dump(self.state, f)
        self.log(f"{Fore.MAGENTA}Saved state: current request {self.state['current_request_index']}, last page {self.state['last_page']}")

    def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS images (
                    id TEXT PRIMARY KEY,
                    filename TEXT UNIQUE
                )
            ''')
            conn.commit()

    def index_existing_images(self):
        self.log(f"{Fore.YELLOW}Indexing existing images...")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for image_file in self.save_dir.glob("*.jpg"):
                image_id = image_file.stem
                cursor.execute("INSERT OR IGNORE INTO images (id, filename) VALUES (?, ?)", (image_id, image_file.name))
            conn.commit()
        self.log(f"{Fore.GREEN}Finished indexing existing images")

    def is_image_downloaded(self, image_id):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM images WHERE id = ?", (image_id,))
            return cursor.fetchone() is not None

    def download_image(self, image_url, image_id):
        if self.is_image_downloaded(image_id):
            self.log(f"{Fore.YELLOW}Image already exists: {image_id}")
            return False

        response = self.session.get(image_url)
        if response.status_code == 200:
            filename = f"{image_id}.jpg"
            file_path = self.save_dir / filename
            with open(file_path, "wb") as f:
                f.write(response.content)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO images (id, filename) VALUES (?, ?)", (image_id, filename))
                conn.commit()
            
            self.log(f"{Fore.GREEN}Downloaded: {filename}")
            return True
        else:
            self.log(f"{Fore.RED}Failed to download: {image_url}, Status code: {response.status_code}")
            return False

    def get_nordvpn_countries(self):
        return [
            "Pakistan", "India", "Sri Lanka", "Bangladesh", "Nepal", "Malaysia", "Singapore",
            "Thailand", "Indonesia", "Hong Kong", "Taiwan", "Philippines", "Vietnam",
            "Kazakhstan", "Uzbekistan", "United Arab Emirates", "Oman", "Saudi Arabia", 
            "Qatar", "Bahrain", "Kuwait", "Turkey", "Israel", "Jordan", "Azerbaijan", 
            "Georgia", "Armenia", "Russia", "Ukraine", "Cyprus", "Greece", "Bulgaria", 
            "Romania", "Hungary", "Slovakia", "Czech Republic", "Poland", "Germany", 
            "Netherlands", "Belgium", "Austria", "Switzerland", "France", "Italy", 
            "Spain", "Portugal", "United Kingdom", "Ireland", "Iceland", "Norway", 
            "Sweden", "Finland", "Denmark", "Latvia", "Lithuania", "Estonia", 
            "Bosnia and Herzegovina", "Serbia", "Montenegro", "North Macedonia", 
            "Albania", "Kosovo", "Croatia", "Slovenia", "Malta", "Luxembourg", 
            "Monaco", "Andorra", "San Marino", "Liechtenstein", "United States", 
            "Canada", "Mexico", "Brazil", "Argentina", "Chile", "Colombia", 
            "Uruguay", "Paraguay", "Peru", "Bolivia", "Venezuela", "Panama", 
            "Costa Rica", "Guatemala", "El Salvador", "Honduras", "Nicaragua", 
            "Cuba", "Dominican Republic", "Jamaica", "Bahamas", "Bermuda", 
            "Trinidad and Tobago", "Barbados", "Saint Lucia", "Saint Vincent and the Grenadines", 
            "Grenada", "Antigua and Barbuda", "Dominica", "Saint Kitts and Nevis", 
            "Australia", "New Zealand", "Papua New Guinea", "Fiji", "Solomon Islands", 
            "Vanuatu", "Samoa", "Tonga", "Kiribati", "Marshall Islands", "Palau", 
            "Micronesia", "Nauru", "Tuvalu"
        ]

    def rotate_vpn(self):
        if not self.nordvpn_countries:
            self.log(f"{Fore.RED}No VPN countries available. Cannot rotate VPN connection.")
            return False

        country = random.choice(self.nordvpn_countries)
        try:
            self.log(f"{Fore.YELLOW}Rotating VPN connection to {country}")
            subprocess.run(['nordvpn', 'disconnect'], check=True)
            subprocess.run(['nordvpn', 'connect'], check=True)
            self.log(f"{Fore.GREEN}Successfully rotated VPN connection to {country}")
            return True
        except subprocess.CalledProcessError as e:
            self.log(f"{Fore.RED}Error rotating VPN connection: {e}")
            return False

    def scrape_images(self, max_pages=None):
        while self.state["current_request_index"] < len(self.requests):
            current_request = self.requests[self.state["current_request_index"]]
            current_page = self.state["last_page"] + 1

            self.log(f"{Fore.BLUE}Starting request {self.state['current_request_index'] + 1}/{len(self.requests)}: "
                     f"Status: {current_request['fTMStatus'][0]}, "
                     f"Nice Class: {current_request['fNiceClass'][0]}, "
                     f"TM Type: {current_request['fTMType'][0]}")

            while True:
                current_request["page"] = str(current_page)

                try:
                    self.log(f"{Fore.YELLOW}Fetching page {current_page} for request {self.state['current_request_index'] + 1}")
                    response = self.session.post(self.api_url, json=current_request)
                    response.raise_for_status()
                except requests.exceptions.RequestException as e:
                    self.log(f"{Fore.RED}Error fetching page {current_page} for request {self.state['current_request_index'] + 1}: {e}")
                    if self.rotate_vpn():
                        time.sleep(10)
                        continue
                    else:
                        break

                try:
                    data = response.json()
                except json.JSONDecodeError:
                    self.log(f"{Fore.RED}Error decoding JSON on page {current_page} for request {self.state['current_request_index'] + 1}")
                    if self.rotate_vpn():
                        time.sleep(10)
                        continue
                    else:
                        break

                trademarks = data.get("tradeMarks", [])

                if not trademarks:
                    self.log(f"{Fore.YELLOW}No more trademarks found for request {self.state['current_request_index'] + 1}")
                    break

                self.log(f"{Fore.GREEN}Found {len(trademarks)} trademarks on page {current_page}")

                # Use ThreadPoolExecutor to download images concurrently
                with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    futures = []
                    for tm in trademarks:
                        image_url = tm.get("detailImageURI")
                        image_id = tm['ST13']
                        if not image_url:
                            continue

                        futures.append(executor.submit(self.download_image, image_url, image_id))

                    for future in as_completed(futures):
                        future.result()

                self.state["last_page"] = current_page
                self.save_state()  # Save state after each page
                current_page += 1

                if max_pages and current_page > max_pages:
                    self.log(f"{Fore.YELLOW}Reached maximum number of pages: {max_pages}")
                    break

            self.state["current_request_index"] += 1
            self.state["last_page"] = 0
            self.save_state()  # Save state after each request

        self.log(f"{Fore.GREEN}Scraping completed")

def run_scraper():
    api_url = "https://www.tmdn.org/tmview/api/search/results"
    save_dir = "downloaded_images"
    
    scraper = ImageScraper(api_url, save_dir)
    scraper.scrape_images(max_pages=100000)

def main():
    while True:
        try:
            run_scraper()
        except Exception as e:
            print(f"{Fore.RED}An unexpected error occurred: {e}")
            print(f"{Fore.YELLOW}Restarting the scraper in 5 seconds...")
            time.sleep(5)
        else:
            print(f"{Fore.GREEN}Scraping completed successfully.")
            break

if __name__ == "__main__":
    main()
