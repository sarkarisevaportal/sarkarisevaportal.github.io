import urllib.request
import urllib.parse
import re
import os
import json
import ssl
import time
from datetime import datetime

# Certificate bypass for older State NIC servers
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

CURRENT_YEAR = str(datetime.now().year)
PREV_YEAR = str(datetime.now().year - 1)

# Authentic official job notification pages
TARGET_SOURCES = [
    {
        'id': 'JKSSB',
        'name': 'JKSSB',
        'badge': '📌 JKSSB Recruitment',
        'url': 'https://jkssb.nic.in/',
        'base': 'https://jkssb.nic.in/',
        'type': 'html'
    },
    {
        'id': 'JKPSC',
        'name': 'JKPSC',
        'badge': '🏢 JKPSC Official',
        'url': 'http://jkpsc.nic.in/',
        'base': 'http://jkpsc.nic.in/',
        'type': 'html'
    },
    {
        'id': 'UPSC',
        'name': 'UPSC',
        'badge': '🏛️ UPSC All India',
        'url': 'https://www.upsc.gov.in/whats-new',
        'base': 'https://www.upsc.gov.in/',
        'type': 'html'
    },
    {
        'id': 'JU',
        'name': 'Jammu University',
        'badge': '🎓 Jammu Univ Jobs',
        'url': 'https://www.jammuuniversity.ac.in/job-openings',
        'base': 'https://www.jammuuniversity.ac.in/',
        'type': 'html'
    },
    {
        'id': 'KU',
        'name': 'Kashmir University',
        'badge': '🎓 Kashmir Univ Recruitment',
        'url': 'https://www.kashmiruniversity.net/jobs.aspx',
        'base': 'https://www.kashmiruniversity.net/',
        'type': 'html'
    },
    {
        'id': 'KVS',
        'name': 'KVS HQ',
        'badge': '🏫 Kendriya Vidyalaya',
        'url': 'https://kvsangathan.nic.in/announcements',
        'base': 'https://kvsangathan.nic.in/',
        'type': 'html'
    },
    {
        'id': 'RRB_JAMMU',
        'name': 'RRB Jammu',
        'badge': '🚆 Railway Recruitment Board',
        'url': 'https://www.rrbjammu.nic.in/',
        'base': 'https://www.rrbjammu.nic.in/',
        'type': 'html'
    }
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9'
}

# Strict keyword matching
MANDATORY_KEYWORDS = [
    'recruitment', 'notification', 'advertisement', 'advt', 'vacancy', 'vacancies',
    'post of', 'posts of', 'selection list', 'provisional list', 'interview schedule',
    'admit card', 'examination date', 'candidature', 'answer key', 'result'
]

# Blacklist words jo menu, policy ya circular se match ho jaate hain
JUNK_PHRASES = [
    'privacy policy', 'terms of use', 'sitemap', 'tender', 'quotation', 'auction',
    'feedback', 'skip to', 'screen reader', 'contact us', 'about us', 'download app',
    'copyright', 'acts & rules', 'rti act', 'citizen charter'
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
    # Store maximum 1200 records permanently
    clean_list = list(history_set)[-1200:]
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(clean_list, f, indent=2)

def clean_title(text):
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&nbsp;|&amp;', ' ', text)
    # Remove junk prefixes
    text = re.sub(r'^(click here to view|download|view|new|notice regarding|subject:?)\s*', '', text, flags=re.I)
    return re.sub(r'\s+', ' ', text).strip()

def normalize_url(url):
    # Strip unnecessary trailing tracking parameters for dedup
    parsed = urllib.parse.urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

def is_current_notice(text, link):
    text_lower = text.lower()
    link_lower = link.lower()

    # Reject junk
    if any(junk in text_lower for junk in JUNK_PHRASES):
        return False

    # Check recruitment relevance
    has_keyword = any(k in text_lower for k in MANDATORY_KEYWORDS) or ('pdf' in link_lower and any(k in link_lower for k in ['advt', 'notif', 'rec', 'job']))
    if not has_keyword:
        return False

    # Year validation: Reject historical archives (2010 to 2023)
    old_years = [str(y) for y in range(2010, int(PREV_YEAR))]
    for y in old_years:
        if re.search(r'\b' + y + r'\b', text) or f"/{y}/" in link_lower or f"_{y}." in link_lower:
            return False

    # Must contain current/previous year OR be explicitly from current active notice board
    has_recent_year = (CURRENT_YEAR in text) or (PREV_YEAR in text) or (CURRENT_YEAR in link) or (PREV_YEAR in link)
    has_date_format = bool(re.search(r'\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4}', text))

    return has_recent_year or has_date_format

def fetch_page(url):
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=20, context=ctx) as response:
            return response.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return ""

