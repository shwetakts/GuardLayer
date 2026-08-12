import contextvars
import logging
import json
import datetime
from typing import Any

# Context variables to track context across asynchronous tasks
request_id_var = contextvars.ContextVar("request_id", default="N/A")
session_id_var = contextvars.ContextVar("session_id", default="N/A")
agent_id_var = contextvars.ContextVar("agent_id", default="N/A")

class ContextFilter(logging.Filter):
    """
    Logging filter that injects request_id, session_id, and agent_id contextvars into the log record.
    """
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get() or "N/A"
        record.session_id = session_id_var.get() or "N/A"
        record.agent_id = agent_id_var.get() or "N/A"
        return True

class JSONFormatter(logging.Formatter):
    """
    JSON formatter that prints log records in structured JSON format.
    """
    def format(self, record: logging.LogRecord) -> str:
        # Prevent circular dependency PII scanner references
        message = record.getMessage()
        
        log_data = {
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": message,
            "request_id": getattr(record, "request_id", "N/A"),
            "session_id": getattr(record, "session_id", "N/A"),
            "agent_id": getattr(record, "agent_id", "N/A"),
        }
        
        # Include exception traceback if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
            
        return json.dumps(log_data)

def setup_logging(log_level: str = "INFO") -> None:
    """Configures structured JSON logging for the application."""
    root_logger = logging.getLogger()
    
    # Remove existing handlers to avoid duplicate formats
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        
    handler = logging.StreamHandler()
    handler.addFilter(ContextFilter())
    handler.setFormatter(JSONFormatter())
    
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level.upper())
