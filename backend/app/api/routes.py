from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.schemas import (
    CreateDocumentRequest,
    CreateDocumentResponse,
    DocumentResponse,
)
from app.services.documents import DocumentNotFoundError, DocumentService

router = APIRouter()


def get_document_service() -> DocumentService:
    raise RuntimeError("Document service dependency was not configured")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post(
    "/documents",
    response_model=CreateDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_document(
    payload: CreateDocumentRequest,
    document_service: DocumentService = Depends(get_document_service),
) -> CreateDocumentResponse:
    document = document_service.create_document(payload.name, payload.content)

    return CreateDocumentResponse(
        id=document.id,
        name=document.name,
        status=document.status.lower(),
    )


@router.get("/documents/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: str,
    document_service: DocumentService = Depends(get_document_service),
) -> DocumentResponse:
    try:
        document = document_service.get_document(document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found") from exc

    return DocumentResponse(
        id=document.id,
        name=document.name,
        size=document.size,
        status=document.status.lower(),
    )


@router.get("/documents/{document_id}/content")
def get_document_content(
    document_id: str,
    document_service: DocumentService = Depends(get_document_service),
) -> Response:
    try:
        content = document_service.get_document_content(document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found") from exc

    return Response(content=content, media_type="text/plain")
