"""
database.py — Connection management, date/text helpers, and category/subcategory resolvers.

Uses environment variables for PostgreSQL credentials.
Now fully asynchronous using asyncpg.
"""

import os
import re
from datetime import datetime, timedelta, date

import asyncpg
from dotenv import load_dotenv

# Load .env so DATABASE_URL is always available
load_dotenv()


# ─────────────────────────────────────────────
#  Connection
# ─────────────────────────────────────────────

async def get_connection():
    """Return a new asyncpg connection using DATABASE_URL or individual env vars."""
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return await asyncpg.connect(database_url)

    # Fallback to individual env vars
    return await asyncpg.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        database=os.getenv("DB_NAME", "railway"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
    )


# ─────────────────────────────────────────────
#  Text helpers (Synchronous)
# ─────────────────────────────────────────────

def clean_text(text: str | None) -> str | None:
    """Strip whitespace and normalise to lowercase. Returns None for empty input."""
    if text is None:
        return None
    cleaned = text.strip()
    return cleaned if cleaned else None


def normalize_date(text: str | None) -> date | None:
    """
    Convert natural-language or loose date strings to datetime.date objects.
    (asyncpg strictly requires native date/datetime objects for PostgreSQL DATE types)

    Supports:
      - "today", "yesterday", "day before yesterday"
      - Relative: "3 days ago", "1 week ago"
      - Explicit formats: YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY
    Returns None if parsing fails.
    """
    if text is None:
        return None

    text = text.strip().lower()
    today = datetime.now().date()

    if text == "today":
        return today
    if text == "yesterday":
        return today - timedelta(days=1)
    if text in ("day before yesterday", "day before"):
        return today - timedelta(days=2)

    match = re.match(r"(\d+)\s*(day|days|week|weeks)\s*ago", text)
    if match:
        n = int(match.group(1))
        unit = match.group(2)
        if unit.startswith("week"):
            n *= 7
        return today - timedelta(days=n)

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    return None


# ─────────────────────────────────────────────
#  Category / subcategory resolvers (Asynchronous)
# ─────────────────────────────────────────────

async def resolve_category(conn: asyncpg.Connection, user_id: int, name: str) -> int:
    """
    Look up a category by name for the given user.
    Auto-creates it if not found.

    Returns: category_id (int)
    """
    name_clean = clean_text(name)
    if not name_clean:
        raise ValueError("Category name cannot be empty.")

    row = await conn.fetchrow(
        "SELECT id FROM categories WHERE user_id = $1 AND LOWER(name) = LOWER($2)",
        user_id, name_clean
    )
    if row:
        return row['id']

    # Auto-create
    try:
        new_id = await conn.fetchval(
            "INSERT INTO categories (user_id, name) VALUES ($1, $2) RETURNING id",
            user_id, name_clean
        )
        return new_id
    except asyncpg.UniqueViolationError:
        # Handle race condition
        row = await conn.fetchrow(
            "SELECT id FROM categories WHERE user_id = $1 AND LOWER(name) = LOWER($2)",
            user_id, name_clean
        )
        return row['id']


async def resolve_subcategory(conn: asyncpg.Connection, user_id: int, category_id: int, name: str) -> int:
    """
    Look up a subcategory by name under the given category.
    Auto-creates it if not found.

    Returns: subcategory_id (int)
    """
    name_clean = clean_text(name)
    if not name_clean:
        raise ValueError("Subcategory name cannot be empty.")

    row = await conn.fetchrow(
        "SELECT id FROM subcategories WHERE category_id = $1 AND LOWER(name) = LOWER($2)",
        category_id, name_clean
    )
    if row:
        return row['id']

    # Auto-create
    try:
        new_id = await conn.fetchval(
            "INSERT INTO subcategories (category_id, user_id, name) VALUES ($1, $2, $3) RETURNING id",
            category_id, user_id, name_clean
        )
        return new_id
    except asyncpg.UniqueViolationError:
        # Handle race condition
        row = await conn.fetchrow(
            "SELECT id FROM subcategories WHERE category_id = $1 AND LOWER(name) = LOWER($2)",
            category_id, name_clean
        )
        return row['id']