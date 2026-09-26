from pwdlib import PasswordHash

password_hash = PasswordHash.recommended()

plain_password = "test"

hashed_password = password_hash.hash(plain_password)
print(f"hash:\n{hashed_password}")
