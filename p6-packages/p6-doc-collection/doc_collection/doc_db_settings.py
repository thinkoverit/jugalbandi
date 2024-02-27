from typing import Annotated
from cachetools import cached
from pydantic import BaseSettings, Field


class DocDbSettings(BaseSettings):
    doc_database_ip: Annotated[str, Field(..., env="QA_DATABASE_IP")]
    doc_database_port: Annotated[str, Field(..., env="QA_DATABASE_PORT")]
    doc_database_username: Annotated[str, Field(..., env="QA_DATABASE_USERNAME")]
    doc_database_password: Annotated[str, Field(..., env="QA_DATABASE_PASSWORD")]
    doc_database_name: Annotated[str, Field(..., env="QA_DATABASE_NAME")]


@cached(cache={})
def get_doc_db_settings():
    return DocDbSettings()
