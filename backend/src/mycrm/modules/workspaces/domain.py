from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class WorkspaceKind(StrEnum):
    PRIVATE = "private"
    TEAM = "team"
    DEMO = "demo"


class WorkspaceStatus(StrEnum):
    ACTIVE = "active"
    READ_ONLY = "read_only"
    RESETTING = "resetting"
    DISABLED = "disabled"


class WorkspaceRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"
    DEMO_VISITOR = "demo_visitor"


class MembershipStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class WorkspaceAccessDeniedError(Exception):
    """Raised when an entity does not belong to the trusted workspace context."""


@dataclass(frozen=True, slots=True)
class WorkspaceContext:
    """Trusted workspace scope derived by the backend, never from a request body."""

    workspace_id: UUID
    actor_id: UUID | None
    role: WorkspaceRole
    kind: WorkspaceKind
    status: WorkspaceStatus

    @property
    def can_write(self) -> bool:
        return self.status == WorkspaceStatus.ACTIVE and self.role not in {
            WorkspaceRole.VIEWER,
            WorkspaceRole.DEMO_VISITOR,
        }

    def assert_scope(self, entity_workspace_id: UUID) -> None:
        if entity_workspace_id != self.workspace_id:
            raise WorkspaceAccessDeniedError("Entity does not belong to the active workspace")
