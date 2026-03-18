# This was made by AGAJAYOFFICIAL (updated with auto‑detect stale tokens & persistent timestamp)
from flask import Flask, jsonify, request
import aiohttp
import asyncio
import json
import random
import time
import threading
import subprocess
import sys
import os
from byte import encrypt_api, Encrypt_ID
from visit_count_pb2 import Info

app = Flask(__name__)

# -------------------- Configuration --------------------
MAX_CONCURRENT = 50                # Number of simultaneous requests
RETRY_BACKOFF_BASE = 2              # Base for exponential backoff (seconds)
MAX_RETRIES = 3                      # Max retries per token on failure
TOKEN_BLACKLIST_TIME = 60            # Seconds to skip a token after repeated failures
REQUEST_DELAY = 0.1                   # Base delay between requests (seconds)
JITTER = 0.05                         # Random jitter added to delay
REFRESH_INTERVAL = 25 * 60             # 25 minutes in seconds (tokens last ~30 min)
MAX_CONSECUTIVE_ZERO_BATCHES = 5       # Stop after this many batches with zero success
LAST_REFRESH_FILE = "last_refresh.txt"  # File storing last successful refresh timestamp

# -------------------- Global state --------------------
token_failures = {}                  # token -> consecutive failure count
token_blacklisted_until = {}         # token -> timestamp until which it's skipped
is_refreshing = False                 # True while token refresh is running
refresh_lock = threading.Lock()

# -------------------- Timestamp helpers --------------------
def get_last_refresh_time():
    """Return timestamp of last successful refresh, or 0 if file missing."""
    try:
        with open(LAST_REFRESH_FILE, 'r') as f:
            return float(f.read().strip())
    except (FileNotFoundError, ValueError):
        return 0

def set_last_refresh_time(t=None):
    """Save the current (or given) timestamp to file."""
    if t is None:
        t = time.time()
    with open(LAST_REFRESH_FILE, 'w') as f:
        f.write(str(t))

