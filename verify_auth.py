import asyncio
import hashlib
from unittest.mock import MagicMock, AsyncMock
from tools import get_user_id, resolve_user_id

async def test_auth():
    print("🧪 Running authentication tests...")

    # Mock Context for SSE with query params
    mock_ctx = MagicMock()
    mock_ctx.transport = "sse"
    mock_ctx.request_context.query_params = {"user_id": "Test@Example.Com", "key": "sk_live_123"}
    
    # 1. Test get_user_id extraction
    uid = get_user_id(None, mock_ctx)
    assert uid == "KEY:Test@Example.Com:sk_live_123"
    print("✅ get_user_id extracted KEY correctly.")

    # 2. Test get_user_id with mixed case and fallback
    mock_ctx.request_context.query_params = {}
    mock_ctx.session.metadata = {"user_id": "test@example.com", "key": "sk_live_456"}
    uid = get_user_id(None, mock_ctx)
    assert uid == "KEY:test@example.com:sk_live_456"
    print("✅ get_user_id extracted from session metadata correctly.")

    # 3. Test resolve_user_id case-insensitivity
    mock_conn = AsyncMock()
    # Mock database returning a user even if queried with different casing
    mock_conn.fetchrow.return_value = {"id": 42}
    
    key = "sk_live_789"
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    
    # This should call the DB with LOWER(email)
    user_id = await resolve_user_id(mock_conn, f"KEY:MixedCase@Email.Com:{key}")
    
    assert user_id == 42
    # Verify the SQL query used LOWER
    args = mock_conn.fetchrow.call_args[0]
    assert "LOWER(email) = LOWER($1)" in args[0]
    assert args[1] == "MixedCase@Email.Com"
    print("✅ resolve_user_id uses case-insensitive email lookup.")

    print("\n🎉 All authentication logic tests passed!")

if __name__ == "__main__":
    asyncio.run(test_auth())
