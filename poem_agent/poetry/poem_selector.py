"""Rank eligible poems and avoid any poem already published to a destination."""
class PoemSelector:
    def __init__(self, repositories):
        self.repositories = repositories

    def select(self, channel_id: str, language=None, emotion=None):
        sql = "SELECT p.* FROM poems p WHERE NOT EXISTS (SELECT 1 FROM drafts d WHERE d.poem_id=p.id AND d.channel_id=? AND d.status='published')"
        args = (channel_id,)
        if language:
            sql += " AND p.language=?"
            args += (language,)
        if emotion:
            sql += " AND p.emotion=?"
            args += (emotion,)
        sql += " ORDER BY COALESCE(p.quality,0) DESC,p.created_at ASC LIMIT 1"
        row = self.repositories.db.one(sql, args)
        return dict(row) if row else None
