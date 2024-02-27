import operator
from typing import Dict
import asyncpg
from datetime import datetime
from zoneinfo import ZoneInfo
from jugalbandi.core.caching import aiocachedmethod
from .doc_db_settings import get_doc_db_settings


class DOCRepository:
    def __init__(self) -> None:
        self.doc_db_settings = get_doc_db_settings()
        self.engine_cache: Dict[str, asyncpg.Pool] = {}

    @aiocachedmethod(operator.attrgetter("engine_cache"))
    async def _get_engine(self) -> asyncpg.Pool:
        engine = await self._create_engine()
        await self._create_schema(engine)
        return engine

    async def _create_engine(self, timeout=5):
        engine = await asyncpg.create_pool(
            host=self.doc_db_settings.doc_database_ip,
            port=self.doc_db_settings.doc_database_port,
            user=self.doc_db_settings.doc_database_username,
            password=self.doc_db_settings.doc_database_password,
            database=self.doc_db_settings.doc_database_name,
            max_inactive_connection_lifetime=timeout,
        )
        return engine

    async def _create_schema(self, engine):
        async with engine.acquire() as connection:
            await connection.execute(
                """
                CREATE TABLE IF NOT EXISTS document_store (
                    id SERIAL PRIMARY KEY,
                    document_name TEXT,
                    uuid_number TEXT,
                    documents_list TEXT[],
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """
            )

    async def insert_document_store(
        self, document_name, uuid_number, documents_list
    ):
        engine = await self._get_engine()

        print(f"document_name - {document_name}, uuid_number - {uuid_number}, documents_list - {documents_list}")

        async with engine.acquire() as connection:
            await connection.execute(
                f"""
                INSERT INTO document_store
                (document_name, uuid_number, documents_list, created_at)
                VALUES ($1, $2, ARRAY {documents_list}, $3)
                """,
                document_name,
                uuid_number,
                datetime.now(ZoneInfo("UTC")),
            )


    async def get_all_documents(self):
        engine = await self._get_engine()

        async with engine.acquire() as connection:
            result = await connection.fetch("SELECT * FROM document_store")
            return result