def scrape_and_notify():
    history = load_history()
    is_initial_run = (len(history) == 0)
    new_alerts = []
    
    token = os.environ.get('BOT_TOKEN')
    channel = os.environ.get('CHANNEL_USERNAME')
    own_site = os.environ.get('OWN_SITE', 'https://sarkarisevaportal.github.io/')

    if not token or not channel:
        print("BOT_TOKEN or CHANNEL_USERNAME missing.")
        return

    for src in TARGET_SOURCES:
        html = fetch_page(src['url'])
        if not html:
            continue

        # Extract all hyperlinks
        matches = re.findall(r'<a\s+[^>]*href=[\'"]([^\'"]+)[\'"][^>]*>(.*?)</a>', html, re.I | re.S)
        board_sent_count = 0
        seen_board_urls = set()

        for raw_link, raw_content in matches:
            title = clean_title(raw_content)
            raw_link = raw_link.strip()

            if len(title) < 15 or len(title) > 280:
                continue

            if raw_link.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
                continue

            full_link = urllib.parse.urljoin(src['base'], raw_link)
            clean_link = normalize_url(full_link)

            # Avoid processing duplicate links on the same page
            if clean_link in seen_board_urls:
                continue
            seen_board_urls.add(clean_link)

            if not is_current_notice(title, full_link):
                continue

            # Unique key is the clean URL
            if clean_link not in history:
                is_pdf = full_link.lower().endswith('.pdf') or ('.pdf' in full_link.lower())
                history.add(clean_link)

                # First run protection: Fill history without spamming old posts
                if is_initial_run:
                    continue

                new_alerts.append({
                    'badge': src['badge'],
                    'title': title,
                    'link': full_link,
                    'is_pdf': is_pdf
                })

                board_sent_count += 1
                if board_sent_count >= 2:  # Maximum 2 latest updates per board per cycle
                    break

    if is_initial_run:
        print("Initial run complete: Database initialized with existing links. No spam sent.")
        save_history(history)
        return

    # Broadcast to Telegram
    for item in new_alerts:
        pdf_status = "📄 *Document:* Official PDF Available\n" if item['is_pdf'] else "🌐 *Document:* Web Notification\n"
        
        # Professional Telegram Card Layout
        message = (
            f"{item['badge']}\n"
            f"━━━━━━━━━━━━━━━━━━━\n\n"
            f"📢 *Subject:* {item['title']}\n\n"
            f"{pdf_status}"
            f"🔗 [Download / View Official Notice]({item['link']})\n\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🏛️ *All Recruitment & UT Services:*\n"
            f"👉 [{own_site}]({own_site})"
        )

        params = urllib.parse.urlencode({
            'chat_id': channel,
            'text': message,
            'parse_mode': 'Markdown',
            'disable_web_page_preview': 'false'
        })
        tg_url = f"https://api.telegram.org/bot{token}/sendMessage?{params}"

        try:
            req = urllib.request.Request(tg_url, headers=HEADERS)
            urllib.request.urlopen(req, timeout=15)
            print(f"Delivered: {item['title'][:45]}...")
            time.sleep(3)  # Telegram flood prevention delay
        except Exception as err:
            print(f"Telegram API delivery error: {err}")

    save_history(history)

if __name__ == '__main__':
    scrape_and_notify()
