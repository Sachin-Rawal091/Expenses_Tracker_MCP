# User Workflow Guide: The AI Concierge

Welcome to the Secure Expense Tracker. We have completely rewritten the security model to prioritize your convenience and privacy. There are **no external scripts or terminals to run anymore**. The AI acts as your personal "Concierge", securely generating the keys for you!

## 1. Initial Setup: Registration

When you first connect (or connect without a key), you are considered `unauthenticated`. 

To create your account, simply tell the AI:
**"Register me as [your-email]!"**

**What happens?**
1. The AI will instantly create your secure vault.
2. It will generate a **Master Key** (starting with `sk_live_...`).
3. It will print this Master Key into your chat *exactly once*.

**⚠️ CRITICAL STEP**:  
**Copy your Master Key immediately.** 
Because this is highly secure, the server only saves a *hash* of your key. Even if the database is hacked, no one can see it. If you lose your Master Key, you cannot log back into this exact vault!

---

## 2. Permanent Local Connection

Once you have your Master Key, you can configure your Claude Desktop or Cursor so you never have to log in again.

Simply update your `claude_desktop_config.json` (or similar file) so that the `command` includes your credentials in the connection URL:

```json
{
  "mcpServers": {
    "expense-tracker": {
      "command": "uv",
      "args": [
        "run",
        "fastmcp",
        "run",
        "main.py:mcp",
        "--port",
        "8000"
      ]
    }
  }
}
```
*Note: Depending on your exact MCP client, you pass the `user_id` and `key` differently. For standard Railway / Web environments, you use URL parameters `?user_id=youremail&key=sk_live_...`. For local stdio configs, you may just ask the AI to log you in when the chat starts.*

---

## 3. Remote Web Access (Sessions)

If you are traveling, using a different computer, or using a web-based chat interface (like Claude web) connected to your Railway server: 

You don't want to paste your permanent Master Key into a public web browser URL! Instead, you can have the AI generate a **Session Token** for you.

Simply tell the AI:
**"Create a session link for me for 24 hours."**

**What happens?**
1. The AI verifies your Master Key.
2. It generates a temporary Session Token (starting with `sess_...`).
3. It provides you a safe connection URL to use remotely:
   `https://your-app.up.railway.app/sse?token=sess_...`

**Why is this better?**
If you suspect someone saw your session URL, simply tell the AI from your Master device:
**"Revoke all my remote sessions."**
The AI will instantly kill all active web links.

---

## 4. Daily Usage 

Once connected securely (either via Master Key locally or Session Token remotely), you just use natural language:

- "I spent $5 on coffee."
- "Show me my expenses for this week."
- "What did I spend on Groceries?"

You are fully isolated from all other users. No one else can access your data.
