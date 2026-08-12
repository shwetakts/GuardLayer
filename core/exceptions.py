class PolicyLoadError(Exception):
    pass

class PolicyValidationError(Exception):
    pass

class ProviderUnavailableError(Exception):
    pass

class ProviderTimeoutError(Exception):
    pass

class ProviderAuthenticationError(Exception):
    pass

class ProviderRateLimitError(Exception):
    pass

class GuardrailExecutionError(Exception):
    pass

class AuditPersistenceError(Exception):
    pass
