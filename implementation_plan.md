# Implementation Plan: Secure Multi-User Identification

This plan outlines the move from a simple session-based system to a professional **Master Key + Session Token** architecture. This ensures that data is permanent, private, and secure across both local and web-based MCP clients.

## High-Level Architecture

1. **User Identity**: Every user is identified by their unique **Email Address**.
2. **Master Key**: A permanent, high-security key (e.g., `sk_live_...`) generated once by the user. Only the hash is stored in the database.
3. **Session Tokens**: Long-lived, revocable tokens (e.g., `sess_...`) generated using the Master Key. Used for persistent web access (Web Connectors).
4. **Data Isolation**: A PostgreSQL trigger ensures that no user can access or modify another user's expenses.

## Usage Scenarios

| Scenario | Recommendation | Expiration |
| :--- | :--- | :--- |
| **Personal Use (Claude Desktop)** | Use Master Key (`sk_live_...`) in your private config. | **Never Expires.** Stay logged in forever. |
| **Web / Mobile Access** | Generate a Session Token (`sess_...`) via the CLI. | **Persistent.** Lasts until explicitly revoked/deleted. |
| **Guest / Shared Access** | Generate a Session Token (`sess_...`) for your friend. | **Revocable.** You can cut their access anytime. |

## AI Security Rules (Concierge Mode)

To ensure maximum security and convenience:
1. **Show Only Once**: Upon registration, the Master Key is displayed exactly once.
2. **Persistent Identity**: Use the Session Token or Master Key in the Connection URL to maintain identity across restarts.
3. **Manual Forget Only**: The AI will "forget" the user only when they explicitly say "logout" or "disconnect".
4. **Reconnect Flow**: If a user is logged out, the AI will ask for their Master Key or a new Session link to restore access.
5. **Resilience**: Even if the Railway server restarts, the `sessions` table ensures your identity is instantly recognized when you reconnect.

---

## Proposed Changes

### [Component] Database Layer
#### [MODIFY] [setup_db.py](file:///d:/MCP_SERVER_BUILDING/REMOTE/setup_db.py)
- **Users Table**: Add `api_key_hash` (TEXT) and `api_key_created_at` (TIMESTAMP).
- **Sessions Table [NEW]**: Store temporary tokens with an `expires_at` timestamp.
- **Migration**: Ensure existing users are not broken during the upgrade.

### [Component] Security CLI
#### [NEW] [generate_key.py](file:///d:/MCP_SERVER_BUILDING/REMOTE/generate_key.py)
A standalone tool for managing identities:
- `--register <email>`: Create a new account and generate a permanent Master Key.
- `--session --email <email> --key <master_key> --hours <N>`: Generate a temporary session URL.
- `--revoke --email <email> --key <master_key>`: Invalidate all active sessions for security.

### [Component] MCP Server Logic
#### [MODIFY] [tools.py](file:///d:/MCP_SERVER_BUILDING/REMOTE/tools.py)
- **[get_user_id](file:///d:/MCP_SERVER_BUILDING/REMOTE/tools.py#22-52)**: Update to look for `?key=` (Master Key) or `?token=` (Session Token) in the URL.
- **[resolve_user_id](file:///d:/MCP_SERVER_BUILDING/REMOTE/tools.py#54-83)**: Update to verify the provided secret against the database hash.
- **Transport Awareness**: Default to `local_owner` for pure local (`stdio`) connections for ease of use.

#### [MODIFY] [main.py](file:///d:/MCP_SERVER_BUILDING/REMOTE/main.py)
- **Instructions**: Update AI personality to guide users on how to "login" or "register" using the CLI tool.

---

## Workflow Example: "A Year Later"

1. **Day 0**: User runs `generate_key.py --register me@email.com`. They get a Master Key.
2. **Day 1**: User adds expenses. They are saved in the DB under [user_id](file:///d:/MCP_SERVER_BUILDING/REMOTE/tools.py#22-52) mapped to `me@email.com`.
3. **Day 365**: User connects from a new device. They use their Master Key. The server finds `me@email.com` in the DB and shows all history.

---

## Verification Plan

### Automated Tests
- Run `python generate_key.py` and verify database entries.
- Mock an SSE request with an expired token and verify rejection.
- Mock an SSE request with a valid Master Key and verify success.

### Manual Verification
- Deploy to Railway.
- Connect using a generated Session Token.
- Revoke the session and verify that the connection drops/fails on the next call.
