from __future__ import annotations

import sqlite3
import unittest

import auth
import techdb_client


class AuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        auth.ensure_auth_schema(self.conn)
        auth.seed_users(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_four_named_accounts(self) -> None:
        names = [row["name"] for row in auth.list_users(self.conn)]
        self.assertEqual(names, ["Alex", "Dios", "Gary", "Wayne"])
        wayne = next(row for row in auth.list_users(self.conn) if row["name"] == "Wayne")
        self.assertEqual(wayne["role"], "admin")

    def test_login_and_search_log_are_named(self) -> None:
        session = auth.login(self.conn, "Wayne", auth.DEFAULT_PASSWORD)
        user = auth.resolve_token(self.conn, session["token"])
        self.assertEqual(user["name"], "Wayne")
        auth.log_search(self.conn, user, "PU 樹脂", material_group="樹脂", result_count=3)
        logs = auth.list_search_logs(self.conn, user)
        self.assertEqual(logs[0]["display_name"], "Wayne")
        self.assertEqual(logs[0]["query"], "PU 樹脂")

    def test_user_can_change_own_password(self) -> None:
        session = auth.login(self.conn, "Alex", auth.DEFAULT_PASSWORD)
        user = auth.resolve_token(self.conn, session["token"])
        auth.change_password(self.conn, user, auth.DEFAULT_PASSWORD, "NewPass-9001", keep_token=session["token"])
        self.assertEqual(auth.resolve_token(self.conn, session["token"])["name"], "Alex")
        with self.assertRaises(PermissionError):
            auth.login(self.conn, "Alex", auth.DEFAULT_PASSWORD)
        again = auth.login(self.conn, "Alex", "NewPass-9001")
        self.assertEqual(again["user"]["name"], "Alex")


class CompactMaterialTests(unittest.TestCase):
    def test_compact_keeps_identity_fields(self) -> None:
        compact = techdb_client.compact_material(
            {
                "id": 6825,
                "name": "LUX220",
                "supplier": "安鋒",
                "material_group": "樹脂",
                "attributes": {"內部原料編碼": "WR22028"},
            }
        )
        self.assertEqual(compact["id"], 6825)
        self.assertNotIn("attributes", compact)


if __name__ == "__main__":
    unittest.main()
