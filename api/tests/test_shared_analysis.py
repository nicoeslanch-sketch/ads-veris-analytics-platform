from app.shared_analysis import SharedAnalysisCoordinator, shared_key_digest


class FakeRedis:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, *, ex=None, nx=False):
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    def eval(self, _script, _keys, key, token):
        if self.values.get(key) == token:
            self.values.pop(key, None)
            return 1
        return 0


def test_shared_key_is_stable_and_separates_users_filters_and_versions():
    base = ("metrics", "user-a", "dataset", "0.28.0", b"content", '{"filter":"all"}')
    assert shared_key_digest(base) == shared_key_digest(base)
    assert shared_key_digest(base) != shared_key_digest((*base[:1], "user-b", *base[2:]))
    assert shared_key_digest(base) != shared_key_digest((*base[:-1], '{"filter":"north"}'))


def test_shared_coordinator_caches_and_uses_token_owned_lock():
    fake = FakeRedis()
    coordinator = SharedAnalysisCoordinator(
        "redis://test",
        cache_ttl_seconds=60,
        lock_ttl_seconds=30,
        client=fake,
    )
    key = ("metrics", "user", b"content")
    token = coordinator.acquire(key)
    assert isinstance(token, str)
    assert coordinator.acquire(key) is False
    coordinator.store(key, {"value": 42})
    assert coordinator.get(key) == {"value": 42}
    coordinator.release(key, "not-owner")
    assert coordinator.acquire(key) is False
    coordinator.release(key, token)
    assert isinstance(coordinator.acquire(key), str)
