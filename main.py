"""
main.py — FastMCP server entry point for the Expense Tracker.

Registers all expense tools and starts the MCP server.
"""

import os
import asyncio
from dotenv import load_dotenv
from fastmcp import FastMCP

from tools import (
    add_expense,
    list_expenses,
    smart_update_expense,
    delete_expense,
    summarize_expenses,
    reset_data,
    register_user,
    create_session_link,
    revoke_all_sessions,
)

# Load .env file for database credentials
load_dotenv()

# ── Create the MCP server ──
mcp = FastMCP(
    name="Expense Tracker online",
    instructions=(
        "You are a secure expense tracking assistant. "
        "User identification is handled automatically via secure tokens in the connection URL. "
        "1. For the OWNER: Access is permanent via the Master Key in your configuration. "
        "2. For GUESTS: Access is temporary via Session Tokens (sk_sess_...). "
        "If a user says they are 'unauthenticated' or get an error, advise them to use the `register_user` tool "
        "to create a Master Key, then update their connection URL. "
        "All data is tied to the user's email and kept strictly isolated."
    ),
)

@mcp.on_startup
async def do_startup():
    """
    Ensures the database schema is up-to-date as soon as the server boots.
    """
    from setup_db import main as setup_database
    try:
        print("🔄 Database Auto-Sync starting...")
        await setup_database()
        print("✅ Database Auto-Sync complete.")
    except Exception as e:
        print(f"⚠️ Database Auto-Sync failed: {e}")

# ── Register tools ──
mcp.tool(add_expense)
mcp.tool(list_expenses)
mcp.tool(smart_update_expense)
mcp.tool(delete_expense)
mcp.tool(summarize_expenses)
mcp.tool(reset_data)
mcp.tool(register_user)
mcp.tool(create_session_link)
mcp.tool(revoke_all_sessions)


if __name__ == "__main__":
    # Get Port from Railway
    port = int(os.environ.get("PORT", "8000"))
    
    # Run over HTTP (SSE) for cloud deployment
    print(f"🚀 Starting Expense Tracker on port {port}...")
    mcp.run(transport='sse', host='0.0.0.0', port=port)
