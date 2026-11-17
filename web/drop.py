"""The drop box: people Mike gives an upload link to can send him photos and large files.

How it stays safe:

- Nobody can upload without a link Mike made on his dashboard. The link's secret is the
  part after the # (https://mikeadamsnc.com/drop#<secret>), which browsers never send in
  the page address, so it stays out of server logs, analytics and link previews. Links
  run out (7 days unless Mike picks otherwise) and Mike can close one at any time, which
  also stops uploads still in flight.
- Files never pass through this app (Cloud Run refuses requests over 32 MB). For each
  file the app opens a one-file, fixed-size upload session on a private Cloud Storage
  bucket and hands the browser that session's address; the browser sends the bytes
  straight to Google. The session can write that one object and do nothing else.
- Every file is stored under a random name as plain bytes, marked "download, never show",
  so nothing a stranger sends is ever displayed or run by the site. Only Mike's dashboard
  can list, download or delete, and a download is a link that works for ten minutes.
- Limits: MAX_FILE per file, MAX_LINK_BYTES and MAX_LINK_FILES per link. A file whose
  size isn't what was promised is deleted, not kept.

On a laptop and in tests the bucket is a temp folder (LocalFiles) and the browser uploads
to this app instead of Google.
"""
import hashlib
import logging
import os
import pathlib
import re
import secrets
import tempfile
import time
import uuid
from datetime import datetime, timedelta
from urllib.parse import quote

import httpx

from . import clock

GB = 1024 ** 3
MAX_FILE = 10 * GB          # one file
MAX_LINK_BYTES = 50 * GB    # everything sent through one link
MAX_LINK_FILES = 500
LINK_DAYS = (1, 7, 30)      # how long a link can last; 7 is the default
STALE = timedelta(days=2)   # an upload that hasn't finished by then is thrown away
BINARY = "application/octet-stream"


