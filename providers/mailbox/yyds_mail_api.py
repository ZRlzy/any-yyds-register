"""YYDS Mail API — register into unified registry."""
from core.base_mailbox import YYDSMailMailbox  # noqa: F401
from providers.registry import register_provider

register_provider("mailbox", "yyds_mail_api")(YYDSMailMailbox)
