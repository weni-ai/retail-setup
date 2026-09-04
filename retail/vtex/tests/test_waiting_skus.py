from django.test import SimpleTestCase

from retail.vtex.tests.fake_redis import FakeRedis
from retail.vtex.waiting_skus import WAITING_SKUS_TTL_SECONDS, WaitingSkusIndex


class WaitingSkusIndexTest(SimpleTestCase):
    def setUp(self):
        self.redis = FakeRedis()
        self.index = WaitingSkusIndex(redis_client=self.redis)

    def test_sadd_sets_ttl_on_new_key(self):
        self.index.sadd_waiting_sku("gaboulstore", "9")

        key = self.index.key_for("gaboulstore")
        self.assertEqual(self.redis.sets[key], {"9"})
        self.assertEqual(self.redis.ttls[key], WAITING_SKUS_TTL_SECONDS)

    def test_sadd_renews_ttl_when_sku_already_in_the_set(self):
        key = self.index.key_for("gaboulstore")
        self.redis.sets[key] = {"9"}
        self.redis.ttls[key] = 50_000

        self.index.sadd_waiting_sku("gaboulstore", "9")

        self.assertEqual(self.redis.ttls[key], WAITING_SKUS_TTL_SECONDS)
        self.assertEqual(self.redis.sets[key], {"9"})

    def test_sadd_renews_ttl_when_adding_another_sku(self):
        self.index.sadd_waiting_sku("gaboulstore", "9")
        key = self.index.key_for("gaboulstore")
        self.redis.ttls[key] = 50_000

        self.index.sadd_waiting_sku("gaboulstore", "12")

        self.assertEqual(self.redis.sets[key], {"9", "12"})
        self.assertEqual(self.redis.ttls[key], WAITING_SKUS_TTL_SECONDS)

    def test_sku_is_waiting_false_when_key_missing_and_rebuild_leaves_empty(self):
        called = []

        result = self.index.sku_is_waiting(
            "gaboulstore", "9", on_missing_key=lambda: called.append(True)
        )

        self.assertFalse(result)
        self.assertEqual(called, [True])

    def test_sku_is_waiting_rebuilds_then_checks_member(self):
        def rebuild():
            self.index.rebuild_for_account("gaboulstore", ["9", "12"])

        result = self.index.sku_is_waiting("gaboulstore", "9", on_missing_key=rebuild)

        self.assertTrue(result)
        key = self.index.key_for("gaboulstore")
        self.assertEqual(self.redis.ttls[key], WAITING_SKUS_TTL_SECONDS)

    def test_sku_is_waiting_false_when_key_exists_but_sku_not_member(self):
        self.index.rebuild_for_account("gaboulstore", ["12"])

        result = self.index.sku_is_waiting("gaboulstore", "9")

        self.assertFalse(result)

    def test_rebuild_replaces_stale_members_and_renews_ttl(self):
        key = self.index.key_for("gaboulstore")
        self.redis.sets[key] = {"orphan"}
        self.redis.ttls[key] = 10

        self.index.rebuild_for_account("gaboulstore", ["9"])

        self.assertEqual(self.redis.sets[key], {"9"})
        self.assertEqual(self.redis.ttls[key], WAITING_SKUS_TTL_SECONDS)

    def test_rebuild_deletes_key_when_no_pending_skus(self):
        key = self.index.key_for("gaboulstore")
        self.redis.sets[key] = {"9"}
        self.redis.ttls[key] = WAITING_SKUS_TTL_SECONDS

        self.index.rebuild_for_account("gaboulstore", [])

        self.assertNotIn(key, self.redis.sets)
