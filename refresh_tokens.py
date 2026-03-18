#!/usr/bin/env python3
"""
Token Refresher for Free Fire Visit API
Reads accounts from converted_accounts-IND.json, obtains fresh JWT tokens,
and writes them to jwt.json and token_IND.json (format expected by app.py).
"""

import json
import time
import requests
import urllib3
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

# Suppress SSL warnings (same as original scripts)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ------------------------------------------------------------------------------
# Configuration – adjust paths and region as needed
# ------------------------------------------------------------------------------
ACCOUNT_FILE = "guests_activated-IND.json"   # Input: list of {uid, password}
OUTPUT_JWT = "jwt.json"                         # Intermediate: list of {uid, token}
OUTPUT_TOKEN = "token_ind.json"                  # Final for app.py (same format)
REGION = "IND"                                    # Must match the server in app.py

# API endpoints for the chosen region (from decoded_app.py)
ACTIVATION_REGIONS = {
    'IND': {
        'guest_url': 'https://ffmconnect.live.gop.garenanow.com/oauth/guest/token/grant',
        'major_login_url': 'https://loginbp.common.ggbluefox.com/MajorLogin',
    },
    # Add other regions if needed
}

# AES encryption key and IV (same as in decoded_app.py and byte.py)
AES_KEY = bytes([89, 103, 38, 116, 99, 37, 68, 69, 117, 104, 54, 37, 90, 99, 94, 56])
AES_IV  = bytes([54, 111, 121, 90, 68, 114, 50, 50, 69, 51, 121, 99, 104, 106, 77, 37])

# ------------------------------------------------------------------------------
# Helper functions (copied from decoded_app.py / byte.py)
# ------------------------------------------------------------------------------
def encrypt_api(plain_hex: str) -> str:
    """Encrypt hex string with AES‑CBC using the API key."""
    try:
        plain_bytes = bytes.fromhex(plain_hex)
        cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
        cipher_bytes = cipher.encrypt(pad(plain_bytes, AES.block_size))
        return cipher_bytes.hex()
    except Exception:
        return None

def parse_jwt_from_response(response_content: bytes) -> str:
    """Extract JWT token from raw MajorLogin response."""
    try:
        text = response_content.decode('utf-8', errors='ignore')
        jwt_start = text.find("eyJ")
        if jwt_start != -1:
            jwt_token = text[jwt_start:]
            # Find the end of the token (second dot + ~44 chars heuristic)
            second_dot = jwt_token.find(".", jwt_token.find(".") + 1)
            if second_dot != -1:
                jwt_token = jwt_token[:second_dot + 44]
                return jwt_token
    except:
        pass
    return None

# ------------------------------------------------------------------------------
# Core login class (simplified from the previous JWT generator)
# ------------------------------------------------------------------------------
class FreeFireLogin:
    def __init__(self, region='IND'):
        self.region = region
        self.cfg = ACTIVATION_REGIONS.get(region, ACTIVATION_REGIONS['IND'])
        self.session = requests.Session()

    def guest_token(self, uid: str, password: str):
        """Step 1: Obtain guest access_token and open_id."""
        url = self.cfg['guest_url']
        data = {
            "uid": uid,
            "password": password,
            "response_type": "token",
            "client_type": "2",
            "client_secret": "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3",
            "client_id": "100067",
        }
        try:
            resp = self.session.post(url, data=data, timeout=15, verify=False)
            if resp.status_code == 200:
                j = resp.json()
                return j.get('access_token'), j.get('open_id')
        except:
            pass
        return None, None

    def major_login(self, access_token: str, open_id: str):
        """Step 2: Perform MajorLogin and return raw response."""
        url = self.cfg['major_login_url']

        # Payload template from decoded_app.py (hex string)
        payload_template = bytes.fromhex(
            '1a13323032352d30372d33302031313a30323a3531220966726565206669726528013a07312e3132302e32422c416e64726f6964204f5320372e312e32202f204150492d323320284e32473438482f373030323530323234294a0848616e6468656c645207416e64726f69645a045749464960c00c68840772033332307a1f41524d7637205646507633204e454f4e20564d48207c2032343635207c203480019a1b8a010f416472656e6f2028544d292036343092010d4f70656e474c20455320332e319a012b476f6f676c657c31663361643662372d636562342d343934622d383730622d623164616364373230393131a2010c3139372e312e31322e313335aa0102656eb201203939366136323964626364623339363462653662363937386635643831346462ba010134c2010848616e6468656c64ea014066663930633037656239383135616633306134336234613966363031393531366530653463373033623434303932353136643064656661346365663531663261f00101ca0207416e64726f6964d2020457494649ca03203734323862323533646566633136343031386336303461316562626665626466e003daa907e803899b07f003bf0ff803ae088004999b078804daa9079004999b079804daa907c80403d204262f646174612f6170702f636f6d2e6474732e667265656669726574682d312f6c69622f61726de00401ea044832303837663631633139663537663261663465376665666630623234643964397c2f646174612f6170702f636f6d2e6474732e667265656669726574682d312f626173652e61706bf00403f804018a050233329a050a32303139313138363933b205094f70656e474c455332b805ff7fc00504e005dac901ea0507616e64726f6964f2055c4b71734854394748625876574c6668437950416c52526873626d43676542557562555551317375746d525536634e30524f3751453141486e496474385963784d614c575437636d4851322b7374745279377830663935542b6456593d8806019006019a060134a2060134'
        )

        # Replace placeholders with actual values
        OLD_OPEN_ID = b"996a629dbcdb3964be6b6978f5d814db"
        OLD_ACCESS_TOKEN = b"ff90c07eb9815af30a43b4a9f6019516e0e4c703b44092516d0defa4cef51f2a"
        payload = payload_template.replace(OLD_OPEN_ID, open_id.encode())
        payload = payload.replace(OLD_ACCESS_TOKEN, access_token.encode())

        encrypted_payload_hex = encrypt_api(payload.hex())
        if not encrypted_payload_hex:
            return None
        final_payload = bytes.fromhex(encrypted_payload_hex)

        headers = {
            'X-Unity-Version': '2018.4.11f1',
            'ReleaseVersion': 'OB52',
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-GA': 'v1 1',
            'User-Agent': 'Dalvik/2.1.0 (Linux; U; Android 7.1.2; ASUS_Z01QD Build/QKQ1.190825.002)',
            'Host': 'loginbp.ggblueshark.com',
            'Connection': 'Keep-Alive',
        }

        try:
            resp = self.session.post(url, headers=headers, data=final_payload,
                                     timeout=15, verify=False)
            if resp.status_code == 200 and len(resp.content) > 0:
                return resp.content
        except:
            pass
        return None

    def get_jwt(self, uid: str, password: str) -> str:
        """Return JWT token for the given credentials, or None."""
        access_token, open_id = self.guest_token(uid, password)
        if not access_token or not open_id:
            return None

        raw_response = self.major_login(access_token, open_id)
        if not raw_response:
            return None

        jwt = parse_jwt_from_response(raw_response)
        return jwt

