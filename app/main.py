import time
import logging
import uuid
import os
import yaml
from typing import Optional

from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    status,
    Query,
)
from fastapi.responses import JSONResponse

from app.config import settings
from app.dependencies import (
    get_provider_router,
    get_guard_engine,
    get_audit_logger,
)
from core.models import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    Policy,
)
from core.policy_loader import PolicyLoader
from core.logging_context import (
    setup_logging,
    request_id_var,
    session_id_var,
    agent_id_var,
)


# ------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------

setup_logging(settings.LOG_LEVEL)
logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Startup
# ------------------------------------------------------------------

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        logger.info(
            f"Loading policy from {settings.POLICY_PATH}..."
        )

        policy = PolicyLoader.load_policy(
            settings.POLICY_PATH
        )

        policy_version = PolicyLoader.get_policy_hash(
            policy
        )

        app.state.policy = policy
        app.state.policy_version = policy_version

        logger.info(
            f"Policy loaded. Version hash: {policy_version}"
        )

    except Exception as e:
        logger.error(
            f"Failed to load policy at startup: {e}",
            exc_info=True,
        )

        app.state.policy = None
        app.state.policy_version = "UNKNOWN"
        
    yield
    # Shutdown logic can go here if needed

# ------------------------------------------------------------------
# FastAPI application
# ------------------------------------------------------------------

app = FastAPI(
    title="GuardLayer API",
    description="Provider-Agnostic LLM Guardrail Policy Engine",
    version="1.0",
    lifespan=lifespan,
)


# ------------------------------------------------------------------
# Global exception handler
# ------------------------------------------------------------------

@app.exception_handler(Exception)
def global_exception_handler(request, exc):
    logger.error(
        f"Unhandled exception: {exc}",
        exc_info=True,
    )

    return JSONResponse(
        status_code=500,
        content={
            "detail": "An internal server error occurred."
        },
    )


# ------------------------------------------------------------------
# Chat endpoint
# ------------------------------------------------------------------

@app.post(
    "/chat",
    response_model=ChatResponse,
)
async def chat(
    request: ChatRequest,
    router=Depends(get_provider_router),
    engine=Depends(get_guard_engine),
    audit=Depends(get_audit_logger),
):
    policy: Optional[Policy] = app.state.policy
    policy_version: str = app.state.policy_version

    if policy is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Active policy is not loaded or invalid.",
        )

    # Generate or reuse request ID.
    request_id = (
        request.request_id
        or str(uuid.uuid4())
    )

    # Propagate request metadata into logging context.
    _rid_token = request_id_var.set(request_id)
    _sid_token = session_id_var.set(
        request.session_id or "N/A"
    )
    _aid_token = agent_id_var.set(
        request.agent_id or "N/A"
    )

    try:

        # ----------------------------------------------------------
        # 1. Resolve provider
        # ----------------------------------------------------------

        try:
            adapter = router.get_adapter(
                request.provider
            )

        except KeyError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

        if not request.messages:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Messages list cannot be empty.",
            )

        # ----------------------------------------------------------
        # 2. Input guardrails
        # ----------------------------------------------------------

        input_text = request.messages[-1].content

        start_time = time.time()

        input_guard_result = engine.check_input(
            input_text,
            policy,
        )

        if not input_guard_result.allowed:

            latency_ms = (
                time.time() - start_time
            ) * 1000

            audit_id = audit.log(
                provider=request.provider,
                policy_version=policy_version,
                input_check_result=(
                    input_guard_result.model_dump()
                ),
                output_check_result=None,
                final_action="block",
                latency_ms=latency_ms,
                called_provider=False,
                input_text=input_text,
                output_text=None,
                session_id=request.session_id,
                agent_id=request.agent_id,
                request_id=request_id,
            )

            return ChatResponse(
                response="Request blocked by safety policy.",
                provider=request.provider,
                model="unknown",
                guardrail_applied=True,
                final_action="block",
                policy_version=policy_version,
                audit_id=audit_id,
                request_id=request_id,
                blocked_rules=(
                    input_guard_result.matched_rules
                ),
            )

        # ----------------------------------------------------------
        # 3. Call LLM provider
        # ----------------------------------------------------------

        messages_to_send = [
            msg.model_dump()
            for msg in request.messages
        ]

        if input_guard_result.action == "redact":
            messages_to_send[-1]["content"] = (
                input_guard_result.text
            )

        try:

            prov_resp = await adapter.generate(
                messages_to_send,
                request_id=request_id,
                session_id=request.session_id,
                agent_id=request.agent_id,
            )

            provider_response = prov_resp.text
            provider_model = prov_resp.model

        except Exception as e:

            latency_ms = (
                time.time() - start_time
            ) * 1000

            logger.error(
                f"Provider '{request.provider}' failed: {e}",
                exc_info=True,
            )

            audit.log(
                provider=request.provider,
                policy_version=policy_version,
                input_check_result=(
                    input_guard_result.model_dump()
                ),
                output_check_result={
                    "error": str(e)
                },
                final_action="error",
                latency_ms=latency_ms,
                called_provider=True,
                input_text=input_text,
                output_text=None,
                session_id=request.session_id,
                agent_id=request.agent_id,
                request_id=request_id,
            )

            from core.exceptions import (
                ProviderTimeoutError,
                ProviderUnavailableError,
            )

            if isinstance(
                e,
                ProviderTimeoutError,
            ):
                http_status = (
                    status.HTTP_504_GATEWAY_TIMEOUT
                )

            elif isinstance(
                e,
                ProviderUnavailableError,
            ):
                http_status = (
                    status.HTTP_503_SERVICE_UNAVAILABLE
                )

            else:
                http_status = (
                    status.HTTP_502_BAD_GATEWAY
                )

            raise HTTPException(
                status_code=http_status,
                detail=f"LLM provider error: {str(e)}",
            )

        # ----------------------------------------------------------
        # 4. Output guardrails
        # ----------------------------------------------------------

        output_guard_result = engine.check_output(
            provider_response,
            policy,
        )

        latency_ms = (
            time.time() - start_time
        ) * 1000

        # Decision priority:
        #
        # block > redact > allow

        if not output_guard_result.allowed:

            final_action = "block"

            response_text = (
                "Response blocked by safety policy."
            )

        elif (
            output_guard_result.action == "redact"
            or input_guard_result.action == "redact"
        ):

            final_action = "redact"

            response_text = (
                output_guard_result.text
            )

        else:

            final_action = "allow"

            response_text = (
                output_guard_result.text
            )

        # ----------------------------------------------------------
        # 5. Audit logging
        # ----------------------------------------------------------

        audit_id = audit.log(
            provider=request.provider,
            policy_version=policy_version,
            input_check_result=(
                input_guard_result.model_dump()
            ),
            output_check_result=(
                output_guard_result.model_dump()
            ),
            final_action=final_action,
            latency_ms=latency_ms,
            called_provider=True,
            input_text=input_text,
            output_text=provider_response,
            session_id=request.session_id,
            agent_id=request.agent_id,
            request_id=request_id,
        )

        # ----------------------------------------------------------
        # 6. Return response
        # ----------------------------------------------------------

        return ChatResponse(
            response=response_text,
            provider=request.provider,
            model=provider_model,
            guardrail_applied=True,
            final_action=final_action,
            policy_version=policy_version,
            audit_id=audit_id,
            request_id=request_id,
            blocked_rules=(
                output_guard_result.matched_rules
                if final_action == "block"
                else None
            ),
        )

    finally:

        # Prevent context leakage between requests.
        request_id_var.reset(_rid_token)
        session_id_var.reset(_sid_token)
        agent_id_var.reset(_aid_token)


