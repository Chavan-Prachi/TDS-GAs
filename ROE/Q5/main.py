import json
import unicodedata
from collections import defaultdict

# Load the data
data = {
  "schema": "roe-unicode-doppelganger-ledger/v1",
  "challenge_id": "udl-bfd423313e",
  # ... (using the uploaded data)
}

# Confusable map from the canonicalization spec
confusable_map = {
    '\u0430': 'a',  # Cyrillic small letter a
    '\u0432': 'b',  # Cyrillic small letter ve
    '\u0441': 'c',  # Cyrillic small letter es
    '\u0435': 'e',  # Cyrillic small letter ie
    '\u043d': 'h',  # Cyrillic small letter en
    '\u0456': 'i',  # Cyrillic small letter byelorussian-ukrainian i
    '\u0458': 'j',  # Cyrillic small letter je
    '\u043a': 'k',  # Cyrillic small letter ka
    '\u043c': 'm',  # Cyrillic small letter em
    '\u043e': 'o',  # Cyrillic small letter o
    '\u0440': 'p',  # Cyrillic small letter er
    '\u0455': 's',  # Cyrillic small letter dze
    '\u0442': 't',  # Cyrillic small letter te
    '\u0445': 'x',  # Cyrillic small letter ha
    '\u0443': 'y',  # Cyrillic small letter u
    '\u03b1': 'a',  # Greek small letter alpha
    '\u03b9': 'i',  # Greek small letter iota
    '\u03ba': 'k',  # Greek small letter kappa
    '\u03bf': 'o',  # Greek small letter omicron
    '\u03c1': 'p',  # Greek small letter rho
    '\u03c7': 'x',  # Greek small letter chi
}

# Code points to remove
remove_cps = {
    '\u00ad',  # SOFT HYPHEN
    '\u034f',  # COMBINING GRAPHEME JOINER
    '\u061c',  # ARABIC LETTER MARK
    '\u200b',  # ZERO WIDTH SPACE
    '\u200c',  # ZERO WIDTH NON-JOINER
    '\u200d',  # ZERO WIDTH JOINER
    '\u2060',  # WORD JOINER
    '\ufe0e',  # VARIATION SELECTOR-15
    '\ufe0f',  # VARIATION SELECTOR-16
    '\ufeff',  # ZERO WIDTH NO-BREAK SPACE
}

def canonicalize(text):
    """Apply the 4-step canonicalization process"""
    # Step 1: NFKC normalization
    text = unicodedata.normalize('NFKC', text)
    
    # Step 2: Lowercase (locale-independent)
    text = text.lower()
    
    # Step 3: Remove exact code points
    text = ''.join(c for c in text if c not in remove_cps)
    
    # Step 4: Apply confusable map (single pass, left-to-right)
    result = []
    for char in text:
        if char in confusable_map:
            result.append(confusable_map[char])
        else:
            result.append(char)
    
    return ''.join(result)

# Process accounts
accounts = data['accounts']
canonical_groups = defaultdict(list)

for acc in accounts:
    acc_id = acc['account_id']
    raw_handle = acc['raw_handle']
    canonical = canonicalize(raw_handle)
    canonical_groups[canonical].append((acc_id, raw_handle))

# Find suspicious accounts
suspicious_account_ids = set()
for canonical, pairs in canonical_groups.items():
    if len(pairs) >= 2:
        raw_handles = set(raw for _, raw in pairs)
        if len(raw_handles) >= 2:
            # This is a suspicious group
            for acc_id, _ in pairs:
                suspicious_account_ids.add(acc_id)

print("Suspicious accounts:", sorted(suspicious_account_ids))

# Process events
events = data['events']

# Step 1: Remove transport replays (same record_id)
seen_record_ids = set()
unique_events = []
for evt in events:
    if evt['record_id'] not in seen_record_ids:
        seen_record_ids.add(evt['record_id'])
        unique_events.append(evt)

print(f"After removing replays: {len(unique_events)} events")

