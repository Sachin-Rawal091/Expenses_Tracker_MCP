"""
main.py — FastMCP server entry point for the Expense Tracker.

Registers all expense tools and starts the MCP server.
"""

import os
from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_request
from fastmcp.server.middleware.middleware import Middleware

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
    ping_server,
)


class SessionAuthMiddleware(Middleware):
    """Persist auth from the initial SSE request into FastMCP session state."""

    async def on_initialize(self, context, call_next):
        ctx = context.fastmcp_context
        if ctx is not None:
            try:
                request = get_http_request()
                params = {
                    str(key).lower().strip(): str(value).strip()
                    for key, value in request.query_params.items()
                }

                master_key = params.get("key")
                user_email = params.get("user_id") or params.get("email")
                token = params.get("token")

                if user_email and master_key and master_key.startswith("sk_live_"):
                    await ctx.set_state("auth_identifier", f"KEY:{user_email}:{master_key}")
                elif token and token.startswith("sess_"):
                    await ctx.set_state("auth_identifier", f"TOKEN:{token}")
            except Exception:
                pass

        return await call_next(context)

# Load .env file for database credentials
load_dotenv()

# ── Create the MCP server ──
mcp = FastMCP(
    name="Expense Tracker online",
    instructions=(
        "You are a secure expense tracking assistant. "
        "User identification is handled automatically via secure tokens in the connection URL. "
        "1. For the OWNER: Access is permanent via the Master Key in your configuration. "
        "2. For GUESTS: Access is temporary via Session Tokens (sess_...). "
        "If a user says they are 'unauthenticated' or get an error, advise them to use the `register_user` tool "
        "to create a Master Key, then update their connection URL. "
        "All data is tied to the user's email and kept strictly isolated."
    ),
)

mcp.add_middleware(SessionAuthMiddleware())

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
mcp.tool(ping_server)


if __name__ == "__main__":
    # Get Port from Railway
    port = int(os.environ.get("PORT", "8000"))
    
    # Run over HTTP (SSE) for cloud deployment
    print(f"🚀 Starting Expense Tracker on port {port}...")
    mcp.run(transport='sse', host='0.0.0.0', port=port)
