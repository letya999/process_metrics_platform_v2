# generate_env_passwords.py
import secrets
import string


def random_password(length=32, alphabet=None):
    if alphabet is None:
        alphabet = string.ascii_letters + string.digits + "!#$%&()*+-=_"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def main():
    env = {
        "POSTGRES_PASSWORD": random_password(24),
        "REDIS_PASSWORD": random_password(24),
        "JWT_SECRET_KEY": secrets.token_urlsafe(32),
    }
    for key, value in env.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