# ------------------------------------------------------------------------------
# Main refresh function
# ------------------------------------------------------------------------------
def refresh_tokens(account_file: str, output_file: str, region: str):
    """
    Read accounts from account_file, obtain fresh JWT tokens,
    and write them to output_file (JSON list of {uid, token}).
    """
    # Load accounts
    try:
        with open(account_file, 'r', encoding='utf-8') as f:
            accounts = json.load(f)
    except Exception as e:
        print(f"❌ Failed to load account file: {e}")
        return

    if not isinstance(accounts, list):
        print("❌ Account file must contain a JSON list.")
        return

    print(f"Loaded {len(accounts)} accounts. Refreshing tokens...")

    login = FreeFireLogin(region=region)
    successful = []
    failed = 0

    for idx, acc in enumerate(accounts, 1):
        uid = acc.get('uid')
        password = acc.get('password')
        if not uid or not password:
            print(f"⚠️  Skipping invalid entry at index {idx}")
            continue

        print(f"[{idx}/{len(accounts)}] Processing UID {uid}...", end=' ', flush=True)
        jwt = login.get_jwt(str(uid), password)
        if jwt:
            successful.append({"uid": uid, "token": jwt})
            print("✅")
        else:
            failed += 1
            print("❌")

    print(f"\nDone. Successful: {len(successful)}, Failed: {failed}")

    # Write output file
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(successful, f, indent=4)
        print(f"✅ Saved {len(successful)} tokens to {output_file}")
    except Exception as e:
        print(f"❌ Failed to write output: {e}")

# ------------------------------------------------------------------------------
# If run as a script, refresh once (or loop if desired)
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    # Option 1: Run once
    refresh_tokens(ACCOUNT_FILE, OUTPUT_JWT, REGION)

    # Option 2: Also copy/rename to token_IND.json (if needed)
    try:
        with open(OUTPUT_JWT, 'r') as f:
            tokens = json.load(f)
        with open(OUTPUT_TOKEN, 'w') as f:
            json.dump(tokens, f, indent=4)
        print(f"✅ Also updated {OUTPUT_TOKEN}")
    except Exception as e:
        print(f"⚠️  Could not update {OUTPUT_TOKEN}: {e}")

    # If you want to run continuously every 30 minutes, uncomment the loop below:
    #
    # while True:
    #     refresh_tokens(ACCOUNT_FILE, OUTPUT_JWT, REGION)
    #     # Copy to token_IND.json
    #     try:
    #         with open(OUTPUT_JWT, 'r') as f:
    #             tokens = json.load(f)
    #         with open(OUTPUT_TOKEN, 'w') as f:
    #             json.dump(tokens, f, indent=4)
    #     except:
    #         pass
    #     print("Sleeping for 30 minutes...")
    #     time.sleep(1800)  # 30 minutes