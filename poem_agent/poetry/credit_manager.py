"""Attribution is explicit and never inferred as fact without provenance."""
class CreditManager:
    def format(self, author=None, source=None):
        lines = []
        if author and author.strip():
            lines.append(f"ရေးသားသူ — {author.strip()}")
        if source and source.strip():
            lines.append(f"ရင်းမြစ် — {source.strip()}")
        return "\n".join(lines)

    def validate(self, author, source):
        return {"author": author.strip() if author else None,
                "source": source.strip() if source else None,
                "needs_review": not bool(author or source)}
