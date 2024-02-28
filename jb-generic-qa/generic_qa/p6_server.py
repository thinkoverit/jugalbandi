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

from jugalbandi.qa import (
    GPTIndexer,
    LangchainIndexer,
    TextConverter,
)

from .server_helper import (
    get_api_key,
    get_text_converter,
    verify_access_token,
    get_document_repository,
    User,
)

router = APIRouter()

@aiocached(cache={})
async def get_document_repo() -> DOCRepository:
    document = DOCRepository()
    return document

@router.post(
    "/new-upload-files",
    summary="Upload files to store the document set for querying",
    tags=["Document Store"],
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

    document_collection = document_repository.new_collection()
    source_files = [DocumentSourceFile(file.filename, file) for file in files]

    await document_collection.init_from_files(source_files)

    documents_list = []
    async for filename in document_collection.list_files():
        documents_list.append(filename)
        await text_converter.textify(filename, document_collection)


    gpt_indexer = GPTIndexer()
    langchain_indexer = LangchainIndexer()

    await gpt_indexer.index(document_collection)
    await langchain_indexer.index(document_collection)
        
    await doc_db.insert_document_store(document_name, document_collection.id, documents_list )

    return {
        "document_name": document_name, 
        "uuid_number": document_collection.id,
        "message": "Files uploading is successful",
    }

@router.get(
    "/get-documents",
    summary="Get Document list",
    tags=["Document Store"],
)
async def append_files(
    authorization: Annotated[User, Depends(verify_access_token)],
    api_key: Annotated[APIKey, Depends(get_api_key)],
    doc_db: DOCRepository = Depends(get_document_repo),
):
    doc_list = await doc_db.get_all_documents()
    return doc_list



@router.post(
    "/update-or-add-document",
    summary="Update or add an existing uploaded document",
    tags=["Document Store"],
)
async def update_or_add_document(
    authorization: Annotated[User, Depends(verify_access_token)],
    api_key: Annotated[APIKey, Depends(get_api_key)],
    files: List[UploadFile],
    document_name: str,
    doc_id: str,
    document_repository: Annotated[DocumentRepository, Depends(get_document_repository)],
    text_converter: Annotated[TextConverter, Depends(get_text_converter)],
    doc_db: Annotated[DOCRepository, Depends(get_document_repo)],
):
    document_info = await doc_db.get_collection(doc_id)
    if not document_info:
        raise InternalServerException("Document not found")

    existing_documents_list = document_info[0]["documents_list"] if document_info else []
    source_files = [DocumentSourceFile(file.filename, file) for file in files]
    
    document_collection = document_repository.get_collection(doc_id)

    await document_collection.init_from_files(source_files)

    async for filename in document_collection.list_files():
        await text_converter.textify(filename, document_collection)

    gpt_indexer = GPTIndexer()
    langchain_indexer = LangchainIndexer()

    await gpt_indexer.index(document_collection)
    await langchain_indexer.index(document_collection)


        # Update or add the document to the database
    if document_info:
        await doc_db.update_document_store(
            document_name, doc_id, existing_documents_list
        )
        message = "Document updated successfully"
    else:
        await doc_db.insert_document_store(
            document_name, doc_id, existing_documents_list
        )
        message = "Document added successfully"


    return {
        "document_name": document_name,
        "updated_uuid_number": document_collection.id,
        "message": message,
    }

@router.delete(
    "/delete-document/{doc_id}",
    summary="Delete a document collection by ID",
    tags=["Document Store"]
)
async def delete_document(
    doc_id: str,
    document_repository: ExtendedDocumentCollection = Depends(get_document_repository),
    doc_db: DOCRepository = Depends(get_document_repo),
):
    
    document_info = await doc_db.get_collection(doc_id)
    if not document_info:
        raise InternalServerException("Document not found")
    
    await doc_db.delete_document_by_id(doc_id)

    try:

        collection = document_repository.get_collection(doc_id)
        await collection.remove_file(doc_id)

        return {
            "updated_uuid_number": doc_id,
            "message": "Document collection deleted successfully"
        }
    
    except Exception as e:
        raise InternalServerException("Failed to delete file: " + str(e))