class Refused(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def size_words(n: int) -> str:
    for unit, step in (("GB", GB), ("MB", 1024 ** 2), ("KB", 1024)):
        if n >= step:
            return f"{n / step:.1f}".rstrip("0").rstrip(".") + f" {unit}"
    return f"{n} bytes"


def clean_name(name) -> str:
    """The file's own name, made harmless: no folders, no control characters, not too long."""
    name = re.split(r"[\\/]", str(name or ""))[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip().lstrip(".")
    if len(name) > 150:
        stem, dot, ext = name.rpartition(".")
        name = (stem[: 150 - len(ext) - 1] + "." + ext) if dot and len(ext) <= 10 else name[:150]
    return name or "file"


def disposition(name: str) -> str:
    """Tells the browser to save the file under its name and never open it in the page."""
    plain = re.sub(r'[^A-Za-z0-9._ -]', "_", name)
    return f"attachment; filename=\"{plain}\"; filename*=UTF-8''{quote(name, safe='')}"


def is_token(token) -> bool:
    """Shaped like a link's secret (so junk never reaches the database)."""
    return isinstance(token, str) and bool(re.fullmatch(r"[A-Za-z0-9_-]{24,64}", token))


def folder(token: str) -> str:
    """Where a link's files sit in the bucket: not the secret itself."""
    return hashlib.sha256(token.encode()).hexdigest()[:16]


def _when(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp)


def active(link: dict | None) -> bool:
    return bool(link) and not link.get("closed") and _when(link["expires_at"]) > clock.now()


# ---------- where the bytes go ----------

class LocalFiles:
    """The bucket's stand-in on a laptop and in tests. The "session address" points back at
    this app (PUT /drop/local/<key>), which speaks the same resume rules Google does."""

    def __init__(self):
        self.dir = pathlib.Path(tempfile.mkdtemp(prefix="drop-"))
        self.sessions: dict[str, dict] = {}

    def _path(self, name: str) -> pathlib.Path:
        return self.dir / name.replace("/", "_")

    def path(self, name: str) -> pathlib.Path | None:
        p = self._path(name)
        return p if p.exists() else None

    def start(self, name: str, size: int, filename: str, origin: str) -> str:
        key = secrets.token_urlsafe(24)
        self.sessions[key] = {"name": name, "size": size}
        return f"/drop/local/{key}"

    def receive(self, key: str, first: int | None, chunk: bytes) -> tuple[int, int] | None:
        """Add bytes to a session (first=None just asks how far it got). Returns
        (bytes kept, bytes expected), or None when the session is gone or the bytes don't fit."""
        s = self.sessions.get(key)
        if not s:
            return None
        part, done = self._path(s["name"] + ".part"), self._path(s["name"])
        if done.exists():
            return s["size"], s["size"]
        have = part.stat().st_size if part.exists() else 0
        if first is not None and chunk:
            if first > have or first + len(chunk) > s["size"]:
                return None
            with open(part, "ab") as f:
                f.write(chunk[have - first:])  # bytes already kept are skipped, as Google does
            have = part.stat().st_size
        if have == s["size"]:
            part.rename(done)
        return have, s["size"]

    def persisted(self, session: str, size: int) -> int | None:
        got = self.receive(session.rsplit("/", 1)[-1], None, b"")
        return got[0] if got else None

    def size(self, name: str) -> int | None:
        p = self._path(name)
        return p.stat().st_size if p.exists() else None

    def delete(self, name: str) -> None:
        for p in (self._path(name), self._path(name + ".part")):
            p.unlink(missing_ok=True)

    def cancel(self, session: str) -> None:
        s = self.sessions.pop(session.rsplit("/", 1)[-1], None)
        if s:
            self._path(s["name"] + ".part").unlink(missing_ok=True)

    def download_url(self, name: str) -> str | None:
        return None  # the app serves local files itself


class CloudFiles:
    """A private Cloud Storage bucket (UPLOAD_BUCKET), made by deploy/setup-drop.sh."""

    def __init__(self, bucket: str):
        import google.auth
        from google.cloud import storage

        self.creds, _ = google.auth.default()
        self.bucket = storage.Client(credentials=self.creds).bucket(bucket)

    def start(self, name: str, size: int, filename: str, origin: str) -> str:
        """Open a session that can write this one object, of exactly this size, once."""
        blob = self.bucket.blob(name)
        blob.content_disposition = disposition(filename)
        return blob.create_resumable_upload_session(content_type=BINARY, size=size, origin=origin,
                                                    if_generation_match=0, checksum=None)

    def persisted(self, session: str, size: int) -> int | None:
        """How many bytes Google has kept for a session; None when the session is gone."""
        try:
            r = httpx.put(session, headers={"Content-Range": f"bytes */{size}", "Content-Length": "0"}, timeout=20)
        except httpx.HTTPError:
            return None
        if r.status_code in (200, 201):
            return size
        if r.status_code == 308:
            kept = r.headers.get("range", "")  # "bytes=0-1999"; missing when nothing is kept yet
            return int(kept.rsplit("-", 1)[1]) + 1 if "-" in kept else 0
        return None

    def size(self, name: str) -> int | None:
        blob = self.bucket.get_blob(name)
        return blob.size if blob else None

    def delete(self, name: str) -> None:
        from google.api_core.exceptions import NotFound

        try:
            self.bucket.blob(name).delete()
        except NotFound:
            pass

    def cancel(self, session: str) -> None:
        try:
            httpx.delete(session, headers={"Content-Length": "0"}, timeout=20)
        except httpx.HTTPError as e:
            logging.warning("drop: session not cancelled: %s", e)

    def download_url(self, name: str) -> str | None:
        """A link to the file that works for ten minutes. Cloud Run has no key file, so Google
        signs it for the site's own identity (needs Service Account Token Creator on itself)."""
        from google.auth.transport import requests as greq

        if not self.creds.valid or "@" not in getattr(self.creds, "service_account_email", ""):
            self.creds.refresh(greq.Request())
        return self.bucket.blob(name).generate_signed_url(
            version="v4", expiration=timedelta(minutes=10), method="GET",
            service_account_email=self.creds.service_account_email, access_token=self.creds.token)


def make_files():
    """The bucket in production (None until UPLOAD_BUCKET is set: the drop box is then off),
    a temp folder everywhere else."""
    if os.environ.get("SITE_BACKEND") != "cloud":
        return LocalFiles()
    bucket = os.environ.get("UPLOAD_BUCKET", "").strip()
    return CloudFiles(bucket) if bucket else None


# ---------- links ----------

def new_link(store, label: str, days: int) -> str:
    days = days if days in LINK_DAYS else 7
    return store.add_drop({"label": " ".join(str(label).split())[:80] or "Files for Mike Adams", "created_at": clock.stamp(),
                           "expires_at": (clock.now() + timedelta(days=days)).isoformat(timespec="seconds"),
                           "closed": False, "bytes": 0, "files": 0})


def facts(link: dict) -> dict:
    """What the upload page may know about a link."""
    return {"label": link["label"], "expires": link["expires_at"], "max_file": MAX_FILE,
            "room": max(0, MAX_LINK_BYTES - int(link.get("bytes", 0)))}


def close(store, files, token: str) -> None:
    """Close a link for good and stop anything still uploading through it."""
    store.set_drop(token, closed=True)
    for f in store.list_drop_files(token, ("pending",)):
        _discard(store, files, f)


# ---------- one file ----------

def start(store, files, token: str, name, size, sender, note, origin: str) -> dict:
    """Open an upload for one file. The same file started again (same name and size, not
    finished) picks up where it stopped instead of starting over."""
    link = store.get_drop(token)
    if not active(link):
        raise Refused(404, "This upload link is not active.")
    name = clean_name(name)
    if not isinstance(size, int) or isinstance(size, bool) or size < 1:
        raise Refused(400, "That file is empty.")
    if size > MAX_FILE:
        raise Refused(413, f"That file is larger than the {size_words(MAX_FILE)} limit for a single file.")
    for f in store.list_drop_files(token, ("pending",)):
        if f["name"] == name and f["size"] == size:
            kept = files.persisted(f["session"], size)
            if kept is not None:
                return {"id": f["id"], "url": f["session"], "offset": kept}
    totals = store.reserve(token, size, 1)
    if totals["bytes"] > MAX_LINK_BYTES or totals["files"] > MAX_LINK_FILES:
        store.reserve(token, -size, -1)
        raise Refused(413, "This link has reached its storage limit. Please ask Mike Adams for a new one.")
    fid = uuid.uuid4().hex
    obj = f"{folder(token)}/{fid}"
    try:
        session = files.start(obj, size, name, origin)
    except Exception as e:
        store.reserve(token, -size, -1)
        logging.warning("drop: upload not opened: %s", e)
        raise Refused(503, "Uploads are temporarily unavailable. Please try again in a minute.")
    store.add_drop_file(fid, {"drop": token, "label": link["label"], "name": name, "size": size, "object": obj,
                              "session": session, "status": "pending", "created_at": clock.stamp(),
                              "from": " ".join(str(sender or "").split())[:80], "note": str(note or "").strip()[:500]})
    return {"id": fid, "url": session, "offset": 0}


def file_of(store, token: str, fid) -> dict | None:
    """A file, only for whoever holds the link it came through."""
    f = store.get_drop_file(str(fid or ""))
    return f if f and secrets.compare_digest(f["drop"], token) else None


def _discard(store, files, f: dict) -> None:
    if f.get("session"):
        files.cancel(f["session"])
    files.delete(f["object"])
    store.delete_drop_file(f["id"])
    store.reserve(f["drop"], -f["size"], -1)


def settle(store, files, f: dict) -> str:
    """Check a waiting file against what really landed in the bucket: "done", still "pending",
    or "gone" (wrong size, or never finished in time: deleted)."""
    if f["status"] != "pending":
        return f["status"]
    landed = files.size(f["object"])
    if landed == f["size"]:
        store.set_drop_file(f["id"], status="done", done_at=clock.stamp(), session=None)
        return "done"
    if landed is not None:
        logging.warning("drop: %s arrived as %s bytes, not the %s promised; deleted", f["id"], landed, f["size"])
    else:
        link = store.get_drop(f["drop"])  # a link that ran out lets uploads already going finish; a closed one doesn't
        if link and not link.get("closed") and clock.now() - _when(f["created_at"]) < STALE:
            return "pending"
    _discard(store, files, f)
    return "gone"


_swept = 0.0


def sweep(store, files) -> None:
    """Settle every waiting file: keep what finished, clear what never will."""
    for f in store.list_drop_files(None, ("pending",)):
        settle(store, files, f)


def sweep_if_due(store, files) -> None:
    """About hourly, riding on the keep-warm ping."""
    global _swept
    if files is None or time.time() - _swept < 3600:
        return
    _swept = time.time()
    sweep(store, files)


def remove(store, files, f: dict) -> None:
    """Mike deleting a file: gone from the bucket and the list, and its room is given back."""
    _discard(store, files, f)
