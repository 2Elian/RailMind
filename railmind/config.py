from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # llm
    openai_api_key: str
    openai_api_base: str = "your_openai_url"
    openai_model: str = "your_model_name"
    rpm: int = 1000 # Requests Per Minute 
    tpm: int = 50000 # Tokens Per Minute
    
    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str
    
    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    
    # Server
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000

    # memory
    long_memory_num: int = 100
    shot_memory_num: int = 20

    sub_query_max_iterations: int = 10
    
    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()
