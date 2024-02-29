from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from fastapi.responses import JSONResponse
from typing import Annotated, List

from doc_collection.doc_db import DOCRepository
from doc_collection.repository import ExtendedDocumentCollection

from fastapi.security.api_key import APIKey

from jugalbandi.core.caching import aiocached
from jugalbandi.core.errors import InternalServerException
from jugalbandi.document_collection.repository import DocumentRepository, DocumentSourceFile
from jugalbandi.qa.indexing import GPTIndexer, LangchainIndexer

from jugalbandi.qa import TextConverter

from .p6_server_helper import (
    get_api_key,
    get_text_converter,
    verify_access_token,
    get_document_repository,
    User,
)

router = APIRouter()

@aiocached(cache={})
async def get_document_repo() -> DOCRepository:
    return DOCRepository()


async def get_document_info(document_id: int, doc_db: DOCRepository = Depends(get_document_repo)):
    document_info = await doc_db.find_by_id(document_id)
    print(document_id)
    if not document_info:
        raise InternalServerException("Document not found")
    return document_info

async def process_files(
        files: List[UploadFile],
        text_converter: Annotated[TextConverter, Depends(get_text_converter)],
        document_id,
        document_repository: Annotated[
            DocumentRepository, Depends(get_document_repository)
        ],):
    
    if document_id:
        document_collection = document_repository.get_collection(document_id)
    else:
        document_collection = document_repository.new_collection()

    source_files = [DocumentSourceFile(file.filename, file) for file in files]
    await document_collection.init_from_files(source_files)

    list_files = []
    async for filename in document_collection.list_files():
        print(filename)
        list_files.append(filename)
        await text_converter.textify(filename, document_collection)

    gpt_indexer = GPTIndexer()
    langchain_indexer = LangchainIndexer()

    await gpt_indexer.index(document_collection)
    await langchain_indexer.index(document_collection)

    return {
        "id": document_collection.id,
        "list_files": list_files
    }

@router.get(
    "/get-documents",
    tags=["Pixel6 Document Store"],
)
async def append_files(
    authorization: Annotated[User, Depends(verify_access_token)],
    api_key: Annotated[APIKey, Depends(get_api_key)],
    doc_db: DOCRepository = Depends(get_document_repo),
):
    return await doc_db.get_all_documents()

@router.post(
    "/new-upload-files",
    tags=["Pixel6 Document Store"],
)
async def upload_files(
    authorization: Annotated[User, Depends(verify_access_token)],
    api_key: Annotated[APIKey, Depends(get_api_key)],
    files: List[UploadFile],
    document_name: str,    
    document_repository: Annotated[
        DocumentRepository, Depends(get_document_repository)
    ],
    text_converter: Annotated[TextConverter, Depends(get_text_converter)],
    doc_db: Annotated[DOCRepository, Depends(get_document_repo)],
):

    data = await process_files(files, text_converter, None, document_repository)
    id = await doc_db.insert_document(document_name, data["id"], data["list_files"])

    return {
        "document_name": document_name, 
        "document_id": id,
        "message": "Files uploading is successful",
    }


@router.post(
    "/update-or-add-document",
    summary="Update or add an existing uploaded document",
    tags=["Pixel6 Document Store"],
)
async def update_or_add_document(
    authorization: Annotated[User, Depends(verify_access_token)],
    api_key: Annotated[APIKey, Depends(get_api_key)],
    files: List[UploadFile],
    document_id: int,
    document_repository: Annotated[DocumentRepository, Depends(get_document_repository)],
    text_converter: Annotated[TextConverter, Depends(get_text_converter)],
    doc_db: Annotated[DOCRepository, Depends(get_document_repo)],
):
    document = await get_document_info(document_id, doc_db)

    print(document[0])

    data = await process_files(files, text_converter, document[0], document_repository)
    await doc_db.update_document(document_id, data["list_files"])

    return {
        "message": "Document updated successfully",
    }

@router.delete(
    "/delete-document/{document_id}",
    summary="Delete a document collection by ID",
    tags=["Pixel6 Document Store"]
)
async def delete_document(
    document_id: int,
    document_repository: ExtendedDocumentCollection = Depends(get_document_repository),
    doc_db: DOCRepository = Depends(get_document_repo),
):

    try:   
        document = await get_document_info(document_id, doc_db)
        print(document)
        uuid_no = document[0]
        collection = document_repository.get_collection(uuid_no)
        await collection.remove_file(uuid_no)
        index = await doc_db.delete_document_by_id(document_id)
    
        return {
            "message": "Document collection deleted successfully"
        }
    
    except Exception as e:
        raise InternalServerException(str(e))


