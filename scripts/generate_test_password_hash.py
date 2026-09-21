#!/usr/bin/env python3
"""
Generate correct bcrypt password hash for test users
"""

import bcrypt

# Test password
test_password = "TestPassword123!"

# Generate hash using bcrypt (matching backend implementation)
password_hash = bcrypt.hashpw(test_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

print(f"Password: {test_password}")
print(f"Hash: {password_hash}")
print("\nUse this hash in your SQL seed script")
