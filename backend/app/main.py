from fastapi import FastAPI

from app.api import routes
from app.services.aws import AwsDocumentStore
from app.services.documents import DocumentService
from app.settings import Settings


def create_app(document_service: DocumentService | None = None) -> FastAPI:
    settings = Settings.from_environment()
    if document_service is None:
        store = AwsDocumentStore(settings)
        document_service = DocumentService(store=store)

    app = FastAPI(title="AWS Local Cloud Lab", version="0.1.0")
    app.dependency_overrides[routes.get_document_service] = lambda: document_service
    app.include_router(routes.router)
    return app


app = create_app()
