from enum import StrEnum


class RecordStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class EntityNotFoundError(Exception):
    pass


class VersionConflictError(Exception):
    pass


class WorkspaceWriteForbiddenError(Exception):
    pass


class RelatedEntityNotFoundError(Exception):
    pass


class RelatedEntityMismatchError(Exception):
    pass


class StageOperationError(Exception):
    pass


def require_workspace_write(can_write: bool) -> None:
    if not can_write:
        raise WorkspaceWriteForbiddenError


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
