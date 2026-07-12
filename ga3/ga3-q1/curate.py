import subprocess
import json
import sys

def get_metadata(url):
    """Fetch YouTube metadata via yt-dlp (no download)."""
    try:
        r = subprocess.run(
            ['yt-dlp', '--dump-json', '--no-download', '--no-warnings', url],
            capture_output=True, text=True, timeout=60
        )
        return json.loads(r.stdout) if r.returncode == 0 else None
    except Exception as e:
        print(f"  [WARN] {url}: {e}")
        return None

def curate(source_urls, min_dur, max_dur, req_words, forb_words, limit):
    passed = []
    for i, url in enumerate(source_urls):
        print(f"[{i+1}/{len(source_urls)}] {url}")
        m = get_metadata(url)
        if not m:
            continue

        dur      = m.get('duration') or 0
        title    = (m.get('title') or '').lower()
        desc     = (m.get('description') or '').lower()
        udate    = m.get('upload_date') or '00000000'
        vid      = m.get('id') or ''

        # 1. Duration filter (inclusive)
        if not (min_dur <= dur <= max_dur):
            print(f"  ✗ duration {dur}s out of [{min_dur},{max_dur}]")
            continue

        # 2. Inclusion: ALL required words in (title + description)
        combined = title + ' ' + desc
        if not all(w.lower() in combined for w in req_words):
            print(f"  ✗ missing required words")
            continue

        # 3. Exclusion: ANY forbidden word in title OR description
        if any(w.lower() in title or w.lower() in desc for w in forb_words):
            print(f"  ✗ contains forbidden word")
            continue

        print(f"  ✓ dur={dur}s  date={udate}  id={vid}")
        passed.append({'url': url, 'upload_date': udate, 'id': vid})

    # 4. Sort: upload_date DESC, then id ASC
    passed.sort(key=lambda x: (-int(x['upload_date']) if x['upload_date'].isdigit() else 0, x['id']))

    # 5. Limit
    return [v['url'] for v in passed[:limit]]


# ============================================================
# 👇 PASTE YOUR TASK PARAMETERS HERE 👇
{
  "source_urls": [
    "https://www.youtube.com/watch?v=j4bhmlkpLfc",
    "https://www.youtube.com/watch?v=GfxJYp9_nJA",
    "https://www.youtube.com/watch?v=e1skexBUb1M",
    "https://www.youtube.com/watch?v=WbTOutpwPHs",
    "https://www.youtube.com/watch?v=khKv-8q7YmY",
    "https://www.youtube.com/watch?v=ve2pmm5JqmI",
    "https://www.youtube.com/watch?v=83-_3x2AjXI",
    "https://www.youtube.com/watch?v=bkpLhQd6YQM",
    "https://www.youtube.com/watch?v=GkgMTyiLtWk",
    "https://www.youtube.com/watch?v=ecZZ8CvNQ6M",
    "https://www.youtube.com/watch?v=IolxqkL7cD8",
    "https://www.youtube.com/watch?v=vutyTx7IaAI",
    "https://www.youtube.com/watch?v=tf3ezjeTpfI",
    "https://www.youtube.com/watch?v=_K_QIx1KGuA",
    "https://www.youtube.com/watch?v=XGa4onZP66Q",
    "https://www.youtube.com/watch?v=W8KRzm-HUcc",
    "https://www.youtube.com/watch?v=Vde5SH8e1OQ",
    "https://www.youtube.com/watch?v=ng2o98k983k",
    "https://www.youtube.com/watch?v=goToXTC96Co",
    "https://www.youtube.com/watch?v=UlygQI2eSdg",
    "https://www.youtube.com/watch?v=5PrZvPeUw60",
    "https://www.youtube.com/watch?v=qbLc5a9jdXo",
    "https://www.youtube.com/watch?v=HW29067qVWk",
    "https://www.youtube.com/watch?v=Oh2Dkkswy30",
    "https://www.youtube.com/watch?v=8dTpNajxaH0",
    "https://www.youtube.com/watch?v=e53tmzo-U3g"
  ],
  "min_duration_seconds": 600,
  "max_duration_seconds": 2400,
  "required_words": [
    "python"
  ],
  "forbidden_words": [
    "shorts",
    "live"
  ],
  "limit": 9
}
# ============================================================
source_urls = [
    # "https://www.youtube.com/watch?v=...",
]
min_duration_seconds = 300      # ← replace
max_duration_seconds = 2400     # ← replace
required_words     = ["python"] # ← replace
forbidden_words    = []         # ← replace
limit              = 10         # ← replace
# ============================================================

if __name__ == "__main__":
    if not source_urls:
        sys.exit("⚠️  Paste your source_urls first!")

    urls = curate(source_urls, min_duration_seconds, max_duration_seconds,
                  required_words, forbidden_words, limit)

    out = {"urls": urls}
    print("\n=== SUBMIT THIS ===")
    print(json.dumps(out, indent=2))

    with open('output.json', 'w') as f:
        json.dump(out, f, indent=2)
    print("✅ Saved to output.json")