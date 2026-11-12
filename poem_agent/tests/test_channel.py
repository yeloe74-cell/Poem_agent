import pytest
from storage.database import Database
from storage.repositories import Repositories
from security.owner_auth import OwnerAuth
from security.execution_guard import ExecutionGuard
from security.permissions import PermissionManager
from channel.channel_manager import ChannelManager
from channel.post_manager import PostManager


class Publisher:
    async def send_message(self, channel_id, text):
        return 42


def setup(tmp_path):
    db = Database(str(tmp_path / "channel.db")); db.initialize()
    repo = Repositories(db)
    auth = OwnerAuth(7)
    perms = PermissionManager(auth, ExecutionGuard())
    return repo, auth, perms


def test_owner_gate_and_approval_required(tmp_path):
    repo, auth, perms = setup(tmp_path)
    with pytest.raises(PermissionError):
        perms.authorize(8, "publish", approved=True)
    with pytest.raises(PermissionError):
        perms.authorize(7, "publish", approved=False)


def test_draft_requires_approval_to_publish(tmp_path):
    import asyncio
    repo, auth, perms = setup(tmp_path)
    repo.add_poem({"id":"p", "text":"poem", "fingerprint":"f", "language":"en"})
    repo.db.execute("INSERT INTO channels(id,owner_id,title,role) VALUES('c',7,'channel','destination')")
    manager = ChannelManager(repo, perms, Publisher())
    draft = manager.create_draft(7, "p", "c", "poem")
    with pytest.raises(ValueError):
        asyncio.run(manager.publish(7, draft, approved=True))
    posts = PostManager(repo, auth); posts.approve(7, draft)
    assert asyncio.run(manager.publish(7, draft, approved=True)) == "42"
