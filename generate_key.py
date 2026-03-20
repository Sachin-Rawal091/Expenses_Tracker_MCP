import argparse
import asyncio
import hashlib
import os
import secrets
from datetime import datetime, timedelta

import asyncpg
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")


def generate_token(prefix="sk_live_"):
    return prefix + secrets.token_urlsafe(32)


def hash_string(text):
    return hashlib.sha256(text.encode()).hexdigest()


async def register_master(email):
    raw_key = generate_token("sk_live_")
    hashed_key = hash_string(raw_key)

    conn = await asyncpg.connect(DATABASE_URL)
    user_id = await conn.fetchval(
        "INSERT INTO users (username, email) VALUES ($1, $1) "
        "ON CONFLICT (username) DO UPDATE SET email = EXCLUDED.email RETURNING id",
        email,
    )
    await conn.execute(
        "UPDATE users SET api_key_hash = $1, api_key_created_at = $2 WHERE id = $3",
        hashed_key,
        datetime.now(),
        user_id,
    )
    await conn.execute("SELECT seed_default_categories($1)", user_id)
    await conn.close()

    print(f"\nAccount registered for {email}")
    print(f"Master key: {raw_key}")
    print("\nSave this key now. It will not be shown again.")
    print(f"Connection URL: ?user_id={email}&key={raw_key}")


async def create_session(email, master_key, hours=None, device="Unknown"):
    conn = await asyncpg.connect(DATABASE_URL)
    user = await conn.fetchrow("SELECT id, api_key_hash FROM users WHERE email = $1", email)

    if not user or hash_string(master_key) != user["api_key_hash"]:
        print("Invalid master key or email.")
        await conn.close()
        return

    if hours is None or hours <= 0:
        print("Session duration must be at least 1 hour.")
        await conn.close()
        return

    sess_token = generate_token("sess_")
    sess_hash = hash_string(sess_token)
    expiry = datetime.now() + timedelta(hours=hours)

    await conn.execute(
        "INSERT INTO sessions (user_id, token_hash, expires_at, device_name) VALUES ($1, $2, $3, $4)",
        user["id"],
        sess_hash,
        expiry,
        device,
    )
    await conn.close()

    print(f"\nSession token created (expires in {hours}h)")
    print(f"Token: {sess_token}")
    print(f"Connection URL: ?token={sess_token}")


async def revoke_sessions(email, master_key):
    conn = await asyncpg.connect(DATABASE_URL)
    user = await conn.fetchrow("SELECT id, api_key_hash FROM users WHERE email = $1", email)
    if not user or hash_string(master_key) != user["api_key_hash"]:
        print("Invalid credentials.")
        await conn.close()
        return

    await conn.execute("DELETE FROM sessions WHERE user_id = $1", user["id"])
    await conn.close()
    print(f"All active sessions revoked for {email}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Expense Tracker Security CLI")
    parser.add_argument("--register", help="Register a new master email")
    parser.add_argument("--session", action="store_true", help="Create a temporary session")
    parser.add_argument("--revoke", action="store_true", help="Revoke all sessions")
    parser.add_argument("--email", help="User email")
    parser.add_argument("--key", help="Master key")
    parser.add_argument("--hours", type=int, help="Session duration in hours")

    args = parser.parse_args()

    if args.register:
        asyncio.run(register_master(args.register))
    elif args.session:
        if not args.email or not args.key:
            print("Email and master key are required to create a session.")
        else:
            asyncio.run(create_session(args.email, args.key, args.hours))
    elif args.revoke:
        if not args.email or not args.key:
            print("Email and master key are required.")
        else:
            asyncio.run(revoke_sessions(args.email, args.key))
    else:
        parser.print_help()
