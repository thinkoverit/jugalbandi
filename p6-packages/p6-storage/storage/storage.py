from abc import ABC, abstractmethod
import os
import shutil
from aiofiles import os as aiofiles_os
import logging

from jugalbandi.storage.storage import LocalStorage, NullStorage, Storage

logger = logging.getLogger(__name__)

class ExtendeStorage(Storage):
    @abstractmethod
    async def remove_file(self, doc_id: str):
        pass

class ExtendeLocalStorage(LocalStorage):
    async def _delete_file_or_directory(self, doc_id: str):
        path = self.path(doc_id)
        if await self.file_exists(doc_id): 
            try:
                if os.path.isfile(path):
                    await aiofiles_os.remove(path)
                elif os.path.isdir(path):
                    shutil.rmtree(path, ignore_errors=False, onerror=None)
            except FileNotFoundError:
                pass
            except Exception as e:
                raise e

    async def remove_file(self, doc_id):
        try:
            await self._delete_file_or_directory(doc_id)
        except Exception as e:
            raise e

class ExtendeNullStorage(NullStorage):
    async def remove_file(self, doc_id: str) -> bytes:
        return b""
