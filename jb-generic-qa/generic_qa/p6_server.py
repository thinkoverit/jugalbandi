from auth_service.db import AuthRepository
from auth_service.password import get_hashed_password, verify_password
from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from fastapi.responses import JSONResponse
from typing import Annotated, List
from asyncpg import Pool

from doc_collection.doc_db import DOCRepository
from doc_collection.repository import ExtendedDocumentCollection
from fastapi.security import OAuth2PasswordRequestForm

from fastapi.security.api_key import APIKey
from jugalbandi.auth_token.token import create_access_token, create_refresh_token

from jugalbandi.core.caching import aiocached
from jugalbandi.core.errors import InternalServerException
from jugalbandi.document_collection.repository import DocumentRepository, DocumentSourceFile
from jugalbandi.qa.indexing import GPTIndexer, LangchainIndexer

from jugalbandi.qa import TextConverter

from .p6_server_helper import (
    LoginResponse,
    UserRequest,
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

@aiocached(cache={})
async def get_auth_repo() -> AuthRepository:
    auth = AuthRepository()
    return auth

async def get_document_info(document_id: int, doc_db: DOCRepository = Depends(get_document_repo)):
    document_info = await doc_db.find_by_id(document_id)
    if not document_info:
        raise InternalServerException("Document not found")
    return document_info

async def process_files(
        files: List[UploadFile],
        document_id,
        document_name,
        document_repository: Annotated[
            DocumentRepository, Depends(get_document_repository)
        ], 
        text_converter: Annotated[TextConverter, Depends(get_text_converter)],
        doc_db: DOCRepository = Depends(get_document_repo)
    ):
    
    if document_id:
        document = await get_document_info(document_id, doc_db)
        document_collection = document_repository.get_collection(document["uuid_number"])
    else:
        document_collection = document_repository.new_collection()

    source_files = [DocumentSourceFile(file.filename, file) for file in files]
    await document_collection.init_from_files(source_files)

    list_files = []
    async for filename in document_collection.list_files():
        list_files.append(filename)
        await text_converter.textify(filename, document_collection)

    gpt_indexer = GPTIndexer()
    langchain_indexer = LangchainIndexer()

    await gpt_indexer.index(document_collection)
    await langchain_indexer.index(document_collection)

    if not document_id:
        return await doc_db.insert_document(document_name, document_collection.id, list_files)
    await doc_db.update_document(document_id, list_files)


@router.post("/signup", summary="Create new user", tags=["Authentication"])
async def signup(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    auth: Annotated[AuthRepository, Depends(get_auth_repo)],
):
    user_row = await auth.get_user(form_data.username)
    if user_row is not None:
        raise HTTPException(
            status_code=422, detail="User with this email already exist"
        )
    password_hash = get_hashed_password(form_data.password)
    await auth.insert_user(form_data.username, password_hash)
    return {
        "message":"User created succesfully",
        "status_code":200
    }


@router.post(
    "/login",
    summary="Create access and refresh tokens for user",
    tags=["Authentication"],
    response_model=LoginResponse,
)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    auth: Annotated[Pool, Depends(get_auth_repo)],
):
    user_row = await auth.get_user(form_data.username)
    if user_row is None:
        raise HTTPException(status_code=200, detail="Incorrect email")
    password_hash = user_row.get("password_hash")
    if not verify_password(form_data.password, password_hash):
        raise HTTPException(status_code=200, detail="Incorrect password")
    return LoginResponse(
        access_token=create_access_token(data={"sub": form_data.username}),
        token_type="bearer",
        refresh_token=create_refresh_token(data={"sub": form_data.username}),
        status_code=200
    )


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
    document_repository: Annotated[DocumentRepository, Depends(get_document_repository)],
    text_converter: Annotated[TextConverter, Depends(get_text_converter)],
    doc_db: Annotated[DOCRepository, Depends(get_document_repo)],
):
    id = await process_files(files, None, document_name, document_repository, text_converter, doc_db)
    return {
        "document_id": id,
        "message": "Files uploading is successful",
        "status_code":200
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
    await process_files(files, document_id, None, document_repository, text_converter, doc_db)
    return {
        "message": "Document updated successfully",
        "status_code":200
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
    print(document_id)
    try:   
        document = await get_document_info(document_id, doc_db)
        uuid_no = document["uuid_number"]
        collection = document_repository.get_collection(uuid_no)
        await collection.remove_file(uuid_no)

        await doc_db.delete_document_by_id(document_id)

        return {
            "message": "Document collection deleted successfully",
            "status_code":200
        }
    
    except Exception as e:
        raise InternalServerException(str(e))
