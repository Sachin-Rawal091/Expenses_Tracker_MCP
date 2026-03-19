"""
main.py — FastMCP server entry point for the Expense Tracker.

Registers all expense tools and starts the MCP server.
"""

import os
from dotenv import load_dotenv
from fastmcp import FastMCP

from tools import (
    add_expense,
    list_expenses,
    smart_update_expense,
    delete_expense,
    summarize_expenses,
    reset_data,
)

# Load .env file for database credentials
load_dotenv()

# ── Create the MCP server ──
mcp = FastMCP(
    name="Expense Tracker online",
    instructions=(
        "You are an expense tracking assistant. "
        "Help users manage their personal expenses using the available tools. "
        "Always require a user_id for every operation. "
        "Categories and subcategories are resolved automatically from names. "
        "Dates support natural language like 'today', 'yesterday', '3 days ago'."
    ),
)

# ── Register tools ──
mcp.tool(add_expense)
mcp.tool(list_expenses)
mcp.tool(smart_update_expense)
mcp.tool(delete_expense)
mcp.tool(summarize_expenses)
mcp.tool(reset_data)


if __name__ == "__main__":
    # Run over HTTP (SSE) for cloud deployment
    # Railway passes the required port dynamically via the PORT environment variable
    port = int(os.environ.get("PORT", "8000"))
    mcp.run(transport='sse', host='0.0.0.0', port=port)
