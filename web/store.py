"""Where pitches, rate-limit counts and the daily visitor salt live.

Firestore (database "mikeadamsnc") in production; plain memory for tests and local runs.
"""
import os
import secrets
import uuid
from datetime import date, timedelta

from . import clock


class MemoryStore:
    def __init__(self):
        self.pitches: dict[str, dict] = {}
        self.salts: dict[str, bytes] = {}
        self.counts: dict[str, int] = {}

    def add_pitch(self, pitch: dict) -> str:
        pid = uuid.uuid4().hex[:12]
        self.pitches[pid] = {"id": pid, **pitch}
        return pid

    def list_pitches(self, limit: int = 200) -> list[dict]:
        return sorted(self.pitches.values(), key=lambda p: p["created_at"], reverse=True)[:limit]

    def set_status(self, pid: str, status: str) -> None:
        if pid in self.pitches:
            self.pitches[pid]["status"] = status
            self.pitches[pid]["status_at"] = clock.stamp()

    def mark_told(self, pid: str) -> None:
        if pid in self.pitches:
            self.pitches[pid]["archer_told_at"] = clock.stamp()

    def daily_salt(self, day: str) -> bytes:
        return self.salts.setdefault(day, secrets.token_bytes(32))

    def bump(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]


class FirestoreStore:
    def __init__(self):
        from google.cloud import firestore

        self.fs = firestore
        self.db = firestore.Client(database="mikeadamsnc")
        self._salt: tuple[str, bytes] | None = None

    def add_pitch(self, pitch: dict) -> str:
        ref = self.db.collection("pitches").document()
        ref.set(pitch)
        return ref.id

    def list_pitches(self, limit: int = 200) -> list[dict]:
        q = self.db.collection("pitches").order_by("created_at", direction="DESCENDING").limit(limit)
        return [{"id": d.id, **d.to_dict()} for d in q.stream()]

    def set_status(self, pid: str, status: str) -> None:
        self.db.collection("pitches").document(pid).update({"status": status, "status_at": clock.stamp()})

    def mark_told(self, pid: str) -> None:
        self.db.collection("pitches").document(pid).update({"archer_told_at": clock.stamp()})

    def daily_salt(self, day: str) -> bytes:
        """A random salt per Eastern day. Yesterday's is deleted, so ids can't be linked across days."""
        if self._salt and self._salt[0] == day:
            return self._salt[1]
        ref = self.db.collection("salts").document(day)

        @self.fs.transactional
        def get_or_make(tx):
            snap = ref.get(transaction=tx)
            if snap.exists:
                return snap.get("salt")
            salt = secrets.token_bytes(32)
            tx.set(ref, {"salt": salt})
            return salt

        salt = get_or_make(self.db.transaction())
        old = (date.fromisoformat(day) - timedelta(days=2)).isoformat()
        for d in self.db.collection("salts").where("__name__", "<", self.db.collection("salts").document(old)).stream():
            d.reference.delete()
        self._salt = (day, salt)
        return salt

    def bump(self, key: str) -> int:
        ref = self.db.collection("limits").document(key)
        ref.set({"n": self.fs.Increment(1), "day": clock.today()}, merge=True)
        return ref.get().get("n")


def make_store():
    return FirestoreStore() if os.environ.get("SITE_BACKEND") == "cloud" else MemoryStore()
