import os
import json
import time
import re
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import urllib.parse
import urllib3

# State NIC portals often have unverified SSL certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CURRENT_YEAR = str(datetime.now().year)
PREV_YEAR = str(datetime.now().year - 1)
ALLOWED_YEARS = [CURRENT_YEAR, PREV_YEAR]

TARGET_CONFIGS = [
    {
        'id': 'JKSSB',
        'badge': '📌 JKSSB (J&K Services Selection Board)',
        'url': 'https://jkssb.nic.in/',
        'base': 'https://jkssb.nic.in/'
    },
    {
        'id': 'JKPSC',
        'badge': '🏢 JKPSC (J&K Public Service Commission)',
        'url': 'http://jkpsc.nic.in/notifications.html',
        'base': 'http://jkpsc.nic.in/'
    },
    {
        'id': 'UPSC',
        'badge': '🏛️ UPSC (Union Public Service Commission)',
        'url': 'https://www.upsc.gov.in/whats-new',
        'base': 'https://www.upsc.gov.in/'
    },
    {
        'id': 'EMRS',
        'badge': '🏫 EMRS (National Education Society for Tribal Students)',
        'url': 'https://nests.tribal.gov.in/show_content.php?lang=1&level=1&ls_id=364&lid=148',
        'base': 'https://nests.tribal.gov.in/'
    },
    {
        'id': 'KVS',
        'badge': '🏫 Kendriya Vidyalaya Sangathan (KVS)',
        'url': 'https://kvsangathan.nic.in/announcements',
        'base': 'https://kvsangathan.nic.in/'
    },
    {
        'id': 'NVS',
        'badge': '🏫 Navodaya Vidyalaya Samiti (NVS)',
        'url': 'https://navodaya.gov.in/nvs/en/Recruitment/Notification-Vacancies/',
        'base': 'https://navodaya.gov.in/'
    },
    {
        'id': 'RRB_JAMMU',
        'badge': '🚆 RRB Jammu & Srinagar',
        'url': 'https://www.rrbjammu.nic.in/',
        'base': 'https://www.rrbjammu.nic.in/'
    },
    {
        'id': 'JAMMU_UNIV',
        'badge': '🎓 University of Jammu',
        'url': 'https://www.jammuuniversity.ac.in/job-openings',
        'base': 'https://www.jammuuniversity.ac.in/'
    },
    {
        'id': 'KASHMIR_UNIV',
        'badge': '🎓 University of Kashmir',
        'url': 'https://www.kashmiruniversity.net/jobs.aspx',
        'base': 'https://www.kashmiruniversity.net/'
    }
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-IN,en;q=0.9',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache'
}

RECRUIT_KEYWORDS = [
    'recruitment', 'notification', 'advertisement', 'advt', 'vacancy', 'vacancies',
    'post of', 'posts of', 'selection list', 'provisional', 'interview',
    'admit card', 'exam', 'candidature', 'answer key', 'result', 'counselling'
]

BLACKLIST = [
    'privacy policy', 'terms of use', 'sitemap', 'tender', 'quotation', 'auction',
    'feedback', 'skip to', 'screen reader', 'contact us', 'about us', 'login', 'rti',
    'citizen charter', 'acts & rules', 'transfer', 'posting'
]

DB_FILE = 'sent_history.json'

def load_history():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_history(history_set):
    records = list(history_set)[-1500:]
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(records, f, indent=2)

def clean_title(raw):
    text = re.sub(r'\s+', ' ', raw)
    text = re.sub(r'^(click here to view|download|view|new|notice regarding|subject:?)\s*', '', text, flags=re.I)
    return text.strip()

def normalize_url(url):
    parsed = urllib.parse.urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

def is_strictly_current_notice(title, link):
    t_low = title.lower()
    l_low = link.lower()

    # Reject junk / static links
    if any(b in t_low for b in BLACKLIST):
        return False

    # Block any notice with historical years (2010 to 2024)
    for y in range(2010, int(PREV_YEAR)):
        sy = str(y)
        if re.search(r'\b' + sy + r'\b', title) or f"/{sy}/" in l_low or f"_{sy}." in l_low:
            return False

    # Recruitment relevance test
    has_recruit_keyword = any(k in t_low for k in RECRUIT_KEYWORDS)
    is_pdf = ('.pdf' in l_low)

    if not (has_recruit_keyword or is_pdf):
        return False

    # Strict Year/Date Whitelist: Must contain 2025/2026 or a standard date format
    has_allowed_year = any(y in title for y in ALLOWED_YEARS) or any(y in link for y in ALLOWED_YEARS)
    has_date_stamp = bool(re.search(r'\b\d{1,2}[-/\.]\d{1,2}[-/\.](20)?(25|26)\b', title))

    return has_allowed_year or has_date_stamp

