from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    jwt_secret_key: str

    model_config = {"env_file": ".env"}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if len(self.jwt_secret_key) < 32:
            raise ValueError("JWT_SECRET_KEY must be ≥32 chars")
