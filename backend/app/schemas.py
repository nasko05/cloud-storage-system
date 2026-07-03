"""Pydantic models for the JSON contract.

Request models validate input; the response models further down lock the
output field names in one place (they are dumped to plain dicts before being
persisted/replayed by the idempotency layer).
"""

from __future__ import annotations

from typing import Any, Literal

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
    ``tool`` are set; ``agent.apply._apply_one`` validates the combination.

    Deliberately NOT a pydantic discriminated union: the imperative checks
    answer 400 with a descriptive message, which is the wire contract clients
    (and tests) rely on — a union would turn those into 422 validation errors."""

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


# --- Response models ----------------------------------------------------------
#
# One definition per response shape so routers can't drift apart on field
# names (files are `filename` everywhere; folders are `name`). Mutating routes
# build a model and pass `.model_dump()` through the idempotency layer, which
# persists and replays plain JSON. Endpoints whose key set is conditional
# (download URLs, archive status) stay hand-assembled in their routers.


class MessageOut(BaseModel):
    message: str


class UploadCreateOut(BaseModel):
    fileId: str
    uploadUrl: str
    expiresIn: int
    status: str


class FinalizeOut(BaseModel):
    fileId: str
    status: str
    size: int
    contentType: str | None


class PatchFileOut(BaseModel):
    message: str
    fileId: str
    filename: str
    parentFolderId: str


class DeleteFileOut(BaseModel):
    message: str
    fileId: str


class ChildFolderOut(BaseModel):
    type: Literal["folder"] = "folder"
    folderId: str
    name: str
    parentFolderId: str
    createdAt: str | None
    updatedAt: str | None


class ChildFileOut(BaseModel):
    type: Literal["file"] = "file"
    fileId: str
    filename: str
    parentFolderId: str
    size: int
    contentType: str | None
    status: str
    isShared: bool
    hasPublicLink: bool
    createdAt: str | None
    updatedAt: str | None


class CreateFolderOut(BaseModel):
    folderId: str
    name: str
    parentFolderId: str


class PatchFolderOut(BaseModel):
    message: str
    folderId: str
    name: str
    parentFolderId: str


class DeleteFolderOut(BaseModel):
    message: str
    folderId: str
    recursive: bool
    deletedFolders: int
    deletedFiles: int


class ShareOut(BaseModel):
    fileId: str
    principalType: str
    principalValue: str
    permission: str
    expiresAt: str | None


class DeleteShareOut(BaseModel):
    message: str
    fileId: str
    principalType: str
    principalValue: str


class InboundShareOut(BaseModel):
    fileId: str
    filename: str
    ownerId: str
    ownerEmail: str | None
    permission: str
    principalType: str
    principalValue: str
    principalDisplay: str | None
    sharedAt: str | None
    expiresAt: str | None


class FileShareOut(BaseModel):
    principalType: str
    principalValue: str
    principalDisplay: str | None
    permission: str
    sharedAt: str | None
    expiresAt: str | None


class PublicLinkCreatedOut(BaseModel):
    token: str
    fileId: str
    filename: str
    hasPassword: bool
    downloadCount: int
    expiresAt: str | None


class PublicLinkOut(BaseModel):
    token: str
    fileId: str
    filename: str | None
    hasPassword: bool
    downloadCount: int
    createdAt: str | None
    updatedAt: str | None
    expiresAt: str | None


class PatchPublicLinkOut(BaseModel):
    token: str
    hasPassword: bool
    expiresAt: str | None


class DeletePublicLinkOut(BaseModel):
    message: str
    token: str


class ArchiveQueuedOut(BaseModel):
    archiveJobId: str
    status: str
