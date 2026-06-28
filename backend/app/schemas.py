"""Pydantic request models for input validation.

Responses are assembled as plain dicts so we can preserve the exact JSON
contract the existing React client depends on.
"""

from __future__ import annotations

from typing import Any

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


class PasskeyRegisterVerifyRequest(BaseModel):
    credential: dict
    challengeToken: str
    name: str | None = Field(default=None, max_length=255)


class PasskeyLoginVerifyRequest(BaseModel):
    credential: dict
    challengeToken: str


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


class AgentChatRequest(BaseModel):
    # The full conversation rides along each turn (the server is stateless
    # between turns). Messages are OpenAI-shaped dicts: role/content plus
    # optional tool_calls / tool_call_id / name.
    messages: list[dict[str, Any]] = Field(default_factory=list)


class AgentOperation(BaseModel):
    """One step of an approved reorganization plan. Only the fields relevant to
    ``tool`` are set; the apply endpoint validates the combination."""

    tool: str
    # create_folder
    parentPath: str | None = None
    name: str | None = None
    # move_node / rename_node
    nodeType: str | None = None
    id: str | None = None
    path: str | None = None
    destinationPath: str | None = None
    newName: str | None = None


class AgentApplyRequest(BaseModel):
    operations: list[AgentOperation] = Field(default_factory=list)
