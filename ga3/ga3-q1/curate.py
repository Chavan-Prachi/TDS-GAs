import subprocess
import json
import sys
import datetime

def get_metadata(url):
    """Fetch YouTube metadata via yt-dlp (no download)."""
    try:
        # Use sys.executable to call yt-dlp as a module (bypasses Windows PATH issues)
        r = subprocess.run(
            [sys.executable, '-m', 'yt_dlp', '--dump-json', '--no-download', '--no-warnings', url],
            capture_output=True, text=True, timeout=60
        )
        if r.returncode != 0:
            return None
        return json.loads(r.stdout)
    except Exception:
        return None

def curate(source_urls, min_dur, max_dur, req_words, forb_words, limit):
    passed = []
    for i, url in enumerate(source_urls):
        print(f"Processing [{i+1}/{len(source_urls)}] {url}...")
        m = get_metadata(url)
        if not m:
            print("  ✗ Failed to fetch metadata")
            continue

        dur = m.get('duration') or 0
        title = (m.get('title') or '').lower()
        desc = (m.get('description') or '').lower()
        
        # Extract video ID safely
        vid = m.get('id')
        if not vid:
            if 'v=' in url: vid = url.split('v=')[-1].split('&')[0]
            elif 'youtu.be/' in url: vid = url.split('youtu.be/')[-1].split('?')[0]
            else: continue

        # ROBUST DATE EXTRACTION: Fallback to timestamp if upload_date is missing
        udate = str(m.get('upload_date') or '').replace('-', '')
        if not udate.isdigit() and m.get('timestamp'):
            udate = datetime.datetime.utcfromtimestamp(m['timestamp']).strftime('%Y%m%d')
        if not udate.isdigit():
            udate = '00000000'

        # 1. Duration filter (inclusive)
        if not (min_dur <= dur <= max_dur):
            continue

        # 2. Inclusion: ALL required words in (title + description)
        combined = title + ' ' + desc
        if not all(w.lower() in combined for w in req_words):
            continue

        # 3. Exclusion: ANY forbidden word in title OR description
        if any(w.lower() in title or w.lower() in desc for w in forb_words):
            continue

        # NORMALIZE URL: Autograder expects strictly this format
        norm_url = f"https://www.youtube.com/watch?v={vid}"
        
        passed.append({'url': norm_url, 'upload_date': udate, 'id': vid})

    # 4. SORTING: Date DESC (newest first), then ID ASC (alphabetical, case-insensitive)
    passed.sort(key=lambda x: (-int(x['upload_date']), x['id'].lower()))

    print(f"\n=== SORTED LIST (Top {limit}) ===")
    for v in passed[:limit]:
        print(f"{v['upload_date']} | {v['id']} | {v['url']}")

    # 5. Limit
    return [v['url'] for v in passed[:limit]]

# ============================================================
# 👇 YOUR TASK PARAMETERS 👇
# ============================================================
source_urls = [
    "https://www.youtube.com/watch?v=j4bhmlkpLfc", "https://www.youtube.com/watch?v=GfxJYp9_nJA",
    "https://www.youtube.com/watch?v=e1skexBUb1M", "https://www.youtube.com/watch?v=WbTOutpwPHs",
    "https://www.youtube.com/watch?v=khKv-8q7YmY", "https://www.youtube.com/watch?v=ve2pmm5JqmI",
    "https://www.youtube.com/watch?v=83-_3x2AjXI", "https://www.youtube.com/watch?v=bkpLhQd6YQM",
    "https://www.youtube.com/watch?v=GkgMTyiLtWk", "https://www.youtube.com/watch?v=ecZZ8CvNQ6M",
    "https://www.youtube.com/watch?v=IolxqkL7cD8", "https://www.youtube.com/watch?v=vutyTx7IaAI",
    "https://www.youtube.com/watch?v=tf3ezjeTpfI", "https://www.youtube.com/watch?v=_K_QIx1KGuA",
    "https://www.youtube.com/watch?v=XGa4onZP66Q", "https://www.youtube.com/watch?v=W8KRzm-HUcc",
    "https://www.youtube.com/watch?v=Vde5SH8e1OQ", "https://www.youtube.com/watch?v=ng2o98k983k",
    "https://www.youtube.com/watch?v=goToXTC96Co", "https://www.youtube.com/watch?v=UlygQI2eSdg",
    "https://www.youtube.com/watch?v=5PrZvPeUw60", "https://www.youtube.com/watch?v=qbLc5a9jdXo",
    "https://www.youtube.com/watch?v=HW29067qVWk", "https://www.youtube.com/watch?v=Oh2Dkkswy30",
    "https://www.youtube.com/watch?v=8dTpNajxaH0", "https://www.youtube.com/watch?v=e53tmzo-U3g"
]
min_duration_seconds = 600
max_duration_seconds = 2400
required_words = ["python"]
forbidden_words = ["shorts", "live"]
limit = 9
# ============================================================

if __name__ == "__main__":
    urls = curate(source_urls, min_duration_seconds, max_duration_seconds,
                  required_words, forbidden_words, limit)

    out = {"urls": urls}
    print("\n=== COPY AND SUBMIT THIS JSON ===")
    print(json.dumps(out, indent=2))

    with open('output.json', 'w') as f:
        json.dump(out, f, indent=2)
    print("✅ Saved to output.json")