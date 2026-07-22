import hashlib
import multiprocessing

# Your personalized values
TOKEN = "1cad85187a807817"
DIFFICULTY = 28

def worker(start, step, queue):
    nonce = start
    prefix = f"{TOKEN}:".encode('utf-8')
    
    while True:
        data = prefix + str(nonce).encode('utf-8')
        h = hashlib.sha256(data).digest()
        
        # 28 leading zero bits means:
        # byte 0 == 0 (8 bits)
        # byte 1 == 0 (8 bits)
        # byte 2 == 0 (8 bits)
        # byte 3 < 16 (4 bits)
        if h[0] == 0 and h[1] == 0 and h[2] == 0 and h[3] < 16:
            queue.put(nonce)
            return
        nonce += step

if __name__ == '__main__':
    queue = multiprocessing.Queue()
    cores = multiprocessing.cpu_count()
    processes = []
    
    print(f"⛏️  Mining for token='{TOKEN}' with difficulty={DIFFICULTY}")
    print(f"⚡ Expected work: ~{2**DIFFICULTY:,} hashes")
    print(f"💻 Using {cores} CPU cores...\n")
    
    for i in range(cores):
        p = multiprocessing.Process(target=worker, args=(i, cores, queue))
        p.start()
        processes.append(p)
    
    nonce = queue.get()
    
    for p in processes:
        p.terminate()
        p.join()
    
    # Verify the result
    verify_data = f"{TOKEN}:{nonce}".encode('utf-8')
    verify_hash = hashlib.sha256(verify_data).digest()
    
    print(f"\n✅ FOUND NONCE: {nonce}")
    print(f"🔐 Hash: {verify_hash.hex()}")
    print(f"📝 Submit this nonce: {nonce}")