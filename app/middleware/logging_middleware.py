import time
import re
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from app.core.logger import get_logger

logger = get_logger(__name__)

# Sensitive keys to mask in logs
SENSITIVE_KEYS = ["password", "token", "access_token", "id_token", "secret", "cvv", "api_key"]

def mask_sensitive_data(text: str) -> str:
    """
    Mask sensitive values in a string (like JSON or query params).
    """
    for key in SENSITIVE_KEYS:
        # Matches "key": "value" or "key"=value
        pattern = rf'("{key}"\s*:\s*")([^"]+)(")|({key}\s*=\s*)([^&\s]+)'
        text = re.sub(pattern, lambda m: f"{m.group(1) or m.group(4)}*****{m.group(3) or ''}", text, flags=re.IGNORECASE)
    return text

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        # Log request basic info
        client_host = request.client.host if request.client else "unknown"
        request_id = request.headers.get("X-Request-ID", "-")
        
        response = await call_next(request)
        process_time = time.time() - start_time
        
        # Mask potentially sensitive info in the path (e.g. email in query params)
        safe_path = mask_sensitive_data(str(request.url.path))
        
        logger.info(
            f"RID: {request_id} | Client: {client_host} | "
            f"Method: {request.method} | Path: {safe_path} | "
            f"Status: {response.status_code} | Duration: {process_time:.4f}s"
        )
        
        return response
