"""DEV-59 / D-142: P-FLOW-001 narrowed by content. The database is replaced by small doubles.

The pure part (normalisation, fingerprints, the comparison) runs anywhere. The ledger queries and the
wiring in execute_call need the Gateway image (psycopg) and are skipped without it.
"""
from __future__ import annotations

import sys
import time
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "gateway"))
from app import flow_fingerprint as ff  # noqa: E402

try:
    from app import classify, core, endpoint_plane  # noqa: E402
except ImportError:  # psycopg and friends only exist in the gateway image
    core = None

SALT = b"s" * 16
READ = ("고객 김민수의 대출 상환 일정은 매월 25일이며 연체 시 가산 이자가 부과된다. "
        "담당 부서는 여신관리팀이고 심사 의견서는 별도 보관함에 있다.")
SENTENCE = "고객 김민수의 대출 상환 일정은 매월 25일이며 연체 시 가산 이자가 부과된다."
UNRELATED = "Fix the flaky login test, then bump the CI timeout to twenty minutes for the nightly job."


def read_row(server, text, salt=SALT):
    shingles, identifiers = ff.fingerprint(text, salt)
    return {"server_id": server, "salt": salt, "key_id": ff.KEY_ID, "shingles": shingles, "identifiers": identifiers}


def unchecked_row(server):
    return {"server_id": server, "salt": None, "key_id": None, "shingles": None, "identifiers": None}


class NormaliseTest(unittest.TestCase):
    def test_spacing_case_width_and_zero_width_characters_do_not_change_the_text(self):
        self.assertEqual(ff.squash("Hello,  WORLD 12"), ff.squash("ｈｅｌｌｏ​ world\n１２"))

    def test_leaf_text_reads_every_value_at_any_depth_and_no_keys_by_default(self):
        deep = {"a": [{"b": {"c": ["x"] * 300 + ["last"]}}], "n": 4012345678901, "flag": True}
        text = ff.leaf_text(deep)
        self.assertIn("last", text)
        self.assertIn("4012345678901", text)
        self.assertNotIn("flag", text)
        self.assertIn("flag", ff.leaf_text(deep, keys=True))


class FingerprintTest(unittest.TestCase):
    def test_only_hashes_come_out_and_the_salt_changes_them(self):
        a = ff.fingerprint(READ, SALT)
        self.assertTrue(a[0] and all(isinstance(value, int) for value in a[0]))
        self.assertEqual(a, ff.fingerprint(READ, SALT))
        self.assertNotEqual(a, ff.fingerprint(READ, b"t" * 16))
        self.assertEqual(len(a[0]), len(ff.squash(READ)) - ff.SHINGLE + 1)

    def test_a_text_over_the_limit_is_refused_before_it_is_hashed(self):
        with self.assertRaises(ValueError):
            ff.fingerprint("가" * 50, SALT, limit=10)
        self.assertEqual(ff.fingerprint("가" * 50, SALT, limit=50)[1], [])
        with self.assertRaises(ValueError):
            ff.fingerprint(" ".join(str(1000000000 + n) for n in range(20)), SALT, limit=10)

    def test_identifiers_shorter_than_a_shingle_are_still_taken(self):
        self.assertEqual(len(ff.fingerprint("연락처 010-1234-5678 입니다", SALT)[1]), 1)
        self.assertEqual(len(ff.fingerprint("kim.minsu@corp.example.com", SALT)[1]), 1)
        self.assertEqual(len(ff.fingerprint("card 4111 1111 1111 1111", SALT)[1]), 1)
        self.assertEqual(ff.fingerprint("at 2026-10-20 10:00:00 and 1.5", SALT)[1], [])

    def test_hostile_text_is_hashed_in_linear_time(self):
        started = time.perf_counter()
        for text in ("a" * 65000, "a." * 32000, "1" * 64999 + ":", "x" * 60 + "@" + "a." * 30000):
            ff.fingerprint(text, SALT)
        self.assertLess(time.perf_counter() - started, 3.0)


