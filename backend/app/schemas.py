from pydantic import BaseModel, Field


class CreateDocumentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=1_048_576)


class CreateDocumentResponse(BaseModel):
    id: str
    name: str
    status: str


class DocumentResponse(BaseModel):
    id: str
    name: str
    size: int
    status: str