# ------------------------------------------------------------------
# Health
# ------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
async def health(audit=Depends(get_audit_logger)):
    db_status = "ok" if audit.health_check() else "error"

    if db_status != "ok":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable.",
        )

    return HealthResponse(
        status="ok",
        database=db_status,
        policy_version=getattr(
            app.state,
            "policy_version",
            "UNKNOWN",
        ),
    )
# ------------------------------------------------------------------
# Policy
# ------------------------------------------------------------------

@app.get("/policy")
def get_policy():
    policy: Optional[Policy] = getattr(
        app.state,
        "policy",
        None,
    )

    if policy is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No policy loaded.",
        )

    return policy.model_dump()


# ------------------------------------------------------------------
# Policy validation
# ------------------------------------------------------------------

@app.post("/policy/validate")
def validate_policy(policy_data: dict):

    policy_dir = os.path.dirname(
        settings.POLICY_PATH
    )

    temp_filename = (
        f"temp_validate_{uuid.uuid4().hex}.yaml"
    )

    temp_path = os.path.join(
        policy_dir,
        temp_filename,
    )

    try:

        # Write temporary policy so that
        # PolicyLoader can resolve relative
        # "extends" paths.

        with open(
            temp_path,
            "w",
            encoding="utf-8",
        ) as f:

            yaml.safe_dump(
                policy_data,
                f,
            )

        PolicyLoader.load_policy(
            temp_path
        )

        return {
            "valid": True,
            "errors": [],
        }

    except Exception as e:

        return {
            "valid": False,
            "errors": [str(e)],
        }

    finally:

        if os.path.exists(temp_path):

            try:
                os.remove(temp_path)

            except Exception:
                pass


# ------------------------------------------------------------------
# Audit
# ------------------------------------------------------------------

@app.get("/audit")
async def get_audit(
    provider: Optional[str] = Query(
        None,
        description="Filter by LLM provider name",
    ),
    agent_id: Optional[str] = Query(
        None,
        description="Filter by Agent ID",
    ),
    session_id: Optional[str] = Query(
        None,
        description="Filter by Session ID",
    ),
    audit=Depends(get_audit_logger),
):
    try:

        records = audit.query_audits(
            provider=provider,
            agent_id=agent_id,
            session_id=session_id,
        )

        return records

    except Exception as e:

        logger.error(
            f"Failed to query audit logs: {e}",
            exc_info=True,
        )

        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail="Failed to query audit logs.",
        )