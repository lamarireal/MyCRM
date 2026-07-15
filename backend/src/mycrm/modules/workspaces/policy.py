from enum import StrEnum

from mycrm.modules.workspaces.domain import WorkspaceContext, WorkspaceKind


class SideEffect(StrEnum):
    SEND_EMAIL = "send_email"
    WRITE_CALENDAR = "write_calendar"
    CALL_WEBHOOK = "call_webhook"
    EXPORT_DATA = "export_data"
    RUN_AUTOMATION = "run_automation"


def can_execute_external_side_effect(context: WorkspaceContext, effect: SideEffect) -> bool:
    """Keep all real-world side effects disabled for public demo workspaces."""
    del effect
    return context.kind != WorkspaceKind.DEMO and context.can_write
