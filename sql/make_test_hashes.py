
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.passwords import hash_password

TEST_PASSWORDS = ["Admin1234", "Test1234"]

TEST_TOKENS = [
    "test-verify-casey-001",
    "test-verify-casey-expired",
    "test-reset-dana-001",
    "test-reset-dana-used",
    "test-reset-dana-expired",
]

print("Password hashes (bcrypt):")
for password in TEST_PASSWORDS:
    print(f"  {password}: {hash_password(password)}")

print()
print("Token hashes (SHA-256):")
for token in TEST_TOKENS:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    print(f"  {token}: {token_hash}")
