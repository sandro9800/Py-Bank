import os
import sqlite3
import tempfile
import unittest

import bank as bank_module
from bank import Bank, BankError, format_cents, parse_amount

# PBKDF2 with 600k iterations is deliberately slow; use a tiny count in tests.
bank_module.PBKDF2_ITERATIONS = 1_000


class BankTestCase(unittest.TestCase):
    def setUp(self):
        self.bank = Bank(":memory:")
        self.addCleanup(self.bank.close)

    def make_user(self, name="alice", password="correct-horse"):
        user_id = self.bank.register(name, password)
        return user_id, self.bank.get_accounts(user_id)[0]["id"]


class TestParseAmount(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(parse_amount("10"), 1000)
        self.assertEqual(parse_amount("10.5"), 1050)
        self.assertEqual(parse_amount(" 0.01 "), 1)

    def test_invalid(self):
        for text in ("abc", "", "nan", "NaN", "inf", "-5", "0", "1.234", "1e50"):
            with self.subTest(text=text):
                with self.assertRaises(BankError):
                    parse_amount(text)

    def test_format(self):
        self.assertEqual(format_cents(15000), "150.00")
        self.assertEqual(format_cents(5), "0.05")


class TestUsers(BankTestCase):
    def test_register_and_login(self):
        user_id = self.bank.register("alice", "correct-horse")
        user = self.bank.login("alice", "correct-horse")
        self.assertEqual(user, {"id": user_id, "username": "alice"})

    def test_password_is_hashed(self):
        self.bank.register("alice", "correct-horse")
        stored = self.bank.con.execute("SELECT password_hash FROM users").fetchone()[0]
        self.assertTrue(stored.startswith("pbkdf2_sha256$"))
        self.assertNotIn("correct-horse", stored)

    def test_same_password_gets_different_hash(self):
        self.bank.register("alice", "correct-horse")
        self.bank.register("bobby", "correct-horse")
        hashes = [r[0] for r in self.bank.con.execute("SELECT password_hash FROM users")]
        self.assertNotEqual(hashes[0], hashes[1])

    def test_duplicate_username_is_case_insensitive(self):
        self.bank.register("alice", "correct-horse")
        with self.assertRaises(BankError):
            self.bank.register("ALICE", "another-password")

    def test_rejects_bad_username_and_short_password(self):
        with self.assertRaises(BankError):
            self.bank.register("a", "correct-horse")
        with self.assertRaises(BankError):
            self.bank.register("bad name!", "correct-horse")
        with self.assertRaises(BankError):
            self.bank.register("alice", "short")

    def test_wrong_password_and_unknown_user_look_the_same(self):
        self.bank.register("alice", "correct-horse")
        with self.assertRaises(BankError) as wrong:
            self.bank.login("alice", "wrong-password")
        with self.assertRaises(BankError) as unknown:
            self.bank.login("nobody", "wrong-password")
        self.assertEqual(str(wrong.exception), str(unknown.exception))

    def test_login_result_has_no_password_data(self):
        self.bank.register("alice", "correct-horse")
        self.assertEqual(set(self.bank.login("alice", "correct-horse")), {"id", "username"})

    def test_new_user_gets_default_account_with_starting_balance(self):
        _, account_id = self.make_user()
        self.assertEqual(self.bank.get_account(account_id)["balance_cents"], 15000)


class TestTransfers(BankTestCase):
    def setUp(self):
        super().setUp()
        self.alice_id, self.alice_acc = self.make_user("alice")
        self.bob_id, self.bob_acc = self.make_user("bobby")

    def balance(self, account_id):
        return self.bank.get_account(account_id)["balance_cents"]

    def test_transfer_moves_money_and_records_it(self):
        self.bank.transfer(self.alice_id, self.alice_acc, self.bob_acc, 2550, "lunch")
        self.assertEqual(self.balance(self.alice_acc), 15000 - 2550)
        self.assertEqual(self.balance(self.bob_acc), 15000 + 2550)
        txns = self.bank.get_transactions(self.alice_id)
        self.assertEqual(len(txns), 1)
        self.assertEqual(txns[0]["description"], "lunch")
        self.assertEqual(txns[0]["dest_username"], "bobby")

    def test_total_money_is_conserved(self):
        self.bank.transfer(self.alice_id, self.alice_acc, self.bob_acc, 1234)
        self.bank.transfer(self.bob_id, self.bob_acc, self.alice_acc, 99)
        self.assertEqual(self.balance(self.alice_acc) + self.balance(self.bob_acc), 30000)

    def test_insufficient_funds_changes_nothing(self):
        with self.assertRaises(BankError):
            self.bank.transfer(self.alice_id, self.alice_acc, self.bob_acc, 15001)
        self.assertEqual(self.balance(self.alice_acc), 15000)
        self.assertEqual(self.balance(self.bob_acc), 15000)
        self.assertEqual(self.bank.get_transactions(self.alice_id), [])

    def test_can_spend_exact_balance(self):
        self.bank.transfer(self.alice_id, self.alice_acc, self.bob_acc, 15000)
        self.assertEqual(self.balance(self.alice_acc), 0)

    def test_rejects_non_positive_and_non_integer_amounts(self):
        for bad in (0, -100, 1.5, True, "10"):
            with self.subTest(amount=bad):
                with self.assertRaises(BankError):
                    self.bank.transfer(self.alice_id, self.alice_acc, self.bob_acc, bad)
        self.assertEqual(self.balance(self.alice_acc), 15000)

    def test_cannot_spend_from_someone_elses_account(self):
        with self.assertRaises(BankError):
            self.bank.transfer(self.alice_id, self.bob_acc, self.alice_acc, 100)
        self.assertEqual(self.balance(self.bob_acc), 15000)

    def test_same_account_and_missing_accounts(self):
        with self.assertRaises(BankError):
            self.bank.transfer(self.alice_id, self.alice_acc, self.alice_acc, 100)
        with self.assertRaises(BankError):
            self.bank.transfer(self.alice_id, self.alice_acc, 9999, 100)
        with self.assertRaises(BankError):
            self.bank.transfer(self.alice_id, 9999, self.bob_acc, 100)

    def test_empty_description_gets_default(self):
        self.bank.transfer(self.alice_id, self.alice_acc, self.bob_acc, 100, "  ")
        self.assertEqual(
            self.bank.get_transactions(self.alice_id)[0]["description"],
            "personal transfer",
        )

    def test_transactions_are_newest_first_and_visible_to_both_sides(self):
        self.bank.transfer(self.alice_id, self.alice_acc, self.bob_acc, 100, "first")
        self.bank.transfer(self.alice_id, self.alice_acc, self.bob_acc, 200, "second")
        descriptions = [t["description"] for t in self.bank.get_transactions(self.bob_id)]
        self.assertEqual(descriptions, ["second", "first"])


class TestAccounts(BankTestCase):
    def test_open_account_and_duplicate_name(self):
        user_id, _ = self.make_user()
        self.bank.open_account(user_id, "savings")
        self.assertEqual(len(self.bank.get_accounts(user_id)), 2)
        with self.assertRaises(BankError):
            self.bank.open_account(user_id, "savings")

    def test_open_account_for_missing_user(self):
        with self.assertRaises(BankError):
            self.bank.open_account(999, "savings")


class TestLegacyDatabase(unittest.TestCase):
    def test_old_format_is_rejected_with_clear_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "old.db")
            con = sqlite3.connect(path)
            con.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, password TEXT)")
            con.commit()
            con.close()
            with self.assertRaises(RuntimeError):
                Bank(path)


if __name__ == "__main__":
    unittest.main()
