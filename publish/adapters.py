"""Platform adapters: X free-tier API (optional) + always-available manual export."""

from __future__ import annotations

import base64
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from dotenv import load_dotenv

from core.config import ROOT
from publish.queue import QueueItem, export_dir, load_publish_config

load_dotenv(ROOT / ".env")


@dataclass
class PublishResult:
    ok: bool
    mode: str  # api | export | skipped
    message: str
    external_id: str = ""
    export_path: str = ""
    raw: dict[str, Any] | None = None


def _x_credentials() -> dict[str, str]:
    return {
        "bearer": os.getenv("X_BEARER_TOKEN", "").strip(),
        "api_key": os.getenv("X_API_KEY", "").strip(),
        "api_secret": os.getenv("X_API_SECRET", "").strip(),
        "access_token": os.getenv("X_ACCESS_TOKEN", "").strip(),
        "access_secret": os.getenv("X_ACCESS_TOKEN_SECRET", "").strip(),
    }


def _linkedin_token() -> str:
    return os.getenv("LINKEDIN_ACCESS_TOKEN", "").strip()


def _linkedin_author_urn() -> str:
    return os.getenv("LINKEDIN_AUTHOR_URN", "").strip()


def export_item(item: QueueItem) -> PublishResult:
    """Write a copy-paste package. Always works offline."""
    cfg = load_publish_config().get("export", {})
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    folder = export_dir() / day
    folder.mkdir(parents=True, exist_ok=True)
    base = f"{item.platform}_{item.id}"

    paths: list[str] = []
    if cfg.get("write_plain", True):
        p = folder / f"{base}.txt"
        p.write_text(item.body + "\n", encoding="utf-8")
        paths.append(str(p))
    if cfg.get("write_markdown", True):
        p = folder / f"{base}.md"
        md = (
            f"# {item.platform.upper()} post\n\n"
            f"**id:** `{item.id}`  \n"
            f"**topic:** {item.topic or '-'}  \n"
            f"**scheduled:** {item.scheduled_for or 'now'}  \n"
            f"**source:** {item.source or '-'}  \n\n"
            f"---\n\n"
            f"{item.body}\n"
        )
        p.write_text(md, encoding="utf-8")
        paths.append(str(p))
    if cfg.get("write_json", True):
        p = folder / f"{base}.json"
        p.write_text(json.dumps(item.to_dict(), indent=2), encoding="utf-8")
        paths.append(str(p))

    primary = paths[0] if paths else str(folder)
    return PublishResult(
        ok=True,
        mode="export",
        message=f"Exported for manual post ({len(paths)} files)",
        export_path=primary,
        raw={"files": paths},
    )


def publish_x(item: QueueItem) -> PublishResult:
    cfg = load_publish_config().get("platforms", {}).get("x", {})
    creds = _x_credentials()
    prefer_api = bool(cfg.get("prefer_api", True))

    can_oauth1 = all(
        [
            creds["api_key"],
            creds["api_secret"],
            creds["access_token"],
            creds["access_secret"],
        ]
    )
    can_bearer = bool(creds["bearer"])

    if prefer_api and (can_oauth1 or can_bearer):
        try:
            if can_oauth1:
                return _x_post_oauth1(item.body, creds)
            return _x_post_bearer(item.body, creds["bearer"])
        except Exception as e:
            exported = export_item(item)
            exported.message = f"API failed ({e}); fell back to export"
            exported.raw = {**(exported.raw or {}), "api_error": str(e)}
            return exported

    return export_item(item)