class NarrowTest(unittest.TestCase):
    def narrow(self, rows, outbound):
        return ff.narrow(rows, outbound)

    def test_the_same_sentence_stays_a_flow_source(self):
        sources, seen = self.narrow([read_row("filesystem", READ)], "이슈 본문: " + SENTENCE)
        self.assertEqual((sources, seen), (["filesystem"], {"filesystem": ff.MATCHED}))

    def test_spacing_and_case_variants_stay_a_flow_source(self):
        english = "The borrower repays on the 25th of every month and late payment adds a surcharge."
        for text, outbound in ((READ, "  ".join(SENTENCE.split(" "))),
                               (READ, SENTENCE.replace(" ", "")),
                               (english, english.upper().replace(" ", "\n")),
                               (english, english.replace(" ", "​ "))):
            with self.subTest(outbound=outbound[:20]):
                self.assertEqual(self.narrow([read_row("filesystem", text)], outbound)[0], ["filesystem"])

    def test_an_unrelated_write_is_not_a_flow_source_and_says_why(self):
        sources, seen = self.narrow([read_row("filesystem", READ)], UNRELATED)
        self.assertEqual((sources, seen), ([], {"filesystem": ff.MISMATCH}))
        self.assertEqual(ff.MISMATCH, "열람 후 다른 서버 호출(내용 불일치)")

    def test_a_short_shared_phrase_is_below_the_threshold(self):
        phrase = "연체 시 가산 이자가 부과된다"  # 13 characters once squashed: no shingle at all
        self.assertEqual(self.narrow([read_row("filesystem", READ)], "정책 메모. " + phrase)[0], [])
        run = ff.squash(READ)[:ff.SHINGLE + ff.MIN_SHARED - 2]  # one shingle short of the threshold
        self.assertEqual(self.narrow([read_row("filesystem", READ)], "메모 " + run)[0], [])
        run = ff.squash(READ)[:ff.SHINGLE + ff.MIN_SHARED - 1]
        self.assertEqual(self.narrow([read_row("filesystem", READ)], "메모 " + run)[0], ["filesystem"])

    def test_a_short_identifier_alone_is_the_same_content(self):
        rows = [read_row("crm", "고객 연락처는 010-1234-5678 이고 메일은 kim@corp.example.com 이다.")]
        self.assertEqual(self.narrow(rows, "전화 01012345678 로 회신")[0], ["crm"])
        self.assertEqual(self.narrow(rows, "mail KIM@corp.example.com")[0], ["crm"])
        self.assertEqual(self.narrow(rows, "전화 010-9999-0000 로 회신")[0], [])

    def test_a_read_that_could_not_be_compared_stays_a_flow_source(self):
        sources, seen = self.narrow([unchecked_row("filesystem")], UNRELATED)
        self.assertEqual((sources, seen), (["filesystem"], {"filesystem": ff.UNCHECKED}))

    def test_servers_are_judged_separately_and_by_all_their_reads(self):
        rows = [read_row("a", READ), read_row("b", UNRELATED), read_row("b", READ), read_row("c", UNRELATED),
                unchecked_row("c"), read_row("d", UNRELATED), read_row("d", "다른 문서의 내용은 이 호출과 무관하다.")]
        sources, seen = self.narrow(rows, SENTENCE)
        self.assertEqual(sources, ["a", "b", "c"])
        self.assertEqual(seen, {"a": ff.MATCHED, "b": ff.MATCHED, "c": ff.UNCHECKED, "d": ff.MISMATCH})

    def test_reads_stored_under_different_salts_are_each_compared_under_their_own(self):
        rows = [read_row("a", READ, b"1" * 16), read_row("b", READ, b"2" * 16)]
        self.assertEqual(self.narrow(rows, SENTENCE)[0], ["a", "b"])

    def test_a_fingerprint_made_under_another_key_cannot_be_compared(self):
        row = {**read_row("a", READ), "key_id": "00000000"}
        self.assertEqual(self.narrow([row], UNRELATED), (["a"], {"a": ff.UNCHECKED}))

    def test_any_error_answers_with_every_server(self):
        rows = [read_row("a", UNRELATED), {"server_id": "b", "salt": SALT, "key_id": ff.KEY_ID, "shingles": 5, "identifiers": []}]
        sources, seen = self.narrow(rows, SENTENCE)
        self.assertEqual((sources, seen), (["a", "b"], {"a": ff.UNCHECKED, "b": ff.UNCHECKED}))

    def test_a_write_with_nothing_to_send_matches_nothing(self):
        self.assertEqual(self.narrow([read_row("a", READ)], "")[0], [])


