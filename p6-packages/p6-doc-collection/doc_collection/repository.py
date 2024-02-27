
from jugalbandi.document_collection.repository import DocumentCollection
from storage.storage import ExtendeStorage

class ExtendedDocumentCollection(DocumentCollection):
    def __init__(self, local_store: ExtendeStorage, remote_store: ExtendeStorage):
        super().__init__(local_store, remote_store)


    async def remove_file(self, doc_id):
        try:
            await self.remote_store.remove_file(doc_id)
            await self.local_store.remove_file(doc_id)
        except Exception as e:
            raise e
