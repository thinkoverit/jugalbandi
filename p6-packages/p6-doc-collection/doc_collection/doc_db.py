import operator
from typing import Dict, Optional, List, Tuple
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
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """
            )

            await connection.execute(
                """
                CREATE TABLE IF NOT EXISTS file_store (
                    id SERIAL PRIMARY KEY,
                    document_id INTEGER REFERENCES document_store(id),
                    file_name TEXT,
                    indexing BOOLEAN,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """
            )

    async def insert_document(
        self, document_name, uuid_number, documents_list
    ) -> Optional[int]:
        engine = await self._get_engine()

        async with engine.acquire() as connection:
            try:
                document_id = await connection.fetchval(
                    """
                    INSERT INTO document_store (document_name, uuid_number) VALUES ($1, $2) RETURNING id
                    """,
                    document_name,
                    uuid_number,
                )
                for file_name in documents_list:
                    await connection.execute(
                        """
                        INSERT INTO file_store (document_id, file_name, indexing) VALUES ($1, $2, $3)
                        """,
                        document_id,
                        file_name,
                        False,
                    )
                return document_id
            except Exception as e:
                print(f"Error creating document: {e}")
                return None


    async def update_document(
        self, document_id: int, documents_list: List[str]
    ) -> Optional[int]:        
        engine = await self._get_engine()

        async with engine.acquire() as connection:
            try:
                await connection.execute(
                    """
                    DELETE FROM file_store WHERE document_id=$1
                    """,
                    document_id,
                )
                for file_name in documents_list:
                    await connection.execute(
                        """
                        INSERT INTO file_store (document_id, file_name, indexing) VALUES ($1, $2, $3)
                        """,
                        document_id,
                        file_name,
                        False,
                    )
                return document_id
            except Exception as e:
                print(f"Error updating document: {e}")
                return None


    async def find_by_id(self, document_id: int) -> Optional[tuple[str, str, List[str]]]:
        engine = await self._get_engine()

        async with engine.acquire() as connection:
            try:
                document_uuid, document_name, documents_list = await connection.fetchrow(
                    """
                    SELECT document_store.uuid_number, document_store.document_name, array_agg(file_store.file_name) as documents_list 
                    FROM document_store
                    JOIN file_store ON document_store.id = file_store.document_id
                    WHERE document_store.id = $1
                    GROUP BY document_store.id, document_store.document_name
                    """,
                    document_id,
                )
                return document_uuid, document_name, documents_list
            except Exception as e:
                return None

        

    async def get_all_documents(self) -> Optional[List[Tuple[int, str, str, List[str]]]]:
        engine = await self._get_engine()

        async with engine.acquire() as connection:
            try:
                documents = await connection.fetch(
                    """
                    SELECT document_store.uuid_number, document_store.document_name, array_agg(file_store.file_name) as documents_list 
                    FROM document_store
                    JOIN file_store ON document_store.id = file_store.document_id
                    GROUP BY document_store.id, document_store.document_name
                    """
                )
                return [(doc[0], doc[1], doc[2], [file[3] for file in doc[4:]]) for doc in documents]
            except Exception as e:
                print(f"Error fetching all documents: {e}")
                return None



    async def delete_document_by_id(self, document_id: int) -> bool:
        engine = await self._get_engine()

        async with engine.acquire() as connection:
            try:
                # Delete associated files
                await connection.execute(
                    """
                    DELETE FROM file_store WHERE document_id = $1
                    """,
                    document_id,
                )
                # Delete document
                deleted_rows = await connection.execute(
                    """
                    DELETE FROM document_store WHERE id = $1
                    """,
                    document_id,
                )
                return deleted_rows == 1
            except Exception as e:
                print(f"Error deleting document with id {document_id}: {e}")
                return False
            
    async def get_uuid_number(self, document_id: int) -> str:
        engine = await self._get_engine()

        async with engine.acquire() as connection:
            row = await connection.fetchrow("SELECT uuid_number FROM document_store WHERE id = $1", document_id)

            return row["uuid_number"] if row else None