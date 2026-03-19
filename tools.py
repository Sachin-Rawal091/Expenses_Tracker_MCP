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

def get_user_id(user_id: int | str | None, ctx: Context | None) -> int | str:
    """
    Resolve the user_id from arguments or session context.
    Prioritize the 'user_id' from URL query parameters if available.
    """
    # 1. Try to get from URL query parameters (e.g. ?user_id=alice_89)
    if ctx and hasattr(ctx, "request_context"):
        # We assume request_context is a Starlette-like Request object
        try:
            query_user = ctx.request_context.query_params.get("user_id")
            if query_user:
                return query_user
        except (AttributeError, KeyError):
            pass

    # 2. Fallback to provided argument if not 0 / None
    if user_id and user_id != 0:
        return user_id

    # 3. Last fallback: Try session_id from Context
    if ctx and ctx.session_id:
        return f"session_{ctx.session_id[:8]}"

    raise ValueError("❌ No user identity found. Please provide a user_id or use a personalized connection URL.")


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
        user_id = get_user_id(user_id, ctx)
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
        user_id = get_user_id(user_id, ctx)
    except ValueError as e:
        return str(e)
    conn = await get_connection()
    try:
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

        if end_date:
            ed = normalize_date(end_date)
            if ed:
                query += f" AND e.expense_date <= ${param_idx}::date"
                params.append(ed)
                param_idx += 1

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
        user_id = get_user_id(user_id, ctx)
    except ValueError as e:
        return str(e)

    conn = await get_connection()
    try:
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

            if subcategory is not None:
                subcategory_id = await resolve_subcategory(conn, user_id, category_id, subcategory)
                set_clauses.append(f"subcategory_id = ${p_idx}")
                params.append(subcategory_id)
                updated_fields.append(f"Subcategory → {subcategory}")
                p_idx += 1
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
        user_id = get_user_id(user_id, ctx)
    except ValueError as e:
        return str(e)

    conn = await get_connection()
    try:
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
        user_id = get_user_id(user_id, ctx)
    except ValueError as e:
        return str(e)

    conn = await get_connection()
    try:
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

        if end_date:
            ed = normalize_date(end_date)
            if ed:
                query += f" AND e.expense_date <= ${p_idx}::date"
                params.append(ed)
                p_idx += 1

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
        user_id = get_user_id(user_id, ctx)
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