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

    def pipeline(self):
        return FakePipeline(self)

    def sadd(self, key, value):
        self.values.setdefault(key, set()).add(value)
        return 1

    def expire(self, _key, _seconds):
        return True

    def smembers(self, key):
        return self.values.get(key, set())

    def delete(self, *keys):
        for key in keys:
            self.values.pop(key, None)
        return len(keys)

    def eval(self, _script, _keys, key, token):
        if self.values.get(key) == token:
            self.values.pop(key, None)
            return 1
        return 0


class FakePipeline:
    def __init__(self, redis):
        self.redis = redis

    def sadd(self, key, value):
        self.redis.sadd(key, value)
        return self

    def expire(self, key, seconds):
        self.redis.expire(key, seconds)
        return self

    def execute(self):
        return [1, True]


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


def test_shared_coordinator_can_purge_only_one_users_indexed_entries():
    fake = FakeRedis()
    coordinator = SharedAnalysisCoordinator(
        "redis://test", cache_ttl_seconds=60, lock_ttl_seconds=30, client=fake,
    )
    user_key = ("metrics", "user-a", "dataset")
    other_key = ("metrics", "user-b", "dataset")
    coordinator.store(user_key, {"private": "a"})
    coordinator.store(other_key, {"private": "b"})
    coordinator.store_job("user-a", "job", {"private": "job-a"})
    coordinator.purge_user("user-a")
    assert coordinator.get(user_key) is None
    assert coordinator.get_job("user-a", "job") is None
    assert coordinator.get(other_key) == {"private": "b"}
