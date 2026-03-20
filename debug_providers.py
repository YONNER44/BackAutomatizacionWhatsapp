import asyncio

from sqlalchemy import select

from app.database.db import AsyncSessionLocal
from app.models.provider import Provider


async def main() -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Provider))
        providers = result.scalars().all()
        print("Providers in DB:")
        for p in providers:
            print(p.id, p.name, p.phone_number)


if __name__ == "__main__":
    asyncio.run(main())