class Ledger:
    """What the Gateway's tables hold, enough for the two queries this feature makes."""

    def __init__(self, fail_insert=False):
        self.fingerprints, self.executed, self.fail_insert = [], [], fail_insert

    async def fetch_one(self, query, params=()):
        assert "FROM flow_fingerprints" in query
        mine = [row for row in self.fingerprints if row["user_token"] == params[0]]
        return {"salt": mine[-1]["salt"]} if mine else None

    async def execute(self, query, params=()):
        self.executed.append((query, params))
        if query.startswith("INSERT"):
            if self.fail_insert:
                raise RuntimeError("database down")
            token, server, decision, salt, key_id, shingles, identifiers, _ = params
            self.fingerprints.append({"user_token": token, "server_id": server, "decision_id": decision,
                                      "salt": salt, "key_id": key_id, "shingles": shingles,
                                      "identifiers": identifiers})
        return 1

    def reads(self, *reads):
        """The decisions rows of important reads, joined to whichever fingerprints exist."""
        by_decision = {row["decision_id"]: row for row in self.fingerprints}
        return [{"server_id": server, **{k: (by_decision[decision][k] if decision in by_decision else None)
                                         for k in ("salt", "key_id", "shingles", "identifiers")}}
                for server, decision in reads]


@unittest.skipUnless(core, "Gateway image: psycopg is not installed here")
class LedgerTest(unittest.IsolatedAsyncioTestCase):
    WRITE = None

    def setUp(self):
        self.write = classify.Classification("github", "create_issue", "w", "w")

    async def sources(self, ledger, reads, outbound="x", mode="content", **kwargs):
        with patch.object(core.db, "fetch_all", AsyncMock(return_value=ledger.reads(*reads))), \
                patch.object(core, "FLOW_MATCH_MODE", mode):
            observed = {}
            found = await core._flow_sources("emp", "github", self.write, outbound_text=outbound, observed=observed, **kwargs)
        return found, observed

    async def remember(self, ledger, decision, server, text):
        result = {"content": [{"type": "text", "text": text}], "is_error": False}
        with patch.object(core.db, "fetch_one", ledger.fetch_one), patch.object(core.db, "execute", ledger.execute):
            await core._remember_flow("emp", server, decision, result)

    async def test_the_same_sentence_is_blocked_and_an_unrelated_write_is_recorded(self):
        ledger = Ledger()
        await self.remember(ledger, 11, "filesystem", READ)
        self.assertEqual(await self.sources(ledger, [("filesystem", 11)], SENTENCE),
                         (["filesystem"], {"filesystem": ff.MATCHED}))
        self.assertEqual(await self.sources(ledger, [("filesystem", 11)], UNRELATED),
                         ([], {"filesystem": ff.MISMATCH}))
        self.assertEqual((await self.sources(ledger, [("filesystem", 11)], SENTENCE.upper().replace(" ", "")))[0],
                         ["filesystem"])

    async def test_the_default_mode_blocks_an_unrelated_write_as_before_and_only_records_the_comparison(self):
        ledger = Ledger()
        await self.remember(ledger, 11, "filesystem", READ)
        self.assertEqual(await self.sources(ledger, [("filesystem", 11)], UNRELATED, mode="coarse"),
                         (["filesystem"], {"filesystem": ff.MISMATCH}))
        self.assertEqual(await self.sources(ledger, [("filesystem", 11)], SENTENCE, mode="coarse"),
                         (["filesystem"], {"filesystem": ff.MATCHED}))
        self.assertEqual(await self.sources(ledger, [("filesystem", 11), ("postgres", 12)], UNRELATED, mode="coarse"),
                         (["filesystem", "postgres"], {"filesystem": ff.MISMATCH, "postgres": ff.UNCHECKED}))

    def test_only_the_word_content_turns_the_narrowing_on(self):
        for value in (None, "", "coarse", "narrow", "true", "1", "contents"):
            self.assertEqual(core._flow_match_mode(value), "coarse", value)
        for value in ("content", " Content ", "CONTENT"):
            self.assertEqual(core._flow_match_mode(value), "content", value)

    async def test_a_read_stored_under_another_pepper_stays_a_source_in_content_mode(self):
        ledger = Ledger()
        await self.remember(ledger, 11, "filesystem", READ)
        ledger.fingerprints[0]["key_id"] = "00000000"
        self.assertEqual(await self.sources(ledger, [("filesystem", 11)], UNRELATED),
                         (["filesystem"], {"filesystem": ff.UNCHECKED}))

    async def test_without_the_call_text_every_server_in_the_window_is_a_source(self):
        ledger = Ledger()
        await self.remember(ledger, 11, "filesystem", READ)
        with patch.object(core.db, "fetch_all", AsyncMock(return_value=ledger.reads(("filesystem", 11)))):
            self.assertEqual(await core._flow_sources("emp", "github", self.write), ["filesystem"])

    async def test_a_failed_store_leaves_the_read_a_coarse_source_and_does_not_raise(self):
        ledger = Ledger(fail_insert=True)
        await self.remember(ledger, 11, "filesystem", READ)
        self.assertEqual(ledger.fingerprints, [])
        self.assertEqual(await self.sources(ledger, [("filesystem", 11)], UNRELATED),
                         (["filesystem"], {"filesystem": ff.UNCHECKED}))

    async def test_a_result_too_large_to_fingerprint_stays_a_coarse_source(self):
        ledger = Ledger()
        with patch.object(ff, "MAX_HASHES", 50):
            await self.remember(ledger, 11, "filesystem", READ * 3)
        self.assertFalse([q for q, _ in ledger.executed if q.startswith("INSERT")])
        self.assertEqual((await self.sources(ledger, [("filesystem", 11)], UNRELATED))[0], ["filesystem"])

    async def test_a_failing_comparison_answers_with_the_coarse_mark(self):
        ledger = Ledger()
        await self.remember(ledger, 11, "filesystem", READ)
        with patch.object(ff, "fingerprint", Mock(side_effect=RuntimeError("boom"))):
            self.assertEqual((await self.sources(ledger, [("filesystem", 11)], UNRELATED))[0], ["filesystem"])

    async def test_the_text_is_never_stored_and_the_principal_keeps_one_salt(self):
        ledger = Ledger()
        await self.remember(ledger, 11, "filesystem", READ)
        await self.remember(ledger, 12, "postgres", UNRELATED)
        stored = [(q, p) for q, p in ledger.executed if q.startswith("INSERT")]
        self.assertEqual(len(stored), 2)
        for _, params in stored:
            token, server, decision, salt, key_id, shingles, identifiers, minutes = params
            self.assertIsInstance(salt, bytes)
            self.assertEqual(key_id, ff.KEY_ID)
            self.assertTrue(all(isinstance(v, int) for v in shingles + identifiers))
            self.assertEqual(minutes, core.CHAIN_WINDOW_MINUTES)
            for value in params:
                for word in ("김민수", "여신관리팀", "flaky", "login", "text"):
                    self.assertNotIn(word, str(value))
        self.assertEqual(stored[0][1][3], stored[1][1][3])
        self.assertIn("ON CONFLICT (decision_id) DO NOTHING", stored[0][0])
        self.assertTrue(any(q.startswith("DELETE FROM flow_fingerprints WHERE expires_at") for q, _ in ledger.executed))

    async def test_the_join_asks_for_unexpired_fingerprints_of_other_servers_only(self):
        fetch = AsyncMock(return_value=[])
        with patch.object(core.db, "fetch_all", fetch):
            await core._flow_sources("emp", "github", self.write, outbound_text="x")
        query, params = fetch.await_args.args
        self.assertIn("server_id<>%s", query)
        self.assertIn("f.expires_at > now()", query)
        self.assertEqual(params[:2], ("emp", "github"))


