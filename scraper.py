import urllib.request
import urllib.parse
import re
import os
import json
import hashlib
import ssl
import time

# SSL context for portals with certificate chain issues
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

OFFICIAL_BOARDS = {
    'JKSSB': {
        'url': 'https://jkssb.nic.in/',
        'emoji': '📌',
        'label': 'JKSSB (Services Selection Board)',
        'fallback_base': 'https://jkssb.nic.in/'
    },
    'JKPSC': {
        'url': 'http://jkpsc.nic.in/',
        'emoji': '🏢',
        'label': 'JKPSC',
        'fallback_base': 'http://jkpsc.nic.in/'
    },
    'UPSC': {
        'url': 'https://www.upsc.gov.in/whats-new',
        'emoji': '🏛️',
        'label': 'UPSC What is New',
        'fallback_base': 'https://www.upsc.gov.in/'
    },
    'JammuUniv': {
        'url': 'https://www.jammuuniversity.ac.in/job-openings',
        'emoji': '🎓',
        'label': 'University of Jammu',
        'fallback_base': 'https://www.jammuuniversity.ac.in/'
    },
    'KashmirUniv': {
        'url': 'https://www.kashmiruniversity.net/jobs.aspx',
        'emoji': '🎓',
        'label': 'University of Kashmir',
        'fallback_base': 'https://www.kashmiruniversity.net/'
    },
    'KVS': {
        'url': 'https://kvsangathan.nic.in/announcements',
        'emoji': '🏫',
        'label': 'Kendriya Vidyalaya Sangathan (KVS)',
        'fallback_base': 'https://kvsangathan.nic.in/'
    },
    'RRB_Jammu': {
        'url': 'https://www.rrbjammu.nic.in/',
        'emoji': '🚆',
        'label': 'RRB Jammu',
        'fallback_base': 'https://www.rrbjammu.nic.in/'
    }
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
}

RECRUIT_KEYWORDS = [
    'recruitment', 'notification', 'advertisement', 'advt', 'vacancy', 
    'vacancies', 'post', 'apply', 'interview', 'selection list', 'admit card', 
    'exam date', 'result', 'candidature', 'answer key'
]

DB_FILE = 'sent_history.json'

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_db(history_set):
    items = list(history_set)[-800:]
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2)

def clean_text(raw):
    clean = re.sub(r'<[^>]+>', ' ', raw)
    return re.sub(r'\s+', ' ', clean).strip()

def get_hash(text, link):
    return hashlib.sha256(f"{text}_{link}".encode('utf-8')).hexdigest()

def run():
    history_hashes = load_db()
    new_items_to_send = []

    for key, conf in OFFICIAL_BOARDS.items():
        try:
            req = urllib.request.Request(conf['url'], headers=HEADERS)
            with urllib.request.urlopen(req, timeout=25, context=ctx) as resp:
                html = resp.read().decode('utf-8', errors='ignore')
        except Exception as e:
            print(f"Skipping {key}: Fetch error ({e})")
            continue

        matches = re.findall(r'<a\s+[^>]*href=[\'"]([^\'"]+)[\'"][^>]*>(.*?)</a>', html, re.I | re.S)
        found_for_board = 0

        for link, raw_title in matches:
            title = clean_text(raw_title)
            if len(title) < 12 or len(title) > 250:
                continue

            link_clean = link.strip()
            if link_clean.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
                continue

            full_link = urllib.parse.urljoin(conf['fallback_base'], link_clean)
            title_lower = title.lower()
            is_pdf = full_link.lower().endswith('.pdf')

            is_relevant = any(k in title_lower for k in RECRUIT_KEYWORDS) or is_pdf

            if not is_relevant:
                continue

            uid = get_hash(title, full_link)
            if uid not in history_hashes:
                new_items_to_send.append({
                    'emoji': conf['emoji'],
                    'label': conf['label'],
                    'title': title,
                    'link': full_link,
                    'is_pdf': is_pdf,
                    'hash': uid
                })
                history_hashes.add(uid)
                found_for_board += 1
                if found_for_board >= 2:
                    break

    token = os.environ.get('BOT_TOKEN')
    channel = os.environ.get('CHANNEL_USERNAME')
    own_site = os.environ.get('OWN_SITE')

    if not token or not channel:
        print("Missing BOT_TOKEN or CHANNEL_USERNAME environment variables.")
        return

    for item in new_items_to_send:
        pdf_badge = "📄 *Format:* Official PDF Document\n" if item['is_pdf'] else ""
        msg = (
            f"🔔 *New Official Recruitment Update*\n\n"
            f"{item['emoji']} *Board:* {item['label']}\n"
            f"📌 *Notice:* {item['title']}\n"
            f"{pdf_badge}\n"
            f"🔗 [Direct Official Notice / PDF Link]({item['link']})\n\n"
            f"🌐 Portal Directory: {own_site}"
        )
        
        params = urllib.parse.urlencode({
            'chat_id': channel,
            'text': msg,
            'parse_mode': 'Markdown',
            'disable_web_page_preview': 'false'
        })
        tg_url = f"https://api.telegram.org/bot{token}/sendMessage?{params}"

        try:
            req = urllib.request.Request(tg_url, headers=HEADERS)
            urllib.request.urlopen(req, timeout=15)
            print(f"Sent update: {item['title'][:40]}...")
            time.sleep(2)
        except Exception as err:
            print(f"Failed to post telegram msg: {err}")

    save_db(history_hashes)

if __name__ == '__main__':
    run()
