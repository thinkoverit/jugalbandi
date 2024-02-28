from abc import ABC, abstractmethod
import os
from typing import AsyncIterator, Self
from aiofiles import os as aiofiles_os
import aiofiles
import shutil
import logging

logger = logging.getLogger(__name__)


class P6Storage(ABC):
    @abstractmethod
    async def write_file(self, file_path: str, file_content: bytes):
        pass

    @abstractmethod
    async def read_file(self, file_path: str) -> bytes:
        pass

    @abstractmethod
    def path(self, path_suffix: str) -> str:
        pass

    @abstractmethod
    def list_files(
        self, folder_path: str, start_offset: str = "", end_offset: str = ""
    ) -> AsyncIterator[str]:
        pass

    @abstractmethod
    def list_subfolders(
        self, folder_path: str, start_offset: str = "", end_offset: str = ""
    ) -> AsyncIterator[str]:
        pass

    @abstractmethod
    async def make_public(self, file_path: str) -> str:
        pass

    @abstractmethod
    async def public_url(self, file_path: str) -> str:
        pass

    @abstractmethod
    async def file_exists(self, file_name: str) -> bool:
        pass

    @abstractmethod
    def new_store(self, folder_suffix: str) -> Self:
        pass

    @abstractmethod
    async def shutdown(self):
        pass

    @abstractmethod
    async def remove_file(self, doc_id: str):
        pass

class P6LocalStorage(P6Storage):
    def __init__(self, base_dir: str):
        self.base_dir = base_dir

    @staticmethod
    async def _make_dir_for_file(file_path: str):
        dirname = os.path.dirname(file_path)
        await aiofiles_os.makedirs(dirname, exist_ok=True)

    async def write_file(self, file_suffix: str, file_content: bytes):
        file_path = self.path(file_suffix)

        await self._make_dir_for_file(file_path)

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(file_content)

    async def read_file(self, file_suffix: str) -> bytes:
        async with aiofiles.open(self.path(file_suffix), "rb") as f:
            return await f.read()

    def path(self, path_suffix: str):
        return f"{self.base_dir}/{path_suffix}"

    async def list_files(
        self, folder_path: str, start_offset: str = "", end_offset: str = ""
    ):
        dir_iterator = await aiofiles_os.scandir(self.path(folder_path))
        for entry in dir_iterator:
            if entry.is_file():
                yield entry.name

    def list_subfolders(
        self, folder_path: str, start_offset: str = "", end_offset: str = ""
    ) -> AsyncIterator[str]:
        raise NotImplementedError("method make_public not implemented")

    async def make_public(self, file_path: str) -> str:
        raise NotImplementedError("method make_public not implemented")

    async def public_url(self, file_path: str) -> str:
        raise NotImplementedError("method make_public not implemented")

    async def file_exists(self, file_name: str) -> bool:
        return await aiofiles_os.path.exists(self.path(file_name))

    def new_store(self, folder_suffix: str) -> "P6LocalStorage":
        folder_path = self.path(folder_suffix)
        return P6LocalStorage(folder_path)

    async def shutdown(self):
        pass
    
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

class P6NullStorage(P6Storage):
    async def write_file(self, file_path: str, file_content: bytes):
        pass

    async def read_file(self, file_path: str) -> bytes:
        return b""

    def path(self, path_suffix: str):
        return path_suffix

    def list_files(
        self, folder_path: str, start_offset: str = "", end_offset: str = ""
    ):
        yield from ()

    async def make_public(self, file_path: str) -> str:
        return file_path

    async def public_url(self, file_path: str) -> str:
        return file_path

    async def shutdown(self):
        pass

    async def file_exists(self, file_name: str) -> bool:
        return False
    
    async def remove_file(self, doc_id: str) -> bytes:
        return b""
