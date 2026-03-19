import asyncio
import sys
sys.stdout.reconfigure(encoding='utf-8')
from tools import register_user, create_session_link, revoke_all_sessions, add_expense

async def test_flow():
    print("--- 1. Registering new user ---")
    reg_msg = await register_user("ai_test@example.com")
    print(reg_msg)
    
    # Extract the key
    if "Your Master Key:" in reg_msg:
        key = reg_msg.split("`")[1]
        print(f"\nExtracted Key: {key}")
        
        print("\n--- 2. Try adding expense (No auth) ---")
        # Simulate unauthenticated tool call
        resp = await add_expense(amount=10, category="Food", user_id="unauthenticated")
        print(resp)
        
        print("\n--- 3. Try adding expense (Master Key Auth) ---")
        # `get_user_id` normally passes "KEY:...:..." to resolve_user_id
        # Let's bypass ctx to pass it manually to user_id arg
        auth_string = f"KEY:ai_test@example.com:{key}"
        resp2 = await add_expense(amount=25.50, category="Transport", user_id=auth_string)
        print(resp2)
        
        print("\n--- 4. Create Session Link ---")
        sess_msg = await create_session_link("ai_test@example.com", key, 24)
        print(sess_msg)
        
        # Extract token
        if "Your Session Token:" in sess_msg:
            token = sess_msg.split("`")[1]
            print(f"\nExtracted Token: {token}")
            
            print("\n--- 5. Try adding expense (Session Token Auth) ---")
            token_str = f"TOKEN:{token}"
            resp3 = await add_expense(amount=5, category="Coffee", user_id=token_str)
            print(resp3)
            
            print("\n--- 6. Revoke Sessions ---")
            rev_msg = await revoke_all_sessions("ai_test@example.com", key)
            print(rev_msg)
            
            print("\n--- 7. Try adding expense with revoked token ---")
            resp4 = await add_expense(amount=5, category="Coffee", user_id=token_str)
            print("Expected fail! Result:")
            print(resp4)

if __name__ == "__main__":
    asyncio.run(test_flow())
