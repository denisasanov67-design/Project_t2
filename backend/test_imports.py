#!/usr/bin/env python
import sys
print("Python path:", sys.path)

try:
    from app.database import engine
    print("✓ database imported")
except Exception as e:
    print("✗ database error:", e)

try:
    from app import models
    print("✓ models imported")
except Exception as e:
    print("✗ models error:", e)

try:
    from app import schemas
    print("✓ schemas imported")
except Exception as e:
    print("✗ schemas error:", e)

try:
    from app import auth
    print("✓ auth imported")
except Exception as e:
    print("✗ auth error:", e)

print("\nПроверка завершена!")