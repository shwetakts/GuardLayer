from core.guard_engine import GuardEngine
from providers.router import ProviderRouter
from storage.audit_logger import AuditLogger


# Application singletons

provider_router = ProviderRouter()
guard_engine = GuardEngine()
audit_logger = AuditLogger()


def get_provider_router() -> ProviderRouter:
    return provider_router


def get_guard_engine() -> GuardEngine:
    return guard_engine


def get_audit_logger() -> AuditLogger:
    return audit_logger