"""S3-compatible blob store (Cloudflare R2, AWS S3, MinIO, Backblaze B2), same interface as
``LocalBlobStore``.

Keys and namespaces are identical to the local store (``ws<id>/<sha256>``), stored under an optional
prefix in one bucket. Requests are signed with AWS Signature Version 4 using the standard library and
httpx, so no SDK is loaded into a small server's memory. ``path()`` downloads into a local cache for
callers that need a file on disk (ONNX Runtime, INT8 conversion); the cache is disposable.

Configuration (all required when ``GC_BLOB_BACKEND=s3``):
  GC_S3_ENDPOINT    e.g. https://<account id>.r2.cloudflarestorage.com
  GC_S3_BUCKET      bucket name
  GC_S3_ACCESS_KEY_ID, GC_S3_SECRET_ACCESS_KEY
  GC_S3_REGION      default "auto" (R2); use the bucket's region on AWS
  GC_S3_PREFIX      optional key prefix, e.g. "prod/"
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx

from app.providers.storage import _KEY

EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
_NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"


class S3Error(RuntimeError):
    """The object store refused or failed a request."""


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _enc(s: str, safe: str = "-_.~") -> str:
    return quote(s, safe=safe)


def sign_v4(method: str, url: str, headers: dict[str, str], payload_hash: str, access_key: str,
            secret_key: str, region: str, now: datetime, service: str = "s3") -> dict[str, str]:  # fmt: skip
    """Headers for a SigV4-signed request: the given ones plus host, x-amz-date,
    x-amz-content-sha256 and Authorization. Every header passed in is signed."""
    parts = urlsplit(url)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    day = amz_date[:8]
    signed = {k.lower(): " ".join(v.strip().split()) for k, v in headers.items()}
    signed.update({"host": parts.netloc, "x-amz-date": amz_date, "x-amz-content-sha256": payload_hash})
    names = sorted(signed)
    query = []
    for pair in filter(None, parts.query.split("&")):
        k, _, v = pair.partition("=")
        query.append((_enc(k), _enc(v)))
    canonical = "\n".join([
        method,
        _enc(parts.path or "/", safe="/-_.~"),
        "&".join(f"{k}={v}" for k, v in sorted(query)),
        "".join(f"{n}:{signed[n]}\n" for n in names),
        ";".join(names),
        payload_hash,
    ])  # fmt: skip
    scope = f"{day}/{region}/{service}/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    key = _hmac(_hmac(_hmac(_hmac(f"AWS4{secret_key}".encode(), day), region), service), "aws4_request")
    sig = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    out = {k: v for k, v in headers.items()}
    out.update({"x-amz-date": amz_date, "x-amz-content-sha256": payload_hash,
                "Authorization": f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
                                 f"SignedHeaders={';'.join(names)}, Signature={sig}"})  # fmt: skip
    return out


class S3BlobStore:
    name = "s3"

    def __init__(self, endpoint: str, bucket: str, access_key: str, secret_key: str, region: str = "auto",
                 prefix: str = "", cache_dir: Path | None = None,
                 transport: httpx.BaseTransport | None = None) -> None:  # fmt: skip
        self.base = f"{endpoint.rstrip('/')}/{bucket}"
        self.access_key, self.secret_key, self.region = access_key, secret_key, region
        self.prefix = prefix.strip("/") + "/" if prefix.strip("/") else ""
        self.cache = cache_dir or Path(tempfile.gettempdir()) / "gc_blob_cache"
        self.http = httpx.Client(timeout=60.0, transport=transport)

    @classmethod
    def from_env(cls) -> S3BlobStore:
        env = os.environ.get
        missing = [k for k in ("GC_S3_ENDPOINT", "GC_S3_BUCKET", "GC_S3_ACCESS_KEY_ID", "GC_S3_SECRET_ACCESS_KEY")
                   if not env(k)]  # fmt: skip
        if missing:
            raise RuntimeError(f"GC_BLOB_BACKEND=s3 needs {', '.join(missing)}")
        return cls(env("GC_S3_ENDPOINT") or "", env("GC_S3_BUCKET") or "", env("GC_S3_ACCESS_KEY_ID") or "",
                   env("GC_S3_SECRET_ACCESS_KEY") or "", env("GC_S3_REGION") or "auto", env("GC_S3_PREFIX") or "")  # fmt: skip

    def _request(self, method: str, key: str = "", query: str = "", body: bytes = b"",
                 headers: dict[str, str] | None = None) -> httpx.Response:  # fmt: skip
        url = f"{self.base}/{_enc(self.prefix + key, safe='/-_.~')}" if key else f"{self.base}/"
        if query:
            url += "?" + query
        h = sign_v4(method, url, headers or {}, hashlib.sha256(body).hexdigest() if body else EMPTY_SHA256,
                    self.access_key, self.secret_key, self.region, datetime.now(UTC))  # fmt: skip
        try:
            return self.http.request(method, url, content=body or None, headers=h)
        except httpx.HTTPError as e:
            raise S3Error(f"object store unreachable: {e}") from e

    @staticmethod
    def _check(key: str) -> None:
        if not _KEY.match(key):
            raise ValueError("invalid blob key")

    def put(self, namespace: str, data: bytes) -> tuple[str, str]:
        if not re.fullmatch(r"ws\d+|library", namespace):
            raise ValueError("invalid namespace")
        digest = hashlib.sha256(data).hexdigest()
        key = f"{namespace}/{digest}"
        r = self._request("PUT", key, body=data, headers={"content-type": "application/octet-stream"})
        if r.status_code != 200:
            raise S3Error(f"upload failed: HTTP {r.status_code}")
        return key, digest

    def get(self, key: str) -> bytes:
        self._check(key)
        r = self._request("GET", key)
        if r.status_code == 404:
            raise FileNotFoundError(key)
        if r.status_code != 200:
            raise S3Error(f"download failed: HTTP {r.status_code}")
        return r.content

    def path(self, key: str) -> Path | None:
        self._check(key)
        local = self.cache / key
        if local.is_file():
            return local
        try:
            data = self.get(key)
        except FileNotFoundError:
            return None
        local.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=local.parent)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, local)
        return local

    def delete(self, key: str) -> None:
        self._check(key)
        r = self._request("DELETE", key)
        if r.status_code not in (200, 204, 404):
            raise S3Error(f"delete failed: HTTP {r.status_code}")
        (self.cache / key).unlink(missing_ok=True)

    def _keys(self, namespace: str, limit: int | None = None) -> list[str]:
        out: list[str] = []
        token = ""
        while True:
            q = f"list-type=2&prefix={_enc(self.prefix + namespace + '/')}"
            if limit:
                q += f"&max-keys={limit}"
            if token:
                q += f"&continuation-token={_enc(token)}"
            r = self._request("GET", query=q)
            if r.status_code != 200:
                raise S3Error(f"listing failed: HTTP {r.status_code}")
            # The listing comes from the operator's own bucket endpoint. The standard library parser does not
            # resolve external entities, and its bundled expat limits entity expansion.
            root = ET.fromstring(r.content)
            out += [(k.text or "")[len(self.prefix):] for k in root.iter(f"{_NS}Key")]
            nxt = root.find(f"{_NS}NextContinuationToken")
            if limit or nxt is None or not nxt.text:
                return out
            token = nxt.text

    def delete_namespace(self, namespace: str) -> None:
        if not re.fullmatch(r"ws\d+", namespace):
            raise ValueError("invalid namespace")
        for key in self._keys(namespace):
            if _KEY.match(key):
                self.delete(key)

    def has_namespace(self, namespace: str) -> bool:
        if not re.fullmatch(r"ws\d+", namespace):
            raise ValueError("invalid namespace")
        return bool(self._keys(namespace, limit=1))
