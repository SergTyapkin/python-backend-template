"""Local cookie auth checks exact Origin and session-bound CSRF for unsafe methods.

SSO Bearer validation remains a separate, explicitly selected dependency.

Uvicorn must run with --no-proxy-headers unless the deployment explicitly supplies
--forwarded-allow-ips for trusted proxy addresses. Never trust user identity headers.
"""
