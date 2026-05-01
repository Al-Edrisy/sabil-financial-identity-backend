from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from fastapi import Request

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
        except RuntimeError as e:
            # Client disconnected before the response could be sent.
            # This commonly happens when ngrok times out on long-running
            # requests (e.g. KYC with OCR model initialisation).
            # Silently return a minimal 200 to avoid crashing the ASGI stack.
            if "No response returned" in str(e):
                return Response(status_code=200)
            raise

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # Prevent Clickjacking
        response.headers["X-Frame-Options"] = "DENY"
        
        # XSS Protection (for older browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # HSTS (Strict Transport Security) - Enabled for production
        # Forces browsers to only interact with the server over HTTPS
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        # Referrer Policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Content Security Policy
        # Relaxed for Swagger UI/Redoc (allowing CDNs and unsafe-inline)
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https://fastapi.tiangolo.com; "
            "connect-src 'self'; "
            "object-src 'none';"
        )
        response.headers["Content-Security-Policy"] = csp
        
        return response
