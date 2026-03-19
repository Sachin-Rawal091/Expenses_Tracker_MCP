from fastmcp import Context
import inspect

try:
    print(inspect.getsource(Context))
except Exception as e:
    print(f"Error: {e}")
