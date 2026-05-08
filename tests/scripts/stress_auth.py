"""
Auth stress test — end-to-end scenarios against a running server.

Usage:
    python tests/scripts/stress_auth.py [--url http://127.0.0.1:2024] [--email test@example.com] [--password TestPass123!]

Scenarios covered:
    1.  Register new user
    2.  Login → valid token pair
    3.  Access protected route with valid access token
    4.  Access protected route with no token → 401
    5.  Access protected route with garbage token → 401
    6.  Sequential token refresh (3 rotations)
    7.  Reuse revoked refresh token → 401
    8.  Concurrent refresh with same refresh token (race condition)
    9.  Access protected route after refresh with NEW access token → 200
    10. Access protected route after refresh with OLD access token (still within expiry) → 200 (expected — no old-access blacklist)
    11. Logout → 200
    12. Access protected route after logout with old access token → 401
    13. Refresh after logout with old refresh token → 401
    14. Re-login after logout → fresh tokens
    15. Rapid sequential logins (session hygiene)
    16. Concurrent logins (independent sessions)
    17. Multiple concurrent protected requests with same valid token
    18. Stress: N sequential refresh cycles without error
"""

import asyncio
import argparse
import sys
import time
import uuid
import httpx
from dataclasses import dataclass
from typing import Optional

BASE_URL = "http://127.0.0.1:2024"
AUTH_BASE = "/api/v1/user"

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
WARN = "\033[93m!\033[0m"

VERBOSE = False


@dataclass
class Result:
    name: str
    passed: bool
    detail: str = ""
    duration_ms: float = 0.0


results: list[Result] = []


def record(name: str, passed: bool, detail: str = "", duration_ms: float = 0.0):
    r = Result(name, passed, detail, duration_ms)
    results.append(r)
    icon = PASS if passed else FAIL
    dur = f" [{duration_ms:.0f}ms]" if duration_ms else ""
    line = f"  {icon}  {name}{dur}"
    if detail:
        line += f"\n       {detail}"
    print(line)
    return passed


def dump(label: str, resp: httpx.Response):
    """Print response body — used on unexpected failures."""
    if not VERBOSE and resp.status_code < 500:
        return
    try:
        body = resp.json()
    except Exception:
        body = resp.text[:300]
    print(f"       {label} → {resp.status_code}: {body}")


async def post(client: httpx.AsyncClient, path: str, **kwargs) -> httpx.Response:
    return await client.post(f"{BASE_URL}{AUTH_BASE}{path}", **kwargs)


async def get(client: httpx.AsyncClient, path: str, token: str) -> httpx.Response:
    return await client.get(
        f"{BASE_URL}{AUTH_BASE}{path}",
        headers={"Authorization": f"Bearer {token}"},
    )


async def register(client: httpx.AsyncClient, email: str, password: str, name: str) -> Optional[dict]:
    r = await post(client, "/register", json={
        "email": email, "password": password, "full_name": name
    })
    if r.status_code in (200, 201):
        return r.json()
    dump("register", r)
    return None


async def login(client: httpx.AsyncClient, email: str, password: str) -> Optional[dict]:
    r = await post(client, "/login", json={"email": email, "password": password})
    if r.status_code == 200:
        data = r.json()
        return data.get("data", data)
    dump("login", r)
    return None


async def refresh(client: httpx.AsyncClient, refresh_token: str) -> tuple[int, Optional[dict], float]:
    t0 = time.perf_counter()
    r = await post(client, "/refresh", json={"refresh_token": refresh_token})
    ms = (time.perf_counter() - t0) * 1000
    if r.status_code == 200:
        data = r.json()
        return r.status_code, data.get("data", data), ms
    # Capture error body for 5xx debugging
    try:
        body = r.json()
    except Exception:
        body = r.text[:500]
    return r.status_code, body, ms


async def logout(client: httpx.AsyncClient, access_token: str, refresh_token: str = None) -> tuple[int, dict]:
    body = {}
    if refresh_token:
        body["refresh_token"] = refresh_token
    r = await client.post(
        f"{BASE_URL}{AUTH_BASE}/logout",
        headers={"Authorization": f"Bearer {access_token}"},
        json=body if body else None,
    )
    try:
        resp_body = r.json()
    except Exception:
        resp_body = {"raw": r.text[:300]}
    return r.status_code, resp_body


