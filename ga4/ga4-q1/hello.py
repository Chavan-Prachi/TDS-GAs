import json
import re
import math
from collections import Counter
import numpy as np

# ============================================================
# 1. LOAD DATA
# ============================================================
with open('documents.jsonl', 'r') as f:
    documents = [json.loads(line) for line in f]

with open('chunk_rules.json', 'r') as f:
    rules = json.load(f)

with open('chunk_embeddings.json', 'r') as f:
    chunk_embeddings_data = json.load(f)

with open('queries.json', 'r') as f:
    queries_data = json.load(f)

with open('query_embeddings.json', 'r') as f:
    query_embeddings_data = json.load(f)

# Extract rules (handle both 'size' and 'chunk_size' key names)
chunk_size = rules.get('chunk_size', rules.get('size'))
overlap    = rules['overlap']
rrf_k      = rules['rrf_k']
top_k      = rules['top_k']

print(f"Rules -> chunk_size={chunk_size}, overlap={overlap}, rrf_k={rrf_k}, top_k={top_k}")

# ============================================================
# 2. SENTENCE SPLITTING & CHUNKING
# ============================================================
def split_sentences(text):
    """Split using regex [.!?]\s+ as specified."""
    parts = re.split(r'[.!?]\s+', text)
    return [p.strip() for p in parts if p.strip()]

chunks = []  # list of (chunk_id, chunk_text)
for doc_idx, doc in enumerate(documents):
    if isinstance(doc, dict):
        text   = doc.get('text', doc.get('content', ''))
        doc_id = doc.get('id', doc_idx)
    else:
        text, doc_id = str(doc), doc_idx

    sentences = split_sentences(text)
    if not sentences:
        continue

    step = max(1, chunk_size - overlap)
    c_idx = 0
    i = 0
    while i < len(sentences):
        chunk_text = ' '.join(sentences[i:i + chunk_size])
        chunk_id   = f"doc_{doc_id}_chunk_{c_idx}"
        chunks.append((chunk_id, chunk_text))
        c_idx += 1
        i += step

print(f"Created {len(chunks)} chunks from {len(documents)} documents")

# ============================================================
# 3. BM25 IMPLEMENTATION
# ============================================================
class BM25:
    def __init__(self, corpus, k1=1.5, b=0.75):
        self.k1, self.b = k1, b
        self.n = len(corpus)
        self.tokenized = [doc.lower().split() for doc in corpus]
        self.doc_lens  = [len(d) for d in self.tokenized]
        self.avgdl     = sum(self.doc_lens) / self.n if self.n else 1

        self.df = Counter()
        for doc in self.tokenized:
            for tok in set(doc):
                self.df[tok] += 1

        self.idf = {tok: math.log((self.n - f + 0.5) / (f + 0.5) + 1)
                    for tok, f in self.df.items()}

    def score(self, query):
        tokens = query.lower().split()
        scores = np.zeros(self.n)
        for i, doc in enumerate(self.tokenized):
            tf = Counter(doc)
            dl = self.doc_lens[i]
            for tok in tokens:
                if tok in tf:
                    f   = tf[tok]
                    num = f * (self.k1 + 1)
                    den = f + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                    scores[i] += self.idf.get(tok, 0) * num / den
        return scores

bm25 = BM25([c[1] for c in chunks])

# ============================================================
# 4. PREPARE EMBEDDINGS
# ============================================================
def to_array(data, keys):
    if isinstance(data, dict):
        return np.array([data[k] for k in keys])
    return np.array(data)

chunk_embs = to_array(chunk_embeddings_data, [c[0] for c in chunks])

queries_list = queries_data if isinstance(queries_data, list) else list(queries_data.values())
query_embs   = to_array(query_embeddings_data,
                        [q.get('id', i) if isinstance(q, dict) else i
                         for i, q in enumerate(queries_list)])

def normalize(E):
    norms = np.linalg.norm(E, axis=1, keepdims=True)
    norms[norms == 0] = 1
    return E / norms

chunk_embs_n = normalize(chunk_embs)

# ============================================================
# 5. PROCESS EACH QUERY
# ============================================================
results = {}
for q_idx, query in enumerate(queries_list):
    if isinstance(query, dict):
        q_text = query.get('query', query.get('text', ''))
        q_id   = query.get('id', q_idx)
    else:
        q_text, q_id = str(query), q_idx

    # --- BM25 ranks (1-indexed) ---
    bm25_scores = bm25.score(q_text)
    order_bm25  = np.argsort(-bm25_scores)
    bm25_rank   = np.empty(len(chunks), dtype=int)
    for rank, idx in enumerate(order_bm25):
        bm25_rank[idx] = rank + 1

    # --- Cosine ranks (1-indexed) ---
    q_emb_n = normalize(query_embs[q_idx].reshape(1, -1))
    cos_sim = (chunk_embs_n @ q_emb_n.T).flatten()
    order_cos = np.argsort(-cos_sim)
    cos_rank  = np.empty(len(chunks), dtype=int)
    for rank, idx in enumerate(order_cos):
        cos_rank[idx] = rank + 1

    # --- RRF fusion ---
    rrf = 1.0 / (rrf_k + bm25_rank) + 1.0 / (rrf_k + cos_rank)

    # --- Top-K with lexicographic tie-break ---
    ranked = sorted(range(len(chunks)),
                    key=lambda i: (-rrf[i], chunks[i][0]))
    results[str(q_id)] = [chunks[i][0] for i in ranked[:top_k]]

# ============================================================
# 6. SAVE
# ============================================================
with open('results.json', 'w') as f:
    json.dump(results, f, indent=2)

print(f"✅ Saved results for {len(results)} queries → results.json")