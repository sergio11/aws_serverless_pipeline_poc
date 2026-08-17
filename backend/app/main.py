from fastapi import FastAPI

from app.api import routes
from app.services.documents import DocumentService, InMemoryDocumentStore
from app.settings import Settings


def create_app() -> FastAPI:
    settings = Settings.from_environment()
    store = InMemoryDocumentStore(bucket_name=settings.s3_bucket)
    document_service = DocumentService(store=store)

    app = FastAPI(title="AWS Local Cloud Lab", version="0.1.0")
    app.dependency_overrides[routes.get_document_service] = lambda: document_service
    app.include_router(routes.router)
    return app


app = create_app()