async def me(client: httpx.AsyncClient, access_token: str) -> tuple[int, float]:
    t0 = time.perf_counter()
    r = await get(client, "/profile", access_token)
    ms = (time.perf_counter() - t0) * 1000
    return r.status_code, ms


# ---------------------------------------------------------------------------
# Scenario helpers
# ---------------------------------------------------------------------------

def unique_email(prefix: str = "stress") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}@stress-test.com"


async def run_all(base_url: str, seed_password: str):
    global BASE_URL
    BASE_URL = base_url.rstrip("/")

    print(f"\n{'='*60}")
    print(f"  Auth Stress Test  →  {BASE_URL}")
    print(f"{'='*60}\n")

    # Check server reachable before running scenarios
    try:
        async with httpx.AsyncClient(timeout=5) as probe:
            await probe.get(f"{BASE_URL}/")
    except Exception:
        print(f"  {FAIL}  Server not reachable at {BASE_URL}")
        print("       Start the server first: uvicorn src.api.server:app --host 127.0.0.1 --port 2024\n")
        return False

    async with httpx.AsyncClient(timeout=60) as client:

        # ------------------------------------------------------------------
        # 1. Register
        # ------------------------------------------------------------------
        print("── Scenario 1: Registration ──")
        email = unique_email("stress")
        t0 = time.perf_counter()
        reg = await register(client, email, seed_password, "Stress Tester")
        ms = (time.perf_counter() - t0) * 1000
        record("Register new user", reg is not None, f"email={email}", ms)

        # Duplicate registration
        t0 = time.perf_counter()
        dup = await post(client, "/register", json={
            "email": email, "password": seed_password, "full_name": "Dup"
        })
        ms = (time.perf_counter() - t0) * 1000
        record("Duplicate email → 409", dup.status_code == 409, f"got {dup.status_code}", ms)

        # ------------------------------------------------------------------
        # 2. Login
        # ------------------------------------------------------------------
        print("\n── Scenario 2: Login ──")
        t0 = time.perf_counter()
        tokens = await login(client, email, seed_password)
        ms = (time.perf_counter() - t0) * 1000
        ok = tokens is not None and "access_token" in tokens
        record("Login → token pair", ok, "", ms)
        if not ok:
            print("  FATAL: cannot continue without tokens")
            return

        access = tokens["access_token"]
        refresh_tok = tokens["refresh_token"]

        # Wrong password
        t0 = time.perf_counter()
        bad = await post(client, "/login", json={"email": email, "password": "WrongPass999!"})
        ms = (time.perf_counter() - t0) * 1000
        record("Wrong password → 401", bad.status_code == 401, f"got {bad.status_code}", ms)

        # ------------------------------------------------------------------
        # 3. Protected route — valid token
        # ------------------------------------------------------------------
        print("\n── Scenario 3: Protected route ──")
        status, ms = await me(client, access)
        record("GET /me with valid access token → 200", status == 200, f"got {status}", ms)

        # No token
        t0 = time.perf_counter()
        r = await client.get(f"{BASE_URL}{AUTH_BASE}/profile")
        ms = (time.perf_counter() - t0) * 1000
        record("GET /me with no token → 401/422", r.status_code in (401, 422), f"got {r.status_code}", ms)

        # Garbage token
        t0 = time.perf_counter()
        r = await client.get(
            f"{BASE_URL}{AUTH_BASE}/profile",
            headers={"Authorization": "Bearer garbage.token.here"},
        )
        ms = (time.perf_counter() - t0) * 1000
        record("GET /me with garbage token → 401", r.status_code == 401, f"got {r.status_code}", ms)

        # ------------------------------------------------------------------
        # 4. Sequential refresh rotations
        # ------------------------------------------------------------------
        print("\n── Scenario 4: Sequential refresh rotations ──")
        cur_access = access
        cur_refresh = refresh_tok
        rotation_ok = True
        for i in range(3):
            code, new_tokens, ms = await refresh(client, cur_refresh)
            if code != 200 or not new_tokens or "access_token" not in new_tokens:
                record(f"Refresh rotation {i+1}/3", False, f"status={code}", ms)
                rotation_ok = False
                break
            old_refresh = cur_refresh
            cur_access = new_tokens["access_token"]
            cur_refresh = new_tokens["refresh_token"]
            record(f"Refresh rotation {i+1}/3", True, "", ms)

            # Verify /me works with new access token
            status, ms2 = await me(client, cur_access)
            record(f"  /me after rotation {i+1} → 200", status == 200, f"got {status}", ms2)

        # ------------------------------------------------------------------
        # 5. Reuse revoked refresh token
        # ------------------------------------------------------------------
        print("\n── Scenario 5: Revoked refresh token reuse ──")
        # old_refresh is the one used in the last rotation above
        if rotation_ok:
            code, _, ms = await refresh(client, old_refresh)
            record("Revoked refresh token → 401", code == 401, f"got {code}", ms)

        # ------------------------------------------------------------------
        # 6. Concurrent refresh (race condition)
        # ------------------------------------------------------------------
        print("\n── Scenario 6: Concurrent refresh (race condition) ──")
        # Get a fresh token pair for this test
        fresh = await login(client, email, seed_password)
        if fresh:
            race_refresh = fresh["refresh_token"]
            tasks = [refresh(client, race_refresh) for _ in range(5)]
            race_results = await asyncio.gather(*tasks, return_exceptions=True)
            successes = [r for r in race_results if not isinstance(r, Exception) and r[0] == 200]
            failures_401 = [r for r in race_results if not isinstance(r, Exception) and r[0] == 401]
            errors = [r for r in race_results if isinstance(r, Exception) or r[0] not in (200, 401)]
            record(
                "Concurrent 5× refresh: exactly 1 success",
                len(successes) == 1,
                f"successes={len(successes)}, 401s={len(failures_401)}, errors={len(errors)}"
            )
            record(
                "Concurrent refresh: no 5xx errors",
                len(errors) == 0,
                f"errors={[(e[0], e[1]) for e in errors if not isinstance(e, Exception)]}"
            )
            for e in errors:
                if not isinstance(e, Exception) and e[0] >= 500:
                    print(f"       [500 body] {e[1]}")
            # Use the winning tokens going forward
            if successes:
                win = successes[0][1]
                cur_access = win["access_token"]
                cur_refresh = win["refresh_token"]
        else:
            record("Concurrent refresh setup login", False, "login failed")

        # ------------------------------------------------------------------
        # 7. Logout flow
        # ------------------------------------------------------------------
        print("\n── Scenario 7: Logout ──")
        # Snapshot tokens before logout
        access_before_logout = cur_access
        refresh_before_logout = cur_refresh

        t0 = time.perf_counter()
        logout_code, logout_body = await logout(client, access_before_logout, refresh_before_logout)
        ms = (time.perf_counter() - t0) * 1000
        record("Logout → 200", logout_code == 200, f"got {logout_code}", ms)
        print(f"       [logout] sent refresh_token={'yes' if refresh_before_logout else 'no'}, response={logout_body}")

        # Access with blacklisted token → 401
        status, ms = await me(client, access_before_logout)
        record("Blacklisted access token → 401", status == 401, f"got {status}", ms)

        # Refresh after logout → 401
        code, refresh_body, ms = await refresh(client, refresh_before_logout)
        record("Refresh after logout → 401", code == 401, f"got {code}", ms)
        if code != 401:
            print(f"       [refresh-after-logout] got {code}: {refresh_body}")

        # Double logout (idempotent)
        t0 = time.perf_counter()
        r = await client.post(
            f"{BASE_URL}{AUTH_BASE}/logout",
            headers={"Authorization": f"Bearer {access_before_logout}"},
        )
        ms = (time.perf_counter() - t0) * 1000
        record("Double logout → 401 (token already blacklisted)", r.status_code == 401, f"got {r.status_code}", ms)

        # ------------------------------------------------------------------
        # 8. Re-login after logout
        # ------------------------------------------------------------------
        print("\n── Scenario 8: Re-login after logout ──")
        new_tokens = await login(client, email, seed_password)
        ok = new_tokens is not None and "access_token" in new_tokens
        record("Re-login after logout → 200", ok, "")
        if ok:
            status, ms = await me(client, new_tokens["access_token"])
            record("Protected route with fresh tokens → 200", status == 200, f"got {status}", ms)
            cur_access = new_tokens["access_token"]
            cur_refresh = new_tokens["refresh_token"]

        # ------------------------------------------------------------------
        # 9. Concurrent protected requests (no auth interference)
        # ------------------------------------------------------------------
        print("\n── Scenario 9: Concurrent protected requests ──")
        tasks = [me(client, cur_access) for _ in range(20)]
        concurrent_results = await asyncio.gather(*tasks, return_exceptions=True)
        all_200 = all(
            not isinstance(r, Exception) and r[0] == 200
            for r in concurrent_results
        )
        avg_ms = sum(r[1] for r in concurrent_results if not isinstance(r, Exception)) / len(concurrent_results)
        record("20× concurrent /me → all 200", all_200,
               f"avg={avg_ms:.0f}ms, failures={sum(1 for r in concurrent_results if isinstance(r, Exception) or r[0] != 200)}")

        # ------------------------------------------------------------------
        # 10. Stress: N sequential refresh cycles
        # ------------------------------------------------------------------
        print("\n── Scenario 10: Stress — 10 sequential refresh cycles ──")
        stress_access = cur_access
        stress_refresh = cur_refresh
        stress_ok = True
        durations = []
        for i in range(10):
            code, new_tok, ms = await refresh(client, stress_refresh)
            durations.append(ms)
            if code != 200 or not new_tok:
                record(f"Stress refresh cycle {i+1}/10", False, f"status={code}", ms)
                stress_ok = False
                break
            stress_access = new_tok["access_token"]
            stress_refresh = new_tok["refresh_token"]
        if stress_ok:
            avg = sum(durations) / len(durations)
            record("10 sequential refresh cycles — all passed", True,
                   f"avg={avg:.0f}ms min={min(durations):.0f}ms max={max(durations):.0f}ms")
            # Final /me check
            status, ms = await me(client, stress_access)
            record("Protected route after 10 rotations → 200", status == 200, f"got {status}", ms)

        # ------------------------------------------------------------------
        # 11. Rapid sequential logins (session hygiene)
        # ------------------------------------------------------------------
        print("\n── Scenario 11: Rapid sequential logins ──")
        last_tokens = None
        for i in range(5):
            t = await login(client, email, seed_password)
            if t:
                last_tokens = t
        ok = last_tokens is not None
        record("5 rapid sequential logins — no server error", ok, "")
        if ok:
            status, ms = await me(client, last_tokens["access_token"])
            record("Protected route with last-login token → 200", status == 200, f"got {status}", ms)

        # ------------------------------------------------------------------
        # 12. Concurrent logins (independent sessions)
        # ------------------------------------------------------------------
        print("\n── Scenario 12: Concurrent logins ──")
        login_tasks = [login(client, email, seed_password) for _ in range(5)]
        login_results = await asyncio.gather(*login_tasks, return_exceptions=True)
        valid_tokens = [r for r in login_results if not isinstance(r, Exception) and r and "access_token" in r]
        record(
            "5 concurrent logins — all succeed",
            len(valid_tokens) == 5,
            f"succeeded={len(valid_tokens)}/5"
        )
        # Each token should independently work
        if valid_tokens:
            me_tasks = [me(client, t["access_token"]) for t in valid_tokens]
            me_results = await asyncio.gather(*me_tasks, return_exceptions=True)
            all_ok = all(not isinstance(r, Exception) and r[0] == 200 for r in me_results)
            record("All concurrent session tokens independently valid", all_ok, "")

        # ------------------------------------------------------------------
        # 13. Invalid / malformed refresh tokens
        # ------------------------------------------------------------------
        print("\n── Scenario 13: Malformed tokens ──")
        malformed_cases = [
            ("empty string", ""),
            ("whitespace", "   "),
            ("jwt structure wrong", "a.b"),
            ("valid jwt wrong secret", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"),
        ]
        for label, tok in malformed_cases:
            code, _, ms = await refresh(client, tok)
            record(f"Malformed refresh ({label}) → 401/422", code in (401, 422), f"got {code}", ms)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    failed = total - passed

    print(f"\n{'='*60}")
    print(f"  Results: {passed}/{total} passed", end="")
    if failed:
        print(f"  ({failed} FAILED)")
        print(f"\n  Failed scenarios:")
        for r in results:
            if not r.passed:
                print(f"    {FAIL}  {r.name}  {r.detail}")
    else:
        print(f"  — all passed {PASS}")
    print(f"{'='*60}\n")

    return failed == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Auth stress test")
    parser.add_argument("--url", default="http://127.0.0.1:2024", help="Base server URL")
    parser.add_argument("--password", default="StressTest@123!", help="Test user password")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print response bodies on all non-5xx failures")
    args = parser.parse_args()

    VERBOSE = args.verbose
    ok = asyncio.run(run_all(args.url, args.password))
    sys.exit(0 if ok else 1)