# -------------------- Refresh function (synchronous) --------------------
def do_refresh():
    """Run refresh_tokens.py and update timestamp on success."""
    global is_refreshing
    with refresh_lock:
        if is_refreshing:
            print("⚠️ Refresh already in progress, skipping this cycle.")
            return
        is_refreshing = True
    try:
        print("🔄 Starting token refresh...")
        result = subprocess.run([sys.executable, "refresh_tokens.py"], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ Token refresh completed successfully.")
            set_last_refresh_time()
        else:
            print(f"❌ Token refresh failed with error:\n{result.stderr}")
    except Exception as e:
        print(f"❌ Exception during token refresh: {e}")
    finally:
        with refresh_lock:
            is_refreshing = False
        print("✅ Refresh flag cleared.")

# -------------------- Background refresh thread --------------------
def refresh_loop():
    """Periodically call do_refresh() every REFRESH_INTERVAL seconds."""
    while True:
        time.sleep(REFRESH_INTERVAL)
        do_refresh()

# -------------------- Initial check on startup --------------------
last = get_last_refresh_time()
if time.time() - last > REFRESH_INTERVAL:
    print("🚨 Tokens are stale (last refresh > 25 min ago). Refreshing now...")
    do_refresh()  # synchronous refresh before server starts
else:
    print(f"✅ Tokens are fresh (last refresh {int(time.time()-last)} seconds ago).")

# Start the background thread after initial check
refresh_thread = threading.Thread(target=refresh_loop, daemon=True)
refresh_thread.start()
print("🚀 Auto-refresh thread started (every 25 minutes)")

# -------------------- Token loading --------------------
def load_tokens(server_name):
    try:
        if server_name == "IND":
            path = "token_ind.json"
        elif server_name in {"BR", "US", "SAC", "NA"}:
            path = "token_br.json"
        else:
            path = "token_bd.json"

        with open(path, "r") as f:
            data = json.load(f)

        tokens = [item["token"] for item in data if "token" in item and item["token"] not in ["", "N/A"]]
        return tokens
    except Exception as e:
        app.logger.error(f"❌ Token load error for {server_name}: {e}")
        return []

def get_url(server_name):
    if server_name == "IND":
        return "https://client.ind.freefiremobile.com/GetPlayerPersonalShow"
    elif server_name in {"BR", "US", "SAC", "NA"}:
        return "https://client.us.freefiremobile.com/GetPlayerPersonalShow"
    else:
        return "https://clientbp.ggblueshark.com/GetPlayerPersonalShow"

def parse_protobuf_response(response_data):
    try:
        info = Info()
        info.ParseFromString(response_data)
        player_data = {
            "uid": info.AccountInfo.UID if info.AccountInfo.UID else 0,
            "nickname": info.AccountInfo.PlayerNickname if info.AccountInfo.PlayerNickname else "",
            "likes": info.AccountInfo.Likes if info.AccountInfo.Likes else 0,
            "region": info.AccountInfo.PlayerRegion if info.AccountInfo.PlayerRegion else "",
            "level": info.AccountInfo.Levels if info.AccountInfo.Levels else 0
        }
        return player_data
    except Exception as e:
        app.logger.error(f"❌ Protobuf parsing error: {e}")
        return None

def is_token_usable(token):
    """Check if token is not blacklisted."""
    if token in token_blacklisted_until:
        if time.time() < token_blacklisted_until[token]:
            return False
        else:
            del token_blacklisted_until[token]
    return True

def mark_token_failure(token):
    """Increase failure count and blacklist if too many failures."""
    global token_failures, token_blacklisted_until
    token_failures[token] = token_failures.get(token, 0) + 1
    if token_failures[token] >= MAX_RETRIES:
        token_blacklisted_until[token] = time.time() + TOKEN_BLACKLIST_TIME
        print(f"⚠️ Token {token[:8]}... blacklisted for {TOKEN_BLACKLIST_TIME}s due to repeated failures")
        token_failures[token] = 0

def mark_token_success(token):
    token_failures[token] = 0

async def visit(session, url, token, uid, data, semaphore):
    headers = {
        "ReleaseVersion": "OB52",
        "X-GA": "v1 1",
        "Authorization": f"Bearer {token}",
        "Host": url.replace("https://", "").split("/")[0]
    }

    for attempt in range(MAX_RETRIES):
        try:
            async with semaphore:
                await asyncio.sleep(REQUEST_DELAY + random.uniform(0, JITTER))
                async with session.post(url, headers=headers, data=data, ssl=False) as resp:
                    if resp.status == 200:
                        response_data = await resp.read()
                        mark_token_success(token)
                        return True, response_data
                    elif resp.status == 429:
                        wait = RETRY_BACKOFF_BASE ** attempt + random.uniform(0, 1)
                        print(f"⚠️ 429 for token {token[:8]}..., retrying in {wait:.1f}s")
                        await asyncio.sleep(wait)
                    else:
                        mark_token_failure(token)
                        return False, None
        except Exception as e:
            print(f"❌ Visit exception: {e}")
            if attempt == MAX_RETRIES - 1:
                mark_token_failure(token)
                return False, None
            await asyncio.sleep(1)
    return False, None

async def send_until_success(tokens, uid, server_name, target_success):
    url = get_url(server_name)
    connector = aiohttp.TCPConnector(limit=0)
    total_success = 0
    total_sent = 0
    first_success_response = None
    player_info = None
    consecutive_zero_batches = 0

    encrypted = encrypt_api("08" + Encrypt_ID(str(uid)) + "1801")
    data = bytes.fromhex(encrypted)
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async with aiohttp.ClientSession(connector=connector) as session:
        while total_success < target_success:
            usable_tokens = [t for t in tokens if is_token_usable(t)]
            if not usable_tokens:
                print("❌ No usable tokens left – all blacklisted.")
                break

            batch_size = min(target_success - total_success, len(usable_tokens) * 2)
            tasks = []
            for _ in range(batch_size):
                token = random.choice(usable_tokens)
                tasks.append(asyncio.create_task(visit(session, url, token, uid, data, semaphore)))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            batch_success = 0
            for res in results:
                if isinstance(res, Exception):
                    print(f"Task exception: {res}")
                    continue
                success, response = res
                if success:
                    total_success += 1
                    batch_success += 1
                    if first_success_response is None and response is not None:
                        first_success_response = response
                        player_info = parse_protobuf_response(response)

            total_sent += batch_size
            print(f"Batch sent: {batch_size}, Success in batch: {batch_success}, Total success so far: {total_success}")

            # Consecutive zero batches detection
            if batch_success == 0:
                consecutive_zero_batches += 1
                print(f"⚠️ Consecutive zero batches: {consecutive_zero_batches}")
                if consecutive_zero_batches >= MAX_CONSECUTIVE_ZERO_BATCHES:
                    raise RuntimeError(f"Stopped after {consecutive_zero_batches} consecutive batches with zero success.")
            else:
                consecutive_zero_batches = 0

    return total_success, total_sent, player_info

@app.route('/<string:server>/<int:uid>', methods=['GET'])
def send_visits(server, uid):
    # Check if token refresh is in progress
    with refresh_lock:
        if is_refreshing:
            return jsonify({"error": "Updating tokens, please try after ~2 minutes"}), 503

    server = server.upper()
    tokens = load_tokens(server)

    try:
        target_success = int(request.args.get('visit', 2000))
        if target_success <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({"error": "❌ Invalid 'visit' parameter. Must be a positive integer."}), 400

    if not tokens:
        return jsonify({"error": "❌ No valid tokens found"}), 500

    print(f"🚀 Sending {target_success} visits to UID: {uid} using {len(tokens)} tokens")
    print(f"Waiting for total {target_success} successful visits...")

    try:
        total_success, total_sent, player_info = asyncio.run(send_until_success(
            tokens, uid, server,
            target_success=target_success
        ))
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        app.logger.error(f"Unexpected error: {e}")
        return jsonify({"error": "Internal server error"}), 500

    if player_info:
        player_info_response = {
            "fail": target_success - total_success,
            "level": player_info.get("level", 0),
            "likes": player_info.get("likes", 0),
            "nickname": player_info.get("nickname", ""),
            "region": player_info.get("region", ""),
            "success": total_success,
            "uid": player_info.get("uid", 0)
        }
        return jsonify(player_info_response), 200
    else:
        return jsonify({"error": "Could not decode player information"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 25648))
    app.run(host="0.0.0.0", port=port)
