# Expense Tracker MCP Server 🚀

A high-performance, multi-user expense tracking server built with **FastMCP** and **PostgreSQL**. This server acts as your personal **AI Concierge**, securely managing your finances through AI assistants like Claude with robust privacy and isolation.

## ✨ Key Features

- **🛡️ Secure Multi-User Isolation**: Every database record is cryptographically tied to a user's email, ensuring total privacy.
- **🔑 Hybrid Authentication**:
    - **Master Keys**: Permanent, high-security keys for your private vault.
    - **Session Tokens**: Temporary or **permanent** tokens for secure remote access.
- **🧠 Smart Tools**:
    - **Natural Language Dates**: Use "today", "yesterday", or "3 days ago".
    - **Dynamic Categorization**: Categories are created automatically as you spend.
    - **Visual Summaries**: Aggregate spending reports across any date range.
- **🌐 Cloud Optimized**: Fully containerized (Docker) and optimized for deployment on **Railway** via SSE transport.

---

## 👨‍💼 The AI Concierge Workflow

No complex terminals—the AI handles your security and keys for you.

### 1. Initial Setup: Registration
When you first connect, you are `unauthenticated`. To create your vault:
- **Command**: Tell the AI: `"Register me as [your-email]!"`
- **What happens**: The AI creates your vault and generates a **Master Key** (`sk_live_...`).
- **⚠️ CRITICAL**: **Copy your Master Key immediately.** It is hashed for security and cannot be shown again.

### 2. Connection Setup (Local & Remote)

#### **Local Desktop Client (Claude / Cursor)**
Add this to your `mcpServers.json` for persistent local access via **Stdio**:

```json
{
  "mcpServers": {
    "expense-tracker": {
      "command": "uv",
      "args": [
        "--directory",
        "D:/MCP_SERVER_BUILDING/REMOTE",
        "run",
        "fastmcp",
        "run",
        "main.py:mcp"
      ],
      "env": {
        "DATABASE_URL": "postgresql://user:password@localhost/db"
      }
    }
  }
}
```

#### **Remote Web Access (Claude.ai SSE)**
Access your vault securely from any device via **SSE**:

**🌐 Server URL (deployed on Railway):**
```
https://mcpremote-production.up.railway.app/sse
```

1. **First-time setup (unauthenticated)**:
   Connect with the bare SSE URL above, then tell the AI: `"Register me as [your-email]!"` to create your vault and receive a **Master Key**.

2. **Permanent connection via Master Key**:
   Go to **Settings → MCP Servers** in Claude.ai and add:
   ```
   https://mcpremote-production.up.railway.app/sse?user_id=YOUR_EMAIL&key=sk_live_...
   ```

3. **Generate a Session Token** (for sharing / guest access):
   Tell the AI: `"Create a session link for 24 hours"` or `"Create a persistent session link"` (pass `hours=0`).
   Use the returned token as:
   ```
  https://expenses-tracker-mcp.onrender.com/sse?token=sess_...
   ```

4. **Logout**: Tell the AI `"logout"` to instantly invalidate your current remote session.

---

## 🛠️ Tools Reference

| Tool | Description |
| :--- | :--- |
| `add_expense` | Log a new expense (amount, category, note, date). |
| `list_expenses` | Query history with date, category, and keyword filters. |
| `summarize_expenses` | Generate reports grouped by category/subcategory. |
| `smart_update_expense` | Modify entries with partial updates. |
| `delete_expense` | Remove an entry (requires confirmation). |
| `register_user` | Onboard a new user and generate a Master Key. |
| `create_session_link` | Generate a `sess_...` token (use `hours=0` for never-expire). |
| `logout` | Instantly invalidate the current session token. |
| `revoke_all_sessions` | Kill all active remote sessions for your account. |

## 🚀 Getting Started

### Prerequisites
- Python 3.13+ | PostgreSQL | [uv](https://github.com/astral-sh/uv)

### Installation
1. Clone the repo and sync: `uv sync`
2. Set up `.env`: `DATABASE_URL=...` and `PORT=8000`
3. Initialize: `python setup_db.py`

### Running the Server
- **Stdio (Local)**: Handled by Claude Desktop via config.
- **SSE (Remote)**: `uv run main.py` (starts SSE if `PORT` is set).

---

## 🤖 Daily Usage Examples
- *"I spent ₹500 on dinner today."*
- *"Show me my grocery expenses from last week."*
- *"Create a session link that never expires."*
- *"Logout my current session."*

---
Built with ❤️ using [FastMCP](https://github.com/jlowin/fastmcp).
