"""Pydantic request models for input validation.

Responses are assembled as plain dicts so we can preserve the exact JSON
contract the existing React client depends on.
"""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)


class ConfirmRequest(BaseModel):
    email: EmailStr
    code: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class CreateUploadRequest(BaseModel):
    filename: str
    contentType: str | None = None
    size: int | None = 0
    parentFolderId: str | None = None


class PatchFileRequest(BaseModel):
    newName: str | None = None
    destinationFolderId: str | None = None


class CreateFolderRequest(BaseModel):
    name: str | None = None
    folderName: str | None = None


class PatchFolderRequest(BaseModel):
    newName: str | None = None
    destinationFolderId: str | None = None


class PutShareRequest(BaseModel):
    permission: str = "read"
    expiryDays: int | None = None


class PatchShareRequest(BaseModel):
    permission: str | None = None
    expiryDays: int | None = None


class CreatePublicLinkRequest(BaseModel):
    password: str | None = None
    expiryDays: int | None = None


class PatchPublicLinkRequest(BaseModel):
    password: str | None = None
    removePassword: bool | None = None
    expiryDays: int | None = None


class PublicDownloadRequest(BaseModel):
    password: str | None = None


class CreateArchiveRequest(BaseModel):
    fileIds: list[str] = Field(default_factory=list)
    folderIds: list[str] = Field(default_factory=list)