# Step 2: Group by event_id, keep greatest revision, tie-break by greatest record_id
event_groups = defaultdict(list)
for evt in unique_events:
    event_groups[evt['event_id']].append(evt)

selected_events = []
for event_id, evts in event_groups.items():
    # Find max revision
    max_rev = max(evt['revision'] for evt in evts)
    # Filter to max revision
    max_rev_evts = [evt for evt in evts if evt['revision'] == max_rev]
    # Tie-break by lexicographically greatest record_id
    max_rev_evts.sort(key=lambda x: x['record_id'], reverse=True)
    selected_events.append(max_rev_evts[0])

print(f"After revision selection: {len(selected_events)} events")

# Step 3: Filter - state must be 'posted' AND account_id in suspicious set
eligible_events = [
    evt for evt in selected_events
    if evt['state'] == 'posted' and evt['account_id'] in suspicious_account_ids
]

print(f"After eligibility filter: {len(eligible_events)} events")

# Step 4: Business deduplication
# Group by (canonical account handle, canonical transfer_key)
# Keep lexicographically earliest occurred_at, tie-break by smallest event_id

def canonicalize_transfer_key(key):
    """Apply same canonicalization to transfer keys"""
    # Step 1: NFKC normalization
    key = unicodedata.normalize('NFKC', key)
    # Step 2: Lowercase
    key = key.lower()
    # Step 3: Remove exact code points
    key = ''.join(c for c in key if c not in remove_cps)
    # Step 4: Apply confusable map
    result = []
    for char in key:
        if char in confusable_map:
            result.append(confusable_map[char])
        else:
            result.append(char)
    return ''.join(result)

business_groups = defaultdict(list)
for evt in eligible_events:
    acc_id = evt['account_id']
    # Get canonical handle for this account
    raw_handle = next(acc['raw_handle'] for acc in accounts if acc['account_id'] == acc_id)
    canonical_handle = canonicalize(raw_handle)
    canonical_tkey = canonicalize_transfer_key(evt['transfer_key'])
    business_groups[(canonical_handle, canonical_tkey)].append(evt)

accepted_events = []
for key, evts in business_groups.items():
    # Sort by occurred_at (lexicographically earliest)
    evts.sort(key=lambda x: x['occurred_at'])
    min_occurred = evts[0]['occurred_at']
    # Filter to min occurred_at
    min_evts = [evt for evt in evts if evt['occurred_at'] == min_occurred]
    # Tie-break by lexicographically smallest event_id
    min_evts.sort(key=lambda x: x['event_id'])
    accepted_events.append(min_evts[0])

print(f"After business dedup: {len(accepted_events)} events")
accepted_event_ids = sorted([evt['event_id'] for evt in accepted_events])
print("Accepted event IDs:", accepted_event_ids)

# Calculate net_minor_units
net = 0
for evt in accepted_events:
    amount = int(evt['amount_minor'])
    if evt['direction'] == 'credit':
        net += amount
    else:  # debit
        net -= amount

print(f"Net minor units: {net}")

# Calculate evidence digest (FNV-1a-32)
suspicious_ids_sorted = sorted(suspicious_account_ids)
accepted_ids_sorted = sorted(accepted_event_ids)

# Create canonical evidence text
evidence_text = f"accounts={','.join(suspicious_ids_sorted)}\nevents={','.join(accepted_ids_sorted)}\nnet={net}\n"

print("Evidence text:")
print(repr(evidence_text))

# FNV-1a-32
def fnv1a_32(data):
    h = 2166136261
    for byte in data.encode('utf-8'):
        h = (h ^ byte) * 16777619 % (2**32)
    return h

hash_value = fnv1a_32(evidence_text)
digest = f"fnv1a32:{hash_value:08x}"

print(f"Evidence digest: {digest}")

# Final result
result = {
    "suspicious_account_ids": suspicious_ids_sorted,
    "accepted_event_ids": accepted_ids_sorted,
    "net_minor_units": str(net),
    "evidence_digest": digest
}

print("\nFinal result:")
print(json.dumps(result, indent=2))