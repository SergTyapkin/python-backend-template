"""Run the complete example against an explicitly started local development API."""

import argparse
import secrets
from contextlib import ExitStack

import httpx


def expect(response: httpx.Response, status: int) -> dict:
    if response.status_code != status:
        raise RuntimeError(
            f"{response.request.method} {response.request.url.path}: "
            f"expected {status}, got {response.status_code}"
        )
    return response.json() if response.content else {}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()
    with ExitStack() as stack:
        clients = []
        for _ in range(2):
            client = stack.enter_context(
                httpx.Client(
                    base_url=args.base_url,
                    timeout=10,
                    trust_env=False,
                    headers={"Origin": "http://localhost:8000"},
                )
            )
            credentials = {
                "username": "example_" + secrets.token_hex(6),
                "password": secrets.token_urlsafe(24),
            }
            expect(client.post("/api/v1/auth/register", json=credentials), 201)
            login = expect(client.post("/api/v1/auth/login", json=credentials), 200)
            client.headers["X-CSRF-Token"] = login["csrf_token"]
            expect(client.get("/api/v1/auth/me"), 200)
            clients.append(client)
        alice, bob = clients
        created = expect(alice.post("/api/v1/tasks", json={"title": "Example task"}), 201)
        path = "/api/v1/tasks/" + created["id"]
        assert expect(alice.get("/api/v1/tasks"), 200)["total"] == 1
        expect(alice.patch(path, json={"description": "Patched one field"}), 200)
        expect(bob.get(path), 404)
        assert expect(bob.get("/api/v1/tasks"), 200)["total"] == 0
        expect(alice.delete(path), 405)
        for client in clients:
            expect(client.post("/api/v1/auth/logout"), 204)
        print("Example passed: auth, owned CRUD, PATCH, isolation, disabled DELETE, logout.")


if __name__ == "__main__":
    main()
