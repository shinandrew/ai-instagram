"""
One-shot script to generate image embeddings for all existing posts.

Run locally (with backend deps installed):
    DATABASE_URL=... OPENAI_API_KEY=... python backfill_embeddings.py

Or run against the live DB by exporting Railway's DATABASE_URL.
"""

import asyncio
import os
import sys

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker


DATABASE_URL = os.environ["DATABASE_URL"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

# asyncpg needs postgresql+asyncpg:// scheme
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(DATABASE_URL, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

sys.path.insert(0, ".")
from app.services.embeddings import image_to_embedding  # noqa: E402
from app.models.post import Post  # noqa: E402


async def main() -> None:
    async with Session() as db:
        rows = (
            await db.execute(
                select(Post)
                .where(Post.image_embedding.is_(None))
                .where(Post.image_url.isnot(None))
                .order_by(Post.created_at)
            )
        ).scalars().all()

    print(f"{len(rows)} posts need embeddings")
    ok = 0

    for post in rows:
        print(f"  {post.id} ...", end=" ", flush=True)
        embedding = image_to_embedding(str(post.image_url), OPENAI_API_KEY)
        if embedding is None:
            print("SKIP")
            continue
        async with Session() as db:
            await db.execute(
                update(Post)
                .where(Post.id == post.id)
                .values(image_embedding=embedding)
            )
            await db.commit()
        print("OK")
        ok += 1

    print(f"\nDone: {ok}/{len(rows)} embeddings generated.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
