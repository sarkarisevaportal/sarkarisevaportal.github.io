import os
import json
import time
import hashlib
import re
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import urllib.parse

CURRENT_YEAR = str(datetime.now().year)
PREV_YEAR = str(datetime.now().year - 1)

# All Major Official Recruitment Portals with exact Notification Endpoints
BOARDS_CONFIG = [
    {
        'id': 'JKSSB',
        'badge': '📌 JKSSB (J&K Services Selection)',
        'url': 'https://jkssb.nic.in/',
        'base': 'https://jkssb.nic.in/',
        'mode': 'bs4'
    },
    {
        'id': 'JKPSC',
        'badge': '🏢 JKPSC (J&K Public Service)',
        'url': 'http://jkpsc.nic.in/notifications.html',
        'base': 'http://jkpsc.nic.in/',
        'mode': 'bs4'
    },
    {
        'id': 'UPSC',
        'badge': '🏛️ UPSC All India',
        'url': 'https://www.upsc.gov.in/whats-new',
        'base': 'https://www.upsc.gov.in/',
        'mode': 'bs4'
    },
    {
        'id': 'EMRS',
        'badge': '🏫 EMRS (NESTS Recruitment)',
        'url': 'https://nests.tribal.gov.in/show_content.php?lang=1&level=1&ls_id=364&lid=148',
        'base': 'https://nests.tribal.gov.in/',
        'mode': 'bs4'
    },
    {
        'id': 'KVS',
        'badge': '🏫 KVS HQ Announcements',
        'url': 'https://kvsangathan.nic.in/announcements',
        'base': 'https://kvsangathan.nic.in/',
        'mode': 'bs4'
    },
    {
        'id': 'NVS',
        'badge': '🏫 Navodaya Vidyalaya (NVS)',
        'url': 'https://navodaya.gov.in/nvs/en/Recruitment/Notification-Vacancies/',
        'base': 'https://navodaya.gov.in/',
        'mode': 'bs4'
    },
    {
        'id': 'RRB_JAMMU',
        'badge': '🚆 RRB Jammu (Railways)',
        'url': 'https://www.rrbjammu.nic.in/',
        'base': 'https://www.rrbjammu.nic.in/',
        'mode': 'bs4'
    },
    {
        'id': 'JAMMU_UNIV',
        'badge': '🎓 University of Jammu',
        'url': 'https://www.jammuuniversity.ac.in/job-openings',
        'base': 'https://www.jammuuniversity.ac.in/',
        'mode': 'bs4'
    },
    {
        'id': 'KASHMIR_UNIV',
        'badge': '🎓 University of Kashmir',
        'url': 'https://www.kashmiruniversity.net/jobs.aspx',
        'base': 'https://www.kashmiruniversity.net/',
        'mode': 'bs4'
    }
]

SESSION_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-IN,en-GB;q=0.9,en;q=0.8',
    'Sec-Ch-Ua': '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"Windows"',
    'Upgrade-Insecure-Requests': '1'
}

RECRUIT_KEYWORDS = [
    'recruitment', 'notification', 'advertisement', 'advt', 'vacancy', 'vacancies',
    'post of', 'posts of', 'selection list', 'provisional list', 'interview schedule',
    'admit card', 'exam date', 'examination', 'candidature', 'answer key', 'result'
]

BLACKLIST_PHRASES = [
    'privacy policy', 'terms of service', 'sitemap', 'tender', 'quotation',
    'feedback', 'skip to', 'screen reader', 'contact us', 'about us', 'login', 'rti act'
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

def clean_text(raw):
    text = re.sub(r'\s+', ' ', raw)
    text = re.sub(r'^(click here to view|download|view|new|notice regarding|subject:?)\s*', '', text, flags=re.I)
    return text.strip()

def normalize_url(url):
    parsed = urllib.parse.urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

def is_valid_recruitment(title, link):
    t_low = title.lower()
    l_low = link.lower()

    if any(b in t_low for b in BLACKLIST_PHRASES):
        return False

    is_pdf = ('.pdf' in l_low)
    has_keyword = any(k in t_low for k in RECRUIT_KEYWORDS) or is_pdf
    if not has_keyword:
        return False

    # Filter out archive years (2010 to PREV_YEAR-1)
    for y in range(2010, int(PREV_YEAR)):
        sy = str(y)
        if re.search(r'\b' + sy + r'\b', title) or f"/{sy}/" in l_low or f"_{sy}." in l_low:
            return False

    return True

def scrape_board(session, cfg):
    results = []
    try:
        resp = session.get(cfg['url'], timeout=20, verify=False)
        if resp.status_code != 200:
            print(f"[{cfg['id']}] HTTP {resp.status_code}")
            return []

        soup = BeautifulSoup(resp.content, 'html.parser')
        links = soup.find_all('a', href=True)

        seen_links = set()
        for a_tag in links:
            raw_title = clean_text(a_tag.get_text())
            href = a_tag['href'].strip()

            if len(raw_title) < 12 or len(raw_title) > 300:
                continue

            if href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
                continue

            full_link = urllib.parse.urljoin(cfg['base'], href)
            clean_link = normalize_url(full_link)

            if clean_link in seen_links:
                continue
            seen_links.add(clean_link)

            if is_valid_recruitment(raw_title, full_link):
                is_pdf = ('.pdf' in full_link.lower())
                results.append({
                    'badge': cfg['badge'],
                    'title': raw_title,
                    'link': full_link,
                    'clean_link': clean_link,
                    'is_pdf': is_pdf
                })
    except Exception as e:
        print(f"[{cfg['id']}] Failed to parse: {e}")
    return results

def main():
    history = load_history()
    is_initial_run = (len(history) == 0)
    new_notices = []

    token = os.environ.get('BOT_TOKEN')
    channel = os.environ.get('CHANNEL_USERNAME')
    own_site = os.environ.get('OWN_SITE', 'https://sarkarisevaportal.github.io/')

    session = requests.Session()
    session.headers.update(SESSION_HEADERS)

    for cfg in BOARDS_CONFIG:
        print(f"Scanning {cfg['id']}...")
        notices = scrape_board(session, cfg)
        board_sent = 0

        for n in notices:
            if n['clean_link'] not in history:
                history.add(n['clean_link'])
                if is_initial_run:
                    continue

                new_notices.append(n)
                board_sent += 1
                if board_sent >= 2:  # Max 2 updates per board per run
                    break

        print(f"Done {cfg['id']}: {board_sent} new updates added.")

    if is_initial_run:
        print("Database initialized on first execution. Subsequent runs will send fresh alerts.")
        save_history(history)
        return

    # Broadcast to Telegram
    for item in new_notices:
        pdf_status = "📄 *Document:* Official PDF Notice\n" if item['is_pdf'] else "🌐 *Document:* Official Web Circular\n"

        msg = (
            f"{item['badge']}\n"
            f"━━━━━━━━━━━━━━━━━━━\n\n"
            f"📢 *Update:* {item['title']}\n\n"
            f"{pdf_status}"
            f"🔗 [Direct Official Notice / PDF]({item['link']})\n\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🏛️ *All Central & UT Portals:*\n"
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
            print(f"Failed to post to Telegram: {err}")

    save_history(history)

if __name__ == '__main__':
    # Disable insecure request warnings for NIC portals
    requests.packages.urllib3.disable_warnings()
    main()
