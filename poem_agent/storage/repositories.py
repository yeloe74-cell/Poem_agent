"""Repository layer centralizes persistence and safe query bounds."""
import json
from storage.database import Database


class Repositories:
    def __init__(self, db: Database):
        self.db = db

    def add_poem(self, item: dict) -> bool:
        try:
            self.db.execute("INSERT INTO poems(id,text,fingerprint,language,author,source,emotion,themes,style,quality) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (item["id"], item["text"], item["fingerprint"], item["language"], item.get("author"), item.get("source"), item.get("emotion"), json.dumps(item.get("themes", []), ensure_ascii=False), item.get("style"), item.get("quality")))
            return True
        except Exception as exc:
            if "UNIQUE constraint failed: poems.fingerprint" in str(exc):
                return False
            raise

    def list_poems(self, limit=100):
        return [dict(row) for row in self.db.all("SELECT * FROM poems ORDER BY created_at DESC LIMIT ?", (max(1, min(int(limit), 500)),))]

    def save_memory(self, row: dict):
        self.db.execute("INSERT INTO memories(id,owner_id,kind,content,confidence,source,verified,expires_at) VALUES(?,?,?,?,?,?,?,?)",
                        (row["id"], row["owner_id"], row["kind"], row["content"], row["confidence"], row.get("source"), int(row.get("verified", False)), row.get("expires_at")))

    def memories(self, owner_id, kind=None):
        sql = "SELECT * FROM memories WHERE owner_id=? AND (expires_at IS NULL OR expires_at>CURRENT_TIMESTAMP)"
        args = (owner_id,)
        if kind:
            sql += " AND kind=?"
            args += (kind,)
        return [dict(r) for r in self.db.all(sql + " ORDER BY confidence DESC,created_at DESC LIMIT 200", args)]

    def audit(self, actor_id, action, target, outcome):
        self.db.execute("INSERT INTO audit(actor_id,action,target,outcome) VALUES(?,?,?,?)", (actor_id, action, target, outcome))