def parse_page(session, cfg):
    results = []
    try:
        resp = session.get(cfg['url'], timeout=20, verify=False)
        if resp.status_code != 200:
            print(f"[{cfg['id']}] HTTP Status: {resp.status_code}")
            return []

        soup = BeautifulSoup(resp.content, 'html.parser')
        
        # Scrape all anchor tags
        anchors = soup.find_all('a', href=True)
        seen_urls = set()

        for a in anchors:
            text = clean_title(a.get_text())
            href = a['href'].strip()

            # Some sites keep notice text in 'title' or 'alt' attributes
            if len(text) < 10:
                text = clean_title(a.get('title', '') or a.get('aria-label', ''))

            if len(text) < 12 or len(text) > 280:
                continue

            if href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
                continue

            full_link = urllib.parse.urljoin(cfg['base'], href)
            clean_link = normalize_url(full_link)

            if clean_link in seen_urls:
                continue
            seen_urls.add(clean_link)

            if is_strictly_current_notice(text, full_link):
                is_pdf = ('.pdf' in full_link.lower())
                results.append({
                    'badge': cfg['badge'],
                    'title': text,
                    'link': full_link,
                    'clean_link': clean_link,
                    'is_pdf': is_pdf
                })
    except Exception as e:
        print(f"[{cfg['id']}] Error: {e}")
    return results

def main():
    history = load_history()
    is_initial_run = (len(history) == 0)
    alerts_to_send = []

    token = os.environ.get('BOT_TOKEN')
    channel = os.environ.get('CHANNEL_USERNAME')
    own_site = os.environ.get('OWN_SITE', 'https://sarkarisevaportal.github.io/')

    if not token or not channel:
        print("Missing BOT_TOKEN or CHANNEL_USERNAME.")
        return

    session = requests.Session()
    session.headers.update(HEADERS)

    for cfg in TARGET_CONFIGS:
        print(f"Checking {cfg['id']}...")
        notices = parse_page(session, cfg)
        board_sent = 0

        for item in notices:
            if item['clean_link'] not in history:
                history.add(item['clean_link'])
                
                # First run builds baseline cache to avoid blasting 50 historic notices at once
                if is_initial_run:
                    continue

                alerts_to_send.append(item)
                board_sent += 1
                if board_sent >= 2: # Max 2 newest alerts per board per check
                    break

        print(f"[{cfg['id']}] Found {len(notices)} valid notices, {board_sent} queued.")

    if is_initial_run:
        print("Initial run complete: Database populated. Next runs will trigger real fresh alerts.")
        save_history(history)
        return

    # Broadcast to Telegram
    for item in alerts_to_send:
        pdf_badge = "📄 *Document:* Official PDF Notice\n" if item['is_pdf'] else "🌐 *Document:* Official Web Circular\n"

        msg = (
            f"{item['badge']}\n"
            f"━━━━━━━━━━━━━━━━━━━\n\n"
            f"📢 *Notification:* {item['title']}\n\n"
            f"{pdf_badge}"
            f"🔗 [Direct Official Notice / PDF]({item['link']})\n\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🏛️ *Sarkari Seva Portal (All UT & Central Services):*\n"
            f"👉 [{own_site}]({own_site})"
        )

        params = urllib.parse.urlencode({
            'chat_id': channel,
            'text': msg,
            'parse_mode': 'Markdown',
            'disable_web_page_preview': 'false'
        })
        tg_url = f"https://api.telegram.org/bot{token}/sendMessage?{params}"

        try:
            r = session.get(tg_url, timeout=15)
            if r.status_code == 200:
                print(f"Sent: {item['title'][:40]}...")
            time.sleep(3)
        except Exception as err:
            print(f"Telegram dispatch error: {err}")

    save_history(history)

if __name__ == '__main__':
    main()
