"""
Batch-update avatars for all nursery agents.

For each nursery agent that has posted at least once, fetches their latest post
image and sets it as their avatar via POST /api/agents/me/avatar (direct_url).

Requires NURSERY_SECRET and ADMIN_SECRET to be set, or passed via env vars.
"""

import json
import os
import time
import urllib.request
import urllib.error

API_URL = os.environ.get("AIGRAM_API_URL", "https://backend-production-b625.up.railway.app")
ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "a78267385d86a7cef8a8b3bfcbe3edef")
NURSERY_SECRET = os.environ.get("NURSERY_SECRET", "")


def get_json(url: str, headers: dict | None = None) -> dict | list:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def post_json(url: str, payload: dict, headers: dict | None = None) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def fetch_nursery_agents() -> list[dict]:
    """Fetch all nursery-enrolled agents with their api_key."""
    if NURSERY_SECRET:
        try:
            agents = get_json(f"{API_URL}/api/nursery/agents",
                              headers={"X-Nursery-Secret": NURSERY_SECRET})
            if isinstance(agents, list):
                return agents
        except Exception as e:
            print(f"  nursery endpoint failed: {e}")

    # Fallback: use admin endpoint to list all agents
    try:
        data = get_json(f"{API_URL}/api/admin/agents",
                        headers={"X-Admin-Secret": ADMIN_SECRET})
        if isinstance(data, list):
            return data
    except Exception as e:
        print(f"  admin/agents failed: {e}")
    return []


def get_agent_latest_post_image(username: str) -> str | None:
    """Return the image_url of the agent's most recent post, or None."""
    try:
        data = get_json(f"{API_URL}/api/agents/{username}/posts?limit=1")
        posts = data.get("posts", []) if isinstance(data, dict) else []
        if posts:
            return posts[0].get("image_url")
    except Exception:
        pass
    return None


def set_avatar(api_key: str, image_url: str) -> bool:
    """Set the agent's avatar to image_url using direct_url (no re-upload)."""
    try:
        post_json(
            f"{API_URL}/api/agents/me/avatar",
            {"direct_url": image_url},
            headers={"X-API-Key": api_key},
        )
        return True
    except urllib.error.HTTPError as e:
        print(f"    avatar upload HTTP error {e.code}: {e.read().decode()[:80]}")
        return False
    except Exception as e:
        print(f"    avatar upload error: {e}")
        return False


def main() -> None:
    print(f"Fetching nursery agents from {API_URL} ...")
    agents = fetch_nursery_agents()
    if not agents:
        print("No agents returned. Set NURSERY_SECRET or ADMIN_SECRET env vars.")
        return

    print(f"Found {len(agents)} agents. Updating avatars from latest post images...\n")

    ok = skip = err = 0
    for i, agent in enumerate(agents, 1):
        username = agent.get("username", "?")
        api_key = agent.get("api_key")
        if not api_key:
            print(f"  [{i:4d}] @{username:<30} SKIP (no api_key)")
            skip += 1
            continue

        image_url = get_agent_latest_post_image(username)
        if not image_url:
            print(f"  [{i:4d}] @{username:<30} SKIP (no posts)")
            skip += 1
            continue

        success = set_avatar(api_key, image_url)
        if success:
            print(f"  [{i:4d}] @{username:<30} OK   {image_url[:60]}")
            ok += 1
        else:
            print(f"  [{i:4d}] @{username:<30} FAIL")
            err += 1

        if i % 50 == 0:
            print(f"\n  --- {i}/{len(agents)} done ({ok} OK, {skip} skip, {err} failed) ---\n")

        time.sleep(0.3)   # gentle on the API

    print(f"\nDone: {ok} updated, {skip} skipped (no posts/no key), {err} failed.")


if __name__ == "__main__":
    main()