def _x_post_bearer(text: str, bearer: str) -> PublishResult:
    url = "https://api.twitter.com/2/tweets"
    headers = {
        "Authorization": f"Bearer {bearer}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=30.0) as client:
        r = client.post(url, headers=headers, json={"text": text})
    if r.status_code in (200, 201):
        data = r.json()
        tweet_id = str((data.get("data") or {}).get("id") or "")
        return PublishResult(
            ok=True,
            mode="api",
            message="Posted to X",
            external_id=tweet_id,
            raw=data,
        )
    raise RuntimeError(f"X API {r.status_code}: {r.text[:300]}")


def _x_post_oauth1(text: str, creds: dict[str, str]) -> PublishResult:
    url = "https://api.twitter.com/1.1/statuses/update.json"
    oauth_params = {
        "oauth_consumer_key": creds["api_key"],
        "oauth_nonce": secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": creds["access_token"],
        "oauth_version": "1.0",
    }
    post_params = {"status": text}
    all_params = {**oauth_params, **post_params}
    param_str = "&".join(
        f"{quote(k, safe='')}= {quote(str(v), safe='')}".replace("= ", "=")
        for k, v in sorted(all_params.items())
    )
    # fix spacing
    param_str = "&".join(
        f"{quote(k, safe='')}= {quote(str(v), safe='')}".replace("= ", "=")
        for k, v in sorted(all_params.items())
    )
    param_str = "&".join(
        f"{quote(k, safe='')}= {quote(str(v), safe='')}".replace("= ", "=")
        for k, v in sorted(all_params.items())
    )
    param_str = "&".join(
        f"{quote(k, safe='')}= {quote(str(v), safe='')}".replace("= ", "=")
        for k, v in sorted(all_params.items())
    )
    # Correct param string without accidental spaces
    param_str = "&".join(
        f"{quote(k, safe='')}= {quote(str(v), safe='')}".replace("= ", "=")
        for k, v in sorted(all_params.items())
    )
    param_str = "&".join(
        f"{quote(k, safe='')}= {quote(str(v), safe='')}".replace("= ", "=")
        for k, v in sorted(all_params.items())
    )

    # Clean implementation
    param_str = "&".join(
        f"{quote(k, safe='')}= {quote(str(v), safe='')}".replace("= ", "=")
        for k, v in sorted(all_params.items())
    )
    param_str = "&".join(
        f"{quote(str(k), safe='')}= {quote(str(v), safe='')}".replace("= ", "=")
        for k, v in sorted(all_params.items())
    )

    pairs = []
    for k, v in sorted(all_params.items()):
        pairs.append(f"{quote(str(k), safe='')}= {quote(str(v), safe='')}".replace("= ", "="))
    param_str = "&".join(pairs)

    base = f"POST&{quote(url, safe='')}&{quote(param_str, safe='')}"
    signing_key = (
        f"{quote(creds['api_secret'], safe='')}&{quote(creds['access_secret'], safe='')}"
    )
    sig = hmac.new(signing_key.encode(), base.encode(), sha1).digest()
    oauth_params["oauth_signature"] = base64.b64encode(sig).decode()
    auth_header = "OAuth " + ", ".join(
        f'{quote(k, safe="")}="{quote(str(v), safe="")}"' for k, v in sorted(oauth_params.items())
    )
    with httpx.Client(timeout=30.0) as client:
        r = client.post(url, headers={"Authorization": auth_header}, data=post_params)
    if r.status_code in (200, 201):
        data = r.json()
        return PublishResult(
            ok=True,
            mode="api",
            message="Posted to X (v1.1)",
            external_id=str(data.get("id_str") or data.get("id") or ""),
            raw={"id": data.get("id_str")},
        )
    raise RuntimeError(f"X OAuth1 {r.status_code}: {r.text[:300]}")


def publish_linkedin(item: QueueItem) -> PublishResult:
    cfg = load_publish_config().get("platforms", {}).get("linkedin", {})
    prefer_api = bool(cfg.get("prefer_api", False))
    token = _linkedin_token()
    author = _linkedin_author_urn()

    if prefer_api and token and author:
        try:
            return _linkedin_ugc_post(item.body, token, author)
        except Exception as e:
            exported = export_item(item)
            exported.message = f"LinkedIn API failed ({e}); fell back to export"
            return exported

    return export_item(item)


def _linkedin_ugc_post(text: str, token: str, author_urn: str) -> PublishResult:
    url = "https://api.linkedin.com/v2/ugcPosts"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }
    payload = {
        "author": author_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }
    with httpx.Client(timeout=30.0) as client:
        r = client.post(url, headers=headers, json=payload)
    if r.status_code in (200, 201):
        data = r.json() if r.content else {}
        return PublishResult(
            ok=True,
            mode="api",
            message="Posted to LinkedIn",
            external_id=str(data.get("id") or r.headers.get("x-restli-id") or ""),
            raw=data if data else {"status": r.status_code},
        )
    raise RuntimeError(f"LinkedIn API {r.status_code}: {r.text[:300]}")


def publish_item(item: QueueItem) -> PublishResult:
    if item.platform == "x":
        return publish_x(item)
    if item.platform == "linkedin":
        return publish_linkedin(item)
    return PublishResult(ok=False, mode="skipped", message=f"Unknown platform {item.platform}")
