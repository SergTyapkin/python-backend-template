"""Bearer-only API: browser cookies and CSRF belong to the Nuxt BFF.

Uvicorn must run with --no-proxy-headers unless the deployment explicitly supplies
--forwarded-allow-ips for trusted proxy addresses. Never trust user identity headers.
"""
