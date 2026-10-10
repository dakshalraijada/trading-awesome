import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from common import dump_entry  # noqa: E402
from trust import assess, label_applied_by_maintainer  # noqa: E402

NOW = dt.datetime(2026, 10, 10, tzinfo=dt.timezone.utc)
POLICY = {
    "min_account_age_days": {"new_entry": 90, "update": 30},
    "limits": {"max_open_submissions": 1, "max_submissions_per_30_days": 3},
    "anomalies": {"many_repos_no_followers": 200, "young_account_days": 180},
    "blocked_users": ["spammer"],
}


class FakeGitHub:
    """Stands in for github_api.GitHub with canned responses."""

    repo = "lentrade/trading-awesome"

    def __init__(self, *, created_days_ago=400, type_="User", repos=10, followers=5, merged=0,
                 open_items=(), recent=0, roles=None, events=()):
        self._user = {
            "created_at": (NOW - dt.timedelta(days=created_days_ago)).isoformat().replace("+00:00", "Z"),
            "type": type_, "public_repos": repos, "followers": followers,
        }
        self._merged, self._open, self._recent = merged, list(open_items), recent
        self._roles = roles or {}
        self._events = list(events)

    def user(self, login):
        return self._user

    def permission(self, login):
        return self._roles.get(login, "read")

    def search_count(self, query):
        if "is:merged" in query:
            return self._merged, []
        if "is:open" in query:
            return len(self._open), self._open
        return self._recent, []

    def issue_events(self, number):
        return self._events


class TrustTest(unittest.TestCase):
    def run_assess(self, gh, kind="new_entry", association="NONE", login="someone", **kw):
        return assess(gh, POLICY, login, association, kind=kind, now=NOW, **kw)

    def test_established_account_passes(self):
        self.assertTrue(self.run_assess(FakeGitHub()).ok)

    def test_young_account_rejected_for_new_entries(self):
        result = self.run_assess(FakeGitHub(created_days_ago=29))
        self.assertFalse(result.ok)
        self.assertIn("29 days old", result.errors[0])
        self.assertIn("2026-12-10", result.errors[0])  # created 2026-09-11 + 90 days

    def test_update_threshold_is_lower(self):
        self.assertTrue(self.run_assess(FakeGitHub(created_days_ago=45), kind="update").ok)
        self.assertFalse(self.run_assess(FakeGitHub(created_days_ago=20), kind="update").ok)

    def test_previous_merged_contribution_exempts_age(self):
        result = self.run_assess(FakeGitHub(created_days_ago=5, merged=1))
        self.assertTrue(result.ok)
        self.assertTrue(result.trusted)

    def test_bots_and_organizations_rejected(self):
        self.assertFalse(self.run_assess(FakeGitHub(type_="Organization")).ok)
        self.assertFalse(self.run_assess(FakeGitHub(type_="Bot")).ok)

    def test_blocklist(self):
        self.assertFalse(self.run_assess(FakeGitHub(), login="Spammer").ok)

    def test_rate_limits(self):
        self.assertFalse(self.run_assess(FakeGitHub(open_items=[{"number": 5}]), exclude_issue=6).ok)
        self.assertTrue(self.run_assess(FakeGitHub(open_items=[{"number": 6}]), exclude_issue=6).ok)
        self.assertFalse(self.run_assess(FakeGitHub(recent=4)).ok)
        self.assertTrue(self.run_assess(FakeGitHub(open_items=[{"number": 5}]), check_limits=False).ok)

    def test_soft_flags(self):
        result = self.run_assess(FakeGitHub(repos=577, followers=0))
        self.assertTrue(result.ok)
        self.assertTrue(result.flags)
        result = self.run_assess(FakeGitHub(created_days_ago=120, repos=0))
        self.assertTrue(result.ok)
        self.assertTrue(result.flags)

    def test_maintainers_skip_checks(self):
        result = self.run_assess(FakeGitHub(created_days_ago=1), association="OWNER")
        self.assertTrue(result.ok and result.maintainer)

    def test_override_label_must_come_from_maintainer(self):
        event = {"event": "labeled", "label": {"name": "maintainer-approved"}, "actor": {"login": "lentrade"}}
        gh = FakeGitHub(roles={"lentrade": "admin"}, events=[event])
        self.assertTrue(label_applied_by_maintainer(gh, 1, "maintainer-approved"))
        forged = dict(event, actor={"login": "random"})
        self.assertFalse(label_applied_by_maintainer(FakeGitHub(events=[forged]), 1, "maintainer-approved"))


class DumpTest(unittest.TestCase):
    def test_no_yaml_aliases_for_equal_dates(self):
        day = dt.date(2026, 10, 10)
        text = dump_entry({"name": "X", "added": day, "last_verified": day})
        self.assertNotIn("&", text)
        self.assertNotIn("*", text)
        self.assertIn("last_verified: 2026-10-10", text)


if __name__ == "__main__":
    unittest.main()
