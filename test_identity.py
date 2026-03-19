import asyncio
from tools import get_user_id

class MockParams:
    def __init__(self, params):
        self.params = params
    def get(self, key):
        return self.params.get(key)

class MockRequestContext:
    def __init__(self, params):
        self.query_params = MockParams(params)

class MockContext:
    def __init__(self, params=None, session_id=None):
        if params is not None:
            self.request_context = MockRequestContext(params)
        self.session_id = session_id

def test():
    print("Testing get_user_id...")

    # Case 1: URL Parameter
    ctx1 = MockContext(params={"user_id": "alice_89"})
    assert get_user_id(None, ctx1) == "alice_89"
    print("✅ Case 1: URL parameter detected")

    # Case 2: Manual Argument Override
    assert get_user_id("bob_vv", ctx1) == "alice_89" # URL parameter should prioritize
    print("✅ Case 2: URL parameter prioritized over manual")

    # Case 3: Fallback to Manual (No URL param)
    ctx2 = MockContext(params={})
    assert get_user_id("charlie", ctx2) == "charlie"
    print("✅ Case 3: Fallback to manual argument")

    # Case 4: Fallback to Session ID
    ctx3 = MockContext(params={}, session_id="abcdef123456")
    assert get_user_id(None, ctx3) == "session_abcdef12"
    print("✅ Case 4: Fallback to session_id")

    # Case 5: No identity error
    try:
        get_user_id(None, None)
    except ValueError:
        print("✅ Case 5: Raises ValueError on no identity")

if __name__ == "__main__":
    test()
