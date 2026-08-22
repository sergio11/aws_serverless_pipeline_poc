import logging

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.logging import log_event
from app.schemas import (
    CreateDocumentRequest,
    CreateDocumentResponse,
    DocumentResponse,
)
from app.services.documents import DocumentInfrastructureError, DocumentNotFoundError, DocumentService

router = APIRouter()


def get_document_service() -> DocumentService:
    raise RuntimeError("Document service dependency was not configured")  # pragma: no cover


@router.get("/health")
def health(document_service: DocumentService = Depends(get_document_service)) -> dict:
    dependencies = document_service.health_check()
    return {"status": "ok", "dependencies": dependencies}


@router.post(
    "/documents",
    response_model=CreateDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_document(
    payload: CreateDocumentRequest,
    document_service: DocumentService = Depends(get_document_service),
) -> CreateDocumentResponse:
    try:
        document = document_service.create_document(payload.name, payload.content)
    except DocumentInfrastructureError as exc:
        log_event(logging.ERROR, "document_create_failed", reason=str(exc))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Document could not be created") from exc

    log_event(logging.INFO, "document_created", document_id=document.id, document_name=document.name)

    return CreateDocumentResponse(
        id=document.id,
        name=document.name,
        status=document.status,
    )


@router.get("/documents/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: str,
    document_service: DocumentService = Depends(get_document_service),
) -> DocumentResponse:
    try:
        document = document_service.get_document(document_id)
    except DocumentNotFoundError as exc:
        log_event(logging.INFO, "document_not_found", document_id=document_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found") from exc
    except DocumentInfrastructureError as exc:
        log_event(logging.ERROR, "document_read_failed", document_id=document_id, reason=str(exc))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Document could not be read") from exc

    return DocumentResponse(
        id=document.id,
        name=document.name,
        size=document.size,
        status=document.status,
    )


@router.get("/documents/{document_id}/content")
def get_document_content(
    document_id: str,
    document_service: DocumentService = Depends(get_document_service),
) -> Response:
    try:
        content = document_service.get_document_content(document_id)
    except DocumentNotFoundError as exc:
        log_event(logging.INFO, "document_content_not_found", document_id=document_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found") from exc
    except DocumentInfrastructureError as exc:
        log_event(logging.ERROR, "document_content_read_failed", document_id=document_id, reason=str(exc))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Document content could not be read") from exc

    return Response(content=content, media_type="text/plain")


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: str,
    document_service: DocumentService = Depends(get_document_service),
) -> Response:
    try:
        document_service.delete_document(document_id)
    except DocumentNotFoundError as exc:
        log_event(logging.INFO, "document_not_found_for_deletion", document_id=document_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found") from exc
    except DocumentInfrastructureError as exc:
        log_event(logging.ERROR, "document_deletion_failed", document_id=document_id, reason=str(exc))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Document could not be deleted") from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)
