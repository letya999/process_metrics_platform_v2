import secrets

with open(".env.generated", "w") as f:
    f.write(f"POSTGRES_PASSWORD={secrets.token_urlsafe(32)}\n")
    f.write(f"SECRET_KEY={secrets.token_hex(32)}\n")
    f.write(f"MB_SECRET={secrets.token_hex(32)}\n")
    f.write(f"MB_ADMIN_PASSWORD={secrets.token_urlsafe(16)}\n")