@unittest.skipUnless(core, "Gateway image: psycopg is not installed here")
class WiringTest(unittest.IsolatedAsyncioTestCase):
    """execute_call hands the call's text to the comparison and keeps what an important read released."""

    PAYLOAD = {"server_id": "github", "tool": "create_issue", "user_token": "emp",
               "arguments": {"title": "회의록", "body": "이슈 본문: " + SENTENCE}}

    async def run_call(self, *, action="w", data_class="important", reads=(), policy=None, result=None, mode="content"):
        cls = SimpleNamespace(action=action, base_action=action, data_class=data_class, destinations=[], resources=[],
                              dlp=[], notes=[], restrictable=[], primary=SimpleNamespace(id="asset", kind="file", owner_department=None),
                              summary=lambda: "unit")
        async def fetch(query, params=()):
            return {"role": "employee", "status": "active", "synthetic": True} if "principals" in query else None
        async def record(event, laps):
            return {**event, "decision_id": 7}
        captured = {}
        async def judge(policy_input):
            captured["input"] = policy_input
            return policy or {"decision": "Allow", "policy_id": "P-ALLOW-001", "reason": "unit"}
        payload = {**self.PAYLOAD}
        remember = AsyncMock()
        released = result if result is not None else {"content": [{"type": "text", "text": READ}], "is_error": False}
        changes = [(core.db, {"fetch_one": AsyncMock(side_effect=fetch), "fetch_all": AsyncMock(return_value=list(reads)),
                              "execute": AsyncMock(return_value=1)}),
                   (core.registry, {"server": Mock(return_value={"endpoint": "http://internal"}),
                                    "allowed_principals": Mock(return_value=None), "catalog_version": Mock(return_value="test")}),
                   (core.classify, {"classify": Mock(return_value=cls), "apply_restrictions": Mock(return_value=({}, [])),
                                    "remember_navigation": Mock()}),
                   (endpoint_plane, {"managed_failure": AsyncMock(return_value=None),
                                     "shadow_count_for": AsyncMock(return_value=0), "shadow_listener_count_for": AsyncMock(return_value=0)}),
                   (core.pac, {"build": AsyncMock(return_value={}), "digest": Mock(return_value="unit")}),
                   (core.consent, {"missing": AsyncMock(return_value=None)}),
                   (core.privacy, {"analyze": AsyncMock(return_value=[])}),
                   (core.secret_scan, {"labels": AsyncMock(return_value=[])}),
                   (core, {"policy_ledger": AsyncMock(), "_reserve_call": AsyncMock(return_value={}),
                           "_privacy_ignore": Mock(return_value=None), "_contract": AsyncMock(return_value={}),
                           "_relationship_scope": AsyncMock(return_value={}), "_sequence_flags": AsyncMock(return_value=[]),
                           "_policy": judge, "enforcement_mode": AsyncMock(return_value="enforce"),
                           "_decision_payload": record, "_call_upstream": AsyncMock(return_value=released),
                           "_inspected_result": AsyncMock(return_value=(released, [])), "_remember_flow": remember,
                           "FLOW_MATCH_MODE": mode})]
        with ExitStack() as stack:
            for target, attributes in changes:
                for name, value in attributes.items():
                    stack.enter_context(patch.object(target, name, value))
            response = await core.execute_call(payload)
        return response, captured.get("input"), remember

    BLOCK = {"decision": "Block", "policy_id": "P-FLOW-001", "reason": "unit"}

    async def test_content_mode_narrows_the_sources_and_the_record_says_what_was_seen(self):
        _, seen, _ = await self.run_call(reads=[read_row("filesystem", READ)], policy=self.BLOCK)
        self.assertEqual(seen["request"]["flow_sources"], ["filesystem"])
        self.assertEqual(seen["request"]["flow_observed"], {"filesystem": ff.MATCHED})
        self.assertEqual(seen["request"]["flow_match_mode"], "content")
        _, seen, _ = await self.run_call(reads=[read_row("filesystem", UNRELATED)], policy=self.BLOCK)
        self.assertEqual(seen["request"]["flow_sources"], [])
        self.assertEqual(seen["request"]["flow_observed"], {"filesystem": ff.MISMATCH})

    async def test_the_default_mode_keeps_an_unrelated_write_a_flow_source_and_records_the_mismatch(self):
        _, seen, _ = await self.run_call(reads=[read_row("filesystem", UNRELATED)], policy=self.BLOCK, mode="coarse")
        self.assertEqual(seen["request"]["flow_sources"], ["filesystem"])
        self.assertEqual(seen["request"]["flow_observed"], {"filesystem": ff.MISMATCH})
        self.assertEqual(seen["request"]["flow_match_mode"], "coarse")
        _, seen, _ = await self.run_call(reads=[read_row("filesystem", READ)], policy=self.BLOCK, mode="coarse")
        self.assertEqual((seen["request"]["flow_sources"], seen["request"]["flow_observed"]),
                         (["filesystem"], {"filesystem": ff.MATCHED}))

    async def test_a_read_without_a_stored_fingerprint_still_marks_the_call(self):
        for mode in ("content", "coarse"):
            _, seen, _ = await self.run_call(reads=[unchecked_row("filesystem")], policy=self.BLOCK, mode=mode)
            self.assertEqual(seen["request"]["flow_sources"], ["filesystem"])
            self.assertEqual(seen["request"]["flow_observed"], {"filesystem": ff.UNCHECKED})

    async def test_an_important_read_keeps_what_it_released_after_its_decision_is_recorded(self):
        response, _, remember = await self.run_call(action="r")
        remember.assert_awaited_once()
        self.assertEqual(remember.await_args.args[:3], ("emp", "github", 7))
        self.assertEqual(remember.await_args.args[3]["content"][0]["text"], READ)
        self.assertEqual(response["decision_id"], 7)

    async def test_other_calls_keep_nothing(self):
        for action, data_class in (("r", "public"), ("r", "nonimportant"), ("w", "important")):
            with self.subTest(action=action, data_class=data_class):
                _, _, remember = await self.run_call(action=action, data_class=data_class)
                remember.assert_not_awaited()
        _, _, remember = await self.run_call(action="r", policy={"decision": "Block", "policy_id": "P-X", "reason": "unit"})
        remember.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
