import os
import time

import redis
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL", "")
REDIS_URL = os.getenv("REDIS_URL", "")


def wait_for_dependencies(max_retries: int = 30, sleep_seconds: int = 2) -> None:
    if not DATABASE_URL or not REDIS_URL:
        raise RuntimeError("DATABASE_URL and REDIS_URL must be set")

    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)

    for attempt in range(1, max_retries + 1):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            redis_client.ping()
            print("worker dependencies are ready")
            return
        except Exception as exc:
            print(f"worker dependency check failed (attempt {attempt}/{max_retries}): {exc}")
            time.sleep(sleep_seconds)

    raise RuntimeError("worker could not connect to dependencies")


def main() -> None:
    wait_for_dependencies()
    print("worker bootstrapped - Phase 1 placeholder loop running")

    while True:
        time.sleep(30)


if __name__ == "__main__":
    main()
