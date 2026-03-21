"""
tools.py — MCP tool definitions for the Expense Tracker.

Every tool requires `user_id` to enforce multi-user isolation.
Fully asynchronous using asyncpg.
"""

from fastmcp import Context
from database import (
    get_connection,
    normalize_date,
    clean_text,
    resolve_category,
    resolve_subcategory,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  0. HELPER: GET USER ID
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _normalize_params(params_raw) -> dict[str, str]:
    """Normalize query/session params into a lowercase string dict."""
    params: dict[str, str] = {}
    if not params_raw:
        return params

    try:
        items = params_raw.items() if hasattr(params_raw, "items") else []
        for key, value in items:
            clean_key = key.decode() if isinstance(key, bytes) else str(key)
            clean_value = value.decode() if isinstance(value, bytes) else str(value)
            params[clean_key.lower().strip()] = clean_value.strip()
    except Exception:
        return {}

    return params


def _identifier_from_params(params: dict[str, str]) -> int | str | None:
    """Build an auth identifier from normalized params if possible."""
    master_key = params.get("key")
    user_email = params.get("user_id") or params.get("email")
    if user_email and master_key and master_key.startswith("sk_live_"):
        return f"KEY:{user_email}:{master_key}"

    token = params.get("token")
    if token and token.startswith("sess_"):
        return f"TOKEN:{token}"

    return None


async def get_user_id(user_id: int | str | None, ctx: Context | None) -> int | str:
    """
    Resolve the user_id from arguments or session context.
    Automatically detects if we are in local (stdio) or web (sse) mode.
    """
    # 1. Identify transport
    transport = getattr(ctx, "transport", "stdio")

    # 2. Local Mode (stdio): Default to a fixed local user
    if transport == "stdio":
        return user_id if (user_id and user_id != 0) else "local_owner"

    # 3. Web Mode (sse): prefer session-scoped auth captured during initialize.
    if transport == "sse" and ctx:
        try:
            session_identifier = await ctx.get_state("auth_identifier")
            if session_identifier:
                return str(session_identifier)
        except Exception:
            pass

        # Fallback: try the current request if query params are still present.
        params_raw = {}

        if hasattr(ctx, "request_context") and ctx.request_context:
            if hasattr(ctx.request_context, "query_params"):
                params_raw = ctx.request_context.query_params
            elif hasattr(ctx.request_context, "request") and hasattr(ctx.request_context.request, "query_params"):
                params_raw = ctx.request_context.request.query_params

        if not params_raw and hasattr(ctx, "request") and ctx.request:
            if hasattr(ctx.request, "query_params"):
                params_raw = ctx.request.query_params

        if not params_raw and hasattr(ctx, "session") and ctx.session:
            params_raw = getattr(ctx.session, "metadata", {})

        identifier = _identifier_from_params(_normalize_params(params_raw))
        if identifier:
            return identifier

        return "unauthenticated"

    # 4. Local Fallback: User-provided argument directly to tool
    if user_id and user_id != 0:
        return user_id

    # 5. Default
    return "unauthenticated"


async def resolve_user_id(conn, identifier: str | int) -> int:
    """
    Map a username/string ID to a database BIGINT id.
    Automatically creates the user and seeds default categories if they don't exist.
    """
    # 1. If it's already a positive integer, use it
    try:
        if isinstance(identifier, int) or (isinstance(identifier, str) and identifier.isdigit()):
            return int(identifier)
    except (ValueError, TypeError):
        pass

    # 2. Treat as a username or token
    ident = str(identifier).strip()
    
    if ident.lower() == "unauthenticated":
        raise ValueError("❌ You are not connected to a secure vault. Please ask the AI to **register your account** or provide your Master Key/Session Token in the connection URL.")
    
    # Session Token Validation
    if ident.startswith("TOKEN:"):
        token = ident.split(":", 1)[1].strip()
        import hashlib
        sess_hash = hashlib.sha256(token.encode()).hexdigest()
        row = await conn.fetchrow(
            "SELECT user_id FROM sessions WHERE token_hash = $1 AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)",
            sess_hash
        )
        if row:
            return row['user_id']
        raise ValueError("❌ Session expired or invalid. Please generate a new connection link.")
        
    # Master Key Validation
    if ident.startswith("KEY:"):
        # Format string is "KEY:email:master_key"
        parts = ident.split(":", 2)
        if len(parts) == 3:
            _, email, key = [p.strip() for p in parts]
            import hashlib
            key_hash = hashlib.sha256(key.encode()).hexdigest()
            row = await conn.fetchrow(
                "SELECT id FROM users WHERE LOWER(email) = LOWER($1) AND api_key_hash = $2",
                email, key_hash
            )
            if row:
                return row['id']
        raise ValueError("❌ Invalid Master Key or Email.")
        
    username = ident.lower()
    if not username:
        raise ValueError("❌ Invalid user identifier.")

    # ⚠️ SECURITY: Anonymous/unprefixed identifiers are only allowed for lookup, NEVER auto-creation.
    # Users must register explicitly via the register_user tool.
    row = await conn.fetchrow("SELECT id FROM users WHERE username = $1", username)
    if row:
        return row['id']

    raise ValueError(f"❌ User '{username}' not found. Please register first or provide your Master Key.")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  0.5 SECURITY TOOLS (AI CONCIERGE)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

import secrets
import hashlib
from datetime import datetime, timedelta

def _generate_token(prefix="sk_live_"):
    return prefix + secrets.token_urlsafe(32)

def _hash_string(text):
    return hashlib.sha256(text.encode()).hexdigest()

async def register_user(email: str) -> str:
    """
    Register a new master email and generate a Master Key.
    Use this when an unauthenticated user wants to create an account.
    
    Args:
        email: The user's email address.
    """
    conn = await get_connection()
    try:
        # Check if user already has a key (Case-Insensitive)
        existing = await conn.fetchrow("SELECT api_key_hash FROM users WHERE LOWER(email) = LOWER($1)", email)
        if existing and existing['api_key_hash']:
            return f"❌ The email {email} is already registered. If you lost your key, you must manually reset it in the database."
        
        raw_key = _generate_token("sk_live_")
        hashed_key = _hash_string(raw_key)

        user_id = await conn.fetchval(
            "INSERT INTO users (username, email) VALUES ($1, $2) "
            "ON CONFLICT (username) DO UPDATE SET email = EXCLUDED.email RETURNING id",
            email.lower(), email
        )
        await conn.execute(
            "UPDATE users SET api_key_hash = $1, api_key_created_at = $2 WHERE id = $3",
            hashed_key, datetime.now(), user_id
        )
        await conn.execute("SELECT seed_default_categories($1)", user_id)
        
        return (
            f"✅ **Account Registered!**\n\n"
            f"**Your Master Key:** `{raw_key}`\n\n"
            f"⚠️ **SAVE THIS KEY NOW.** It is extremely sensitive and will never be shown to you again.\n"
            f"To connect permanently to this vault, update your connection URL to:\n"
            f"`.../sse?user_id={email}&key={raw_key}`"
        )
    except Exception as e:
        return f"❌ Failed to register: {e}"
    finally:
        await conn.close()

async def create_session_link(email: str, master_key: str, hours: int = 24) -> str:
    """
    Create a persistent/temporary session and return a connection URL.
    Use this when a registered user wants to connect from the web or share access.
    
    Args:
        email: The user's registered email.
        master_key: The user's Master Key (sk_live_...).
        hours: How many hours the session should live (default 24). Pass 0 for a non-expiring link.
    """
    conn = await get_connection()
    try:
        user = await conn.fetchrow("SELECT id, api_key_hash FROM users WHERE LOWER(email) = LOWER($1)", email)
        if not user or _hash_string(master_key) != user['api_key_hash']:
            return "❌ Invalid master key or email."

        sess_token = _generate_token("sess_")
        sess_hash = _hash_string(sess_token)
        
        # Support for non-expiring sessions (hours=0)
        expiry = None
        if hours > 0:
            expiry = datetime.now() + timedelta(hours=hours)
        
        await conn.execute(
            "INSERT INTO sessions (user_id, token_hash, expires_at) VALUES ($1, $2, $3)",
            user['id'], sess_hash, expiry
        )
        
        expiry_label = f"Expires in {hours}h" if hours > 0 else "Never Expires"
        return (
            f"✅ **Session Created** ({expiry_label})\n\n"
            f"**Your Session Token:** `{sess_token}`\n"
            f"To connect using this session, use the URL parameter:\n"
            f"`.../sse?token={sess_token}`"
        )
    except Exception as e:
        return f"❌ Failed to create session: {e}"
    finally:
        await conn.close()

async def revoke_all_sessions(email: str, master_key: str) -> str:
    """
    Revoke all active web sessions for a user, instantly severing remote access.
    
    Args:
        email: The user's registered email.
        master_key: The user's Master Key.
    """
    conn = await get_connection()
    try:
        user = await conn.fetchrow("SELECT id, api_key_hash FROM users WHERE LOWER(email) = LOWER($1)", email)
        if not user or _hash_string(master_key) != user['api_key_hash']:
            return "❌ Invalid credentials."

        res = await conn.execute("DELETE FROM sessions WHERE user_id = $1", user['id'])
        deleted_count = int(res.split(" ")[1]) if res else 0
        return f"✅ Instantly revoked {deleted_count} active sessions for {email}."
    except Exception as e:
        return f"❌ Failed to revoke sessions: {e}"
    finally:
        await conn.close()


async def logout(ctx: Context | None = None) -> str:
    """
    Instantly logout and invalidate the current session token.
    Use this when you want to terminate your current remote access.
    """
    if not ctx:
        return "❌ Logout only works in a session-aware environment (SSE)."
    
    try:
        session_identifier = await ctx.get_state("auth_identifier")
        if session_identifier and session_identifier.startswith("TOKEN:"):
            token = session_identifier.split(":", 1)[1].strip()
            import hashlib
            sess_hash = hashlib.sha256(token.encode()).hexdigest()
            
            conn = await get_connection()
            try:
                await conn.execute("DELETE FROM sessions WHERE token_hash = $1", sess_hash)
                return "✅ **Logout Successful.** This session link has been permanently invalidated."
            finally:
                await conn.close()
        
        return "❌ No active session token found to logout. (Are you connected via Master Key?)"
    except Exception as e:
        return f"❌ Failed to logout: {e}"


async def ping_server() -> str:
    """A simple tool to verify the server is online and tools are loading correctly."""
    return "✅ Server is online and tools are responsive!"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  1. ADD EXPENSE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def add_expense(
    amount: float,
    category: str,
    user_id: int | str | None = None,
    subcategory: str | None = None,
    note: str | None = None,
    date: str | None = None,
    ctx: Context | None = None,
) -> str:
    """
    Add a new expense for the user.

    Args:
        amount: Expense amount (must be > 0).
        category: Category name (auto-created if missing).
        user_id: Optional ID (overridden by URL parameter if present).
        subcategory: Optional subcategory name (auto-created if missing).
        note: Optional note / description.
        date: Date string — supports 'today', 'yesterday', '3 days ago', 'YYYY-MM-DD', etc.
        ctx: MCP Context (injected automatically).
    """
    try:
        user_id_raw = await get_user_id(user_id, ctx)
    except ValueError as e:
        return str(e)

    if amount <= 0:
        return "❌ Amount must be greater than zero."

    expense_date = normalize_date(date) if date else normalize_date("today")
    if expense_date is None:
        return f"❌ Could not parse date: '{date}'. Use formats like 'today', 'yesterday', '3 days ago', or 'YYYY-MM-DD'."

    note_clean = clean_text(note)

    conn = await get_connection()
    try:
        # Resolve identity -> database ID
        user_id = await resolve_user_id(conn, user_id_raw)

        # Resolve category → id
        category_id = await resolve_category(conn, user_id, category)

        # Resolve subcategory → id (optional)
        subcategory_id = None
        if subcategory:
            subcategory_id = await resolve_subcategory(conn, user_id, category_id, subcategory)

        # asyncpg handles transactions via execute() with single queries or explicit tx
        expense_id = await conn.fetchval(
            """
            INSERT INTO expenses (user_id, category_id, subcategory_id, amount, note, expense_date)
            VALUES ($1, $2, $3, $4, $5, $6::date)
            RETURNING id
            """,
            user_id, category_id, subcategory_id, amount, note_clean, expense_date,
        )

        sub_label = f" > {subcategory}" if subcategory else ""
        return (
            f"✅ Expense added successfully!\n"
            f"   ID: {expense_id}\n"
            f"   Amount: ₹{amount:.2f}\n"
            f"   Category: {category}{sub_label}\n"
            f"   Date: {expense_date}\n"
            f"   Note: {note_clean or '—'}"
        )
    except Exception as e:
        return f"❌ Failed to add expense: {e}"
    finally:
        await conn.close()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  2. LIST EXPENSES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def list_expenses(
    category: str | None = None,
    subcategory: str | None = None,
    user_id: int | str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    note_search: str | None = None,
    limit: int = 25,
    ctx: Context | None = None,
) -> str:
    """
    List expenses for the user with optional filters.

    Args:
        category: Filter by category name.
        subcategory: Filter by subcategory name.
        user_id: Optional ID (overridden by URL parameter if present).
        start_date: Include expenses on or after this date.
        end_date: Include expenses on or before this date.
        note_search: Search keyword within expense notes.
        limit: Maximum number of results (default 25).
        ctx: MCP Context (injected automatically).
    """
    try:
        user_id_raw = await get_user_id(user_id, ctx)
    except ValueError as e:
        return str(e)

    conn = await get_connection()
    try:
        # Resolve identity -> database ID
        user_id = await resolve_user_id(conn, user_id_raw)
        query = """
            SELECT e.id, e.amount, c.name AS category, sc.name AS subcategory,
                   e.note, e.expense_date
            FROM expenses e
            JOIN categories c ON c.id = e.category_id
            LEFT JOIN subcategories sc ON sc.id = e.subcategory_id
            WHERE e.user_id = $1
        """
        params: list = [user_id]
        param_idx = 2

        if category:
            query += f" AND LOWER(c.name) = LOWER(${param_idx})"
            params.append(category.strip())
            param_idx += 1

        if subcategory:
            query += f" AND LOWER(sc.name) = LOWER(${param_idx})"
            params.append(subcategory.strip())
            param_idx += 1

        if start_date:
            sd = normalize_date(start_date)
            if sd:
                query += f" AND e.expense_date >= ${param_idx}::date"
                params.append(sd)
                param_idx += 1
            else:
                return f"❌ Invalid start_date: '{start_date}'. Please use YYYY-MM-DD or relative terms like 'today'."

        if end_date:
            ed = normalize_date(end_date)
            if ed:
                query += f" AND e.expense_date <= ${param_idx}::date"
                params.append(ed)
                param_idx += 1
            else:
                return f"❌ Invalid end_date: '{end_date}'. Please use YYYY-MM-DD or relative terms like 'today'."

        if note_search:
            query += f" AND e.note ILIKE ${param_idx}"
            params.append(f"%{note_search.strip()}%")
            param_idx += 1

        query += f" ORDER BY e.expense_date DESC, e.id DESC LIMIT ${param_idx}"
        params.append(limit)

        rows = await conn.fetch(query, *params)

        if not rows:
            return "📭 No expenses found matching the filters."

        lines = ["📋 **Expenses**\n"]
        lines.append(f"{'ID':<6} {'Amount':>10} {'Category':<18} {'Subcategory':<18} {'Date':<12} {'Note'}")
        lines.append("─" * 85)

        for row in rows:
            eid = row['id']
            amt = float(row['amount'])
            cat = row['category']
            subcat = row['subcategory']
            dt = row['expense_date']
            nt = row['note']
            lines.append(
                f"{eid:<6} ₹{amt:>9.2f} {cat or '—':<18} {subcat or '—':<18} {str(dt):<12} {nt or '—'}"
            )

        lines.append(f"\nShowing {len(rows)} expense(s).")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Failed to list expenses: {e}"
    finally:
        await conn.close()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  3. SMART UPDATE EXPENSE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def smart_update_expense(
    expense_id: int,
    amount: float | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    user_id: int | str | None = None,
    note: str | None = None,
    date: str | None = None,
    ctx: Context | None = None,
) -> str:
    """
    Update specific fields of an existing expense. Only provided fields are changed.

    Args:
        expense_id: The ID of the expense to update.
        amount: New amount (optional).
        category: New category name (optional, auto-created if missing).
        subcategory: New subcategory name (optional, auto-created if missing).
        user_id: Optional ID (overridden by URL parameter if present).
        note: New note (optional).
        date: New date (optional).
        ctx: MCP Context (injected automatically).
    """
    try:
        user_id_raw = await get_user_id(user_id, ctx)
    except ValueError as e:
        return str(e)

    conn = await get_connection()
    try:
        # Resolve identity -> database ID
        user_id = await resolve_user_id(conn, user_id_raw)

        # Verify the expense belongs to the user
        valid_exp = await conn.fetchrow(
            "SELECT id FROM expenses WHERE id = $1 AND user_id = $2",
            expense_id, user_id
        )
        if not valid_exp:
            return f"❌ Expense #{expense_id} not found for your account."

        set_clauses: list[str] = []
        params: list = []
        updated_fields: list[str] = []
        p_idx = 1

        if amount is not None:
            if amount <= 0:
                return "❌ Amount must be greater than zero."
            set_clauses.append(f"amount = ${p_idx}")
            params.append(amount)
            updated_fields.append(f"Amount → ₹{amount:.2f}")
            p_idx += 1

        if category is not None:
            category_id = await resolve_category(conn, user_id, category)
            set_clauses.append(f"category_id = ${p_idx}")
            params.append(category_id)
            updated_fields.append(f"Category → {category}")
            p_idx += 1

            # If category changes, we MUST either update or clear the subcategory
            # to prevent trigger violations (subcategory must belong to category).
            if subcategory is not None:
                subcategory_id = await resolve_subcategory(conn, user_id, category_id, subcategory)
                set_clauses.append(f"subcategory_id = ${p_idx}")
                params.append(subcategory_id)
                updated_fields.append(f"Subcategory → {subcategory}")
                p_idx += 1
            else:
                set_clauses.append(f"subcategory_id = NULL")
                updated_fields.append("Subcategory → (Cleared due to category change)")
        elif subcategory is not None:
            existing_cat_id = await conn.fetchval(
                "SELECT category_id FROM expenses WHERE id = $1 AND user_id = $2",
                expense_id, user_id
            )
            subcategory_id = await resolve_subcategory(conn, user_id, existing_cat_id, subcategory)
            set_clauses.append(f"subcategory_id = ${p_idx}")
            params.append(subcategory_id)
            updated_fields.append(f"Subcategory → {subcategory}")
            p_idx += 1

        if note is not None:
            note_clean = clean_text(note)
            set_clauses.append(f"note = ${p_idx}")
            params.append(note_clean)
            updated_fields.append(f"Note → {note_clean or '—'}")
            p_idx += 1

        if date is not None:
            expense_date = normalize_date(date)
            if expense_date is None:
                return f"❌ Could not parse date: '{date}'."
            set_clauses.append(f"expense_date = ${p_idx}::date")
            params.append(expense_date)
            updated_fields.append(f"Date → {expense_date}")
            p_idx += 1

        if not set_clauses:
            return "⚠️ No fields provided to update."

        params.extend([expense_id, user_id])
        sql = f"UPDATE expenses SET {', '.join(set_clauses)} WHERE id = ${p_idx} AND user_id = ${p_idx + 1}"

        await conn.execute(sql, *params)

        changes = "\n   ".join(updated_fields)
        return f"✅ Expense #{expense_id} updated:\n   {changes}"
    except Exception as e:
        return f"❌ Failed to update expense: {e}"
    finally:
        await conn.close()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  4. DELETE EXPENSE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def delete_expense(
    expense_id: int,
    user_id: int | str | None = None,
    confirm: bool = False,
    ctx: Context | None = None,
) -> str:
    """
    Delete an expense by ID. Requires confirm=True for safety.

    Args:
        expense_id: The ID of the expense to delete.
        user_id: Optional ID (overridden by URL parameter if present).
        confirm: Must be True to actually delete. If False, shows expense details for review.
        ctx: MCP Context (injected automatically).
    """
    try:
        user_id_raw = await get_user_id(user_id, ctx)
    except ValueError as e:
        return str(e)

    conn = await get_connection()
    try:
        # Resolve identity -> database ID
        user_id = await resolve_user_id(conn, user_id_raw)

        row = await conn.fetchrow(
            """
            SELECT e.id, e.amount, c.name AS cat_name, sc.name AS subcat_name, e.note, e.expense_date
            FROM expenses e
            JOIN categories c ON c.id = e.category_id
            LEFT JOIN subcategories sc ON sc.id = e.subcategory_id
            WHERE e.id = $1 AND e.user_id = $2
            """,
            expense_id, user_id
        )

        if not row:
            return f"❌ Expense #{expense_id} not found for your account."

        eid = row['id']
        amt = float(row['amount'])
        cat = row['cat_name']
        subcat = row['subcat_name']
        nt = row['note']
        dt = row['expense_date']

        if not confirm:
            return (
                f"⚠️ Are you sure you want to delete this expense?\n"
                f"   ID: {eid}\n"
                f"   Amount: ₹{amt:.2f}\n"
                f"   Category: {cat}{(' > ' + subcat) if subcat else ''}\n"
                f"   Date: {dt}\n"
                f"   Note: {nt or '—'}\n\n"
                f"Call again with confirm=True to proceed."
            )

        await conn.execute(
            "DELETE FROM expenses WHERE id = $1 AND user_id = $2",
            expense_id, user_id
        )

        return f"🗑️ Expense #{eid} (₹{amt:.2f} — {cat}) has been deleted."
    except Exception as e:
        return f"❌ Failed to delete expense: {e}"
    finally:
        await conn.close()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  5. SUMMARIZE EXPENSES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def summarize_expenses(
    user_id: int | str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    group_by_subcategory: bool = False,
    ctx: Context | None = None,
) -> str:
    """
    Summarize expenses grouped by category (and optionally subcategory) for a date range.

    Args:
        user_id: Optional ID (overridden by URL parameter if present).
        start_date: Include expenses on or after this date.
        end_date: Include expenses on or before this date.
        group_by_subcategory: If True, group by category + subcategory.
        ctx: MCP Context (injected automatically).
    """
    try:
        user_id_raw = await get_user_id(user_id, ctx)
    except ValueError as e:
        return str(e)

    conn = await get_connection()
    try:
        # Resolve identity -> database ID
        user_id = await resolve_user_id(conn, user_id_raw)

        if group_by_subcategory:
            select = "c.name AS category, COALESCE(sc.name, '—') AS subcategory, SUM(e.amount) AS total, COUNT(*) AS cnt"
            group = "c.name, sc.name"
            order = "c.name, sc.name"
        else:
            select = "c.name AS category, SUM(e.amount) AS total, COUNT(*) AS cnt"
            group = "c.name"
            order = "total DESC"

        query = f"""
            SELECT {select}
            FROM expenses e
            JOIN categories c ON c.id = e.category_id
            LEFT JOIN subcategories sc ON sc.id = e.subcategory_id
            WHERE e.user_id = $1
        """
        params: list = [user_id]
        p_idx = 2

        if start_date:
            sd = normalize_date(start_date)
            if sd:
                query += f" AND e.expense_date >= ${p_idx}::date"
                params.append(sd)
                p_idx += 1
            else:
                return f"❌ Invalid start_date: '{start_date}'."

        if end_date:
            ed = normalize_date(end_date)
            if ed:
                query += f" AND e.expense_date <= ${p_idx}::date"
                params.append(ed)
                p_idx += 1
            else:
                return f"❌ Invalid end_date: '{end_date}'."

        query += f" GROUP BY {group} ORDER BY {order}"

        rows = await conn.fetch(query, *params)

        if not rows:
            return "📭 No expenses found for the given period."

        lines = ["📊 **Expense Summary**\n"]

        grand_total = 0.0
        if group_by_subcategory:
            lines.append(f"{'Category':<18} {'Subcategory':<18} {'Total':>12} {'Count':>6}")
            lines.append("─" * 58)
            for row in rows:
                cat = row['category']
                subcat = row['subcategory']
                total = float(row['total'])
                cnt = row['cnt']
                lines.append(f"{cat:<18} {subcat:<18} ₹{total:>11.2f} {cnt:>6}")
                grand_total += total
        else:
            lines.append(f"{'Category':<25} {'Total':>12} {'Count':>6}")
            lines.append("─" * 46)
            for row in rows:
                cat = row['category']
                total = float(row['total'])
                cnt = row['cnt']
                lines.append(f"{cat:<25} ₹{total:>11.2f} {cnt:>6}")
                grand_total += total

        lines.append("─" * 46)
        lines.append(f"{'GRAND TOTAL':<25} ₹{grand_total:>11.2f}")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Failed to summarize expenses: {e}"
    finally:
        await conn.close()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  6. RESET DATA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def reset_data(
    user_id: int | str | None = None,
    confirm: bool = False,
    reseed_defaults: bool = True,
    ctx: Context | None = None,
) -> str:
    """
    Delete ALL data (expenses, subcategories, categories) for a user.
    Table structure remains intact. Requires confirm=True for safety.

    Args:
        user_id: Optional ID (overridden by URL parameter if present).
        confirm: Must be True to actually reset. If False, shows a warning.
        reseed_defaults: If True, re-seeds default categories after reset.
        ctx: MCP Context (injected automatically).
    """
    try:
        user_id_raw = await get_user_id(user_id, ctx)
    except ValueError as e:
        return str(e)

    if not confirm:
        return (
            "⚠️ **WARNING**: This will permanently delete ALL your expenses, "
            "subcategories, and categories.\n\n"
            "Table structure will remain intact.\n"
            "Call again with confirm=True to proceed."
        )

    conn = await get_connection()
    try:
        # Resolve identity -> database ID
        user_id = await resolve_user_id(conn, user_id_raw)

        async with conn.transaction():
            # Delete in FK-safe order: expenses → subcategories → categories
            res_exp = await conn.execute("DELETE FROM expenses WHERE user_id = $1", user_id)
            exp_count = int(res_exp.split(" ")[1])

            res_sub = await conn.execute("DELETE FROM subcategories WHERE user_id = $1", user_id)
            subcat_count = int(res_sub.split(" ")[1])

            res_cat = await conn.execute("DELETE FROM categories WHERE user_id = $1", user_id)
            cat_count = int(res_cat.split(" ")[1])

            # Optionally re-seed default categories
            if reseed_defaults:
                await conn.execute("SELECT seed_default_categories($1)", user_id)

        msg = (
            f"🔄 Data reset complete for user {user_id}:\n"
            f"   Expenses deleted: {exp_count}\n"
            f"   Subcategories deleted: {subcat_count}\n"
            f"   Categories deleted: {cat_count}"
        )
        if reseed_defaults:
            msg += "\n   ✅ Default categories have been re-seeded."

        return msg
    except Exception as e:
        return f"❌ Failed to reset data: {e}"
    finally:
        await conn.close()
