#!/usr/bin/env python3
import base64
import json
import os
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CODEX_TOKENS_DIR = SCRIPT_DIR
OUTPUT_FILE = os.path.join(
    CODEX_TOKENS_DIR, f"import_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
)
ARCHIVE_FOLDER = datetime.now().strftime("%Y%m%d")
ARCHIVE_PATH = os.path.join(CODEX_TOKENS_DIR, ARCHIVE_FOLDER)

MODEL_WHITELIST = ["gpt-5.2", "gpt-5.2-codex"]


def decode_jwt_payload_without_verify(token: str) -> dict:
    """Decode JWT payload without verification"""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return {}
        payload = parts[1]
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += "=" * padding
        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    except Exception:
        return {}


def convert_to_sub2api_account(token: dict) -> dict:
    email = token.get("email", "")
    access_token = token.get("access_token", "")
    refresh_token = token.get("refresh_token", "")
    id_token = token.get("id_token", "")
    expired = token.get("expired", "")

    expires_at = None
    access_token_has_error = False

    if access_token:
        payload = decode_jwt_payload_without_verify(access_token)
        exp_timestamp = payload.get("exp")
        if exp_timestamp:
            expires_at = int(exp_timestamp)
    elif expired:
        try:
            dt = datetime.fromisoformat(expired.replace("+08:00", ""))
            expires_at = int(dt.timestamp())
        except Exception:
            access_token_has_error = True
    else:
        access_token_has_error = True

    credentials = {}

    if email:
        credentials["email"] = email

    if access_token:
        credentials["access_token"] = access_token

    if refresh_token:
        credentials["refresh_token"] = refresh_token

    if id_token:
        credentials["id_token"] = id_token

    account_id = token.get("account_id", "")
    if account_id:
        credentials["chatgpt_account_id"] = account_id

    if MODEL_WHITELIST:
        model_mapping = {}
        for model in MODEL_WHITELIST:
            model_mapping[model] = model
        credentials["model_mapping"] = model_mapping

    extra = {}

    if expired:
        extra["expired"] = expired

    last_refresh = token.get("last_refresh", "")
    if last_refresh:
        extra["last_refresh"] = last_refresh

    notes = f"Codex account: {email}"

    if access_token_has_error:
        notes += " [WARNING: No access_token - cannot use for API calls]"

    return {
        "name": email,
        "notes": notes,
        "platform": "openai",
        "type": "oauth",
        "credentials": credentials,
        "extra": extra,
        "proxy_key": None,
        "concurrency": 5,
        "priority": 0,
        "rate_multiplier": None,
        "expires_at": expires_at,
        "auto_pause_on_expired": True,
    }


def main():
    accounts = []
    processed_files = []
    warnings = []

    for filename in os.listdir(CODEX_TOKENS_DIR):
        if not filename.endswith(".json"):
            continue
        if filename.startswith("import_") or filename == "sub2api_codex_import.json":
            continue

        filepath = os.path.join(CODEX_TOKENS_DIR, filename)
        if os.path.isfile(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                token = json.load(f)

            email = token.get("email", filename)
            access_token = token.get("access_token", "")
            refresh_token = token.get("refresh_token", "")

            account = convert_to_sub2api_account(token)
            accounts.append(account)
            processed_files.append(filepath)

            msg = f"Processed: {filename} (email: {email})"

            if not access_token:
                warnings.append(
                    f"{filename}: NO access_token - cannot use for API calls!"
                )
                msg += " [WARNING: No access_token]"
            elif not refresh_token:
                warnings.append(
                    f"{filename}: No refresh_token - cannot auto-refresh after expiry"
                )
                msg += " [WARNING: No refresh_token]"
            else:
                msg += " [OK]"

            print(msg)

    if not accounts:
        print("No codex token files found to process.")
        return

    if warnings:
        print("\n" + "=" * 60)
        print("WARNINGS:")
        for w in warnings:
            print(f"  - {w}")
        print("=" * 60 + "\n")

    payload = {
        "type": "sub2api-data",
        "version": 1,
        "exported_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "proxies": [],
        "accounts": accounts,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"\nSuccessfully converted {len(accounts)} accounts to {OUTPUT_FILE}")

    os.makedirs(ARCHIVE_PATH, exist_ok=True)

    for filepath in processed_files:
        filename = os.path.basename(filepath)
        dest_path = os.path.join(ARCHIVE_PATH, filename)
        if os.path.exists(dest_path):
            os.remove(dest_path)
        os.rename(filepath, dest_path)
        print(f"Moved to archive: {filename} -> {ARCHIVE_FOLDER}/")

    print(f"\nDone! Archive folder: {ARCHIVE_FOLDER}")


if __name__ == "__main__":
    main()
