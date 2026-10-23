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
        self.votes: dict[str, int] = {}
        self.lab: dict | None = None
        self.reading: dict[str, dict] = {}
        self.reading_skipped: set[str] = set()
        self.reading_at: float = 0
        self.lab_photo: bytes | None = None
        self.comments: dict[str, dict] = {}
        self.cards: dict[str, dict] = {}

    def add_pitch(self, pitch: dict) -> str:
        pid = uuid.uuid4().hex[:12]
        self.pitches[pid] = {"id": pid, **pitch}
        return pid

    def list_pitches(self, limit: int = 200) -> list[dict]:
        return sorted(self.pitches.values(), key=lambda p: p["created_at"], reverse=True)[:limit]

    def add_card(self, card: dict) -> str:
        cid = secrets.token_urlsafe(8)
        self.cards[cid] = card
        return cid

    def get_card(self, cid: str) -> dict | None:
        return self.cards.get(cid)

    def set_status(self, pid: str, status: str) -> None:
        if pid in self.pitches:
            self.pitches[pid]["status"] = status
            self.pitches[pid]["status_at"] = clock.stamp()

    def mark_told(self, pid: str) -> None:
        if pid in self.pitches:
            self.pitches[pid]["archer_told_at"] = clock.stamp()

    # what I'm reading
    def reading_keys(self) -> set[str]:
        return set(self.reading) | self.reading_skipped

    def add_reading(self, k: str, item: dict) -> None:
        self.reading[k] = item

    def skip_reading(self, k: str) -> None:
        self.reading_skipped.add(k)

    def list_reading(self, limit: int = 30) -> list[dict]:
        return sorted(self.reading.values(), key=lambda r: r["picked_at"], reverse=True)[:limit]

    def prune_reading(self, days: int) -> None:
        pass

    def reading_refreshed(self) -> float:
        return self.reading_at

    def set_reading_refreshed(self, t: float) -> None:
        self.reading_at = t

    def put_lab(self, summary: dict, photo: bytes | None) -> None:
        self.lab = summary
        if photo is not None:
            self.lab_photo = photo

    def get_lab(self) -> dict | None:
        return self.lab

    def get_lab_photo(self) -> bytes | None:
        return self.lab_photo

    # votes: one per visitor per day per experiment; value 1, -1 or 0 (taken back)
    def vote(self, slug: str, voter: str, value: int) -> dict:
        self.votes[f"{slug}__{voter}"] = value
        return self.tally(slug)

    def tally(self, slug: str) -> dict:
        vals = [v for k, v in self.votes.items() if k.startswith(slug + "__")]
        return {"up": vals.count(1), "down": vals.count(-1)}

    def tallies(self) -> dict[str, dict]:
        return {slug: self.tally(slug) for slug in {k.split("__")[0] for k in self.votes}}

    def my_vote(self, slug: str, voter: str) -> int:
        return self.votes.get(f"{slug}__{voter}", 0)

    # comments
    def add_comment(self, c: dict) -> str:
        cid = uuid.uuid4().hex[:12]
        self.comments[cid] = {"id": cid, **c}
        return cid

    def list_comments(self, slug: str | None = None, statuses: tuple = ("visible",)) -> list[dict]:
        out = [c for c in self.comments.values() if (slug is None or c["slug"] == slug) and c["status"] in statuses]
        return sorted(out, key=lambda c: c["created_at"])

    def set_comment(self, cid: str, status: str) -> None:
        if cid in self.comments:
            self.comments[cid]["status"] = status

    def mark_comment_told(self, cid: str) -> None:
        if cid in self.comments:
            self.comments[cid]["archer_told_at"] = clock.stamp()

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

    def add_card(self, card: dict) -> str:
        cid = secrets.token_urlsafe(8)  # unguessable: a card is seen only by whoever has the link
        self.db.collection("cards").document(cid).set(card)
        return cid

    def get_card(self, cid: str) -> dict | None:
        if not cid or "/" in cid:
            return None
        snap = self.db.collection("cards").document(cid).get()
        return snap.to_dict() if snap.exists else None

    def list_pitches(self, limit: int = 200) -> list[dict]:
        q = self.db.collection("pitches").order_by("created_at", direction="DESCENDING").limit(limit)
        return [{"id": d.id, **d.to_dict()} for d in q.stream()]

    def set_status(self, pid: str, status: str) -> None:
        self.db.collection("pitches").document(pid).update({"status": status, "status_at": clock.stamp()})

    def mark_told(self, pid: str) -> None:
        self.db.collection("pitches").document(pid).update({"archer_told_at": clock.stamp()})

    def reading_keys(self) -> set[str]:
        return {d.id for d in self.db.collection("reading").select([]).stream()} | \
               {d.id for d in self.db.collection("reading_skipped").select([]).stream()}

    def add_reading(self, k: str, item: dict) -> None:
        self.db.collection("reading").document(k).set(item)
        self._reading = None

    def skip_reading(self, k: str) -> None:
        self.db.collection("reading_skipped").document(k).set({"at": clock.stamp()})

    def list_reading(self, limit: int = 30) -> list[dict]:
        import time
        if getattr(self, "_reading", None) and time.time() - self._reading[0] < 300:
            return self._reading[1][:limit]
        q = self.db.collection("reading").order_by("picked_at", direction="DESCENDING").limit(60)
        rows = [d.to_dict() for d in q.stream()]
        self._reading = (time.time(), rows)
        return rows[:limit]

    def prune_reading(self, days: int) -> None:
        from datetime import timedelta
        cutoff = (clock.now() - timedelta(days=days)).isoformat(timespec="seconds")
        for col in ("reading", "reading_skipped"):
            field = "picked_at" if col == "reading" else "at"
            for d in self.db.collection(col).where(field, "<", cutoff).stream():
                d.reference.delete()

    def reading_refreshed(self) -> float:
        snap = self.db.collection("state").document("reading").get()
        return snap.get("at") if snap.exists else 0

    def set_reading_refreshed(self, t: float) -> None:
        self.db.collection("state").document("reading").set({"at": t})

    def put_lab(self, summary: dict, photo: bytes | None) -> None:
        self.db.collection("lab").document("latest").set(summary)
        if photo is not None:
            self.db.collection("lab").document("photo").set({"jpeg": photo, "at": clock.stamp()})
        self._lab = None

    def get_lab(self) -> dict | None:
        import time

        if getattr(self, "_lab", None) and time.time() - self._lab[0] < 60:
            return self._lab[1]
        snap = self.db.collection("lab").document("latest").get()
        val = snap.to_dict() if snap.exists else None
        self._lab = (time.time(), val)
        return val

    def get_lab_photo(self) -> bytes | None:
        snap = self.db.collection("lab").document("photo").get()
        return snap.get("jpeg") if snap.exists else None

    def vote(self, slug: str, voter: str, value: int) -> dict:
        ref = self.db.collection("votes").document(f"{slug}__{voter}")
        ref.set({"slug": slug, "value": value, "at": clock.stamp()})
        return self.tally(slug)

    def tally(self, slug: str) -> dict:
        q = self.db.collection("votes").where("slug", "==", slug)
        vals = [d.get("value") for d in q.stream()]
        return {"up": vals.count(1), "down": vals.count(-1)}

    def tallies(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for d in self.db.collection("votes").stream():
            t = out.setdefault(d.get("slug"), {"up": 0, "down": 0})
            if d.get("value") == 1:
                t["up"] += 1
            elif d.get("value") == -1:
                t["down"] += 1
        return out

    def my_vote(self, slug: str, voter: str) -> int:
        snap = self.db.collection("votes").document(f"{slug}__{voter}").get()
        return snap.get("value") if snap.exists else 0

    def add_comment(self, c: dict) -> str:
        ref = self.db.collection("comments").document()
        ref.set(c)
        return ref.id

    def list_comments(self, slug: str | None = None, statuses: tuple = ("visible",)) -> list[dict]:
        q = self.db.collection("comments")
        if slug:
            q = q.where("slug", "==", slug)
        out = [{"id": d.id, **d.to_dict()} for d in q.stream()]
        return sorted([c for c in out if c.get("status") in statuses], key=lambda c: c["created_at"])

    def set_comment(self, cid: str, status: str) -> None:
        self.db.collection("comments").document(cid).update({"status": status, "status_at": clock.stamp()})

    def mark_comment_told(self, cid: str) -> None:
        self.db.collection("comments").document(cid).update({"archer_told_at": clock.stamp()})

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
