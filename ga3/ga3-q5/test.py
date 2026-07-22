import json
import numpy as np

# CHANGE THIS to the actual name of your downloaded JSON file
FILENAME = 'task5.json' 

with open(FILENAME) as f:
    data = json.load(f)

# --- AUTO-DETECT JSON STRUCTURE ---
# Scenario A: The JSON is a dict mapping IDs directly to embeddings (e.g., {"D001": [0.1, ...]})
if isinstance(data, dict) and 'documents' not in data and 'queries' not in data:
    # Check if it's the documents dict or queries dict based on length (250 vs 10)
    if len(data) == 250:
        D_ids = list(data.keys())
        D_emb = np.array(list(data.values()))
    elif len(data) == 10:
        Q_ids = list(data.keys())
        Q_emb = np.array(list(data.values()))
    else:
        print("Unexpected dictionary length:", len(data))
        exit()

# Scenario B: The JSON has 'documents' and 'queries' keys containing lists of dicts
elif isinstance(data, dict) and 'documents' in data:
    docs = data['documents']
    queries = data['queries']
    
    # Auto-find the ID and Embedding keys for documents
    sample_doc = docs[0]
    id_key = next((k for k in sample_doc.keys() if 'id' in k.lower()), None)
    emb_key = next((k for k in sample_doc.keys() if 'emb' in k.lower() or 'vec' in k.lower()), None)
    
    if not id_key or not emb_key:
        print("❌ Could not auto-detect keys. First document looks like:", sample_doc)
        exit()
        
    D_ids = [d[id_key] for d in docs]
    D_emb = np.array([d[emb_key] for d in docs])
    
    # Auto-find keys for queries
    sample_q = queries[0]
    q_id_key = next((k for k in sample_q.keys() if 'id' in k.lower()), None)
    q_emb_key = next((k for k in sample_q.keys() if 'emb' in k.lower() or 'vec' in k.lower()), None)
    
    Q_ids = [q[q_id_key] for q in queries]
    Q_emb = np.array([q[q_emb_key] for q in queries])
else:
    print("❌ Unexpected JSON structure. Top keys are:", data.keys())
    exit()

# --- COMPUTE COSINE SIMILARITY ---
# Embeddings are unit-normalized, so cosine similarity is just the dot product
sims = Q_emb @ D_emb.T 

# Extract numeric part of doc_id for tie-breaking (e.g., "D000001" -> 1)
doc_nums = np.array([int(''.join(filter(str.isdigit, d_id))) for d_id in D_ids])

result = {}
for i, q_id in enumerate(Q_ids):
    q_sims = sims[i]
    
    # np.lexsort sorts by the last key first. 
    # We want: 1st priority = similarity descending (-q_sims), 2nd priority = doc_id ascending (doc_nums)
    sorted_indices = np.lexsort((doc_nums, -q_sims))
    top5_indices = sorted_indices[:5]
    
    result[q_id] = [D_ids[idx] for idx in top5_indices]

# Print the final JSON to copy-paste into the platform
print(json.dumps(result))