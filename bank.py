"""Core banking logic for PyBank: users, accounts and money transfers (SQLite).

Design notes
------------
* Money is stored as integer cents, never as floats.
* Passwords are stored as salted PBKDF2-HMAC-SHA256 hashes, never in plain text.
* Every write runs inside an explicit ``BEGIN IMMEDIATE`` transaction, so a
  transfer either fully happens or not at all, and two programs using the same
  database file cannot overdraw an account at the same time.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import sqlite3
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from functools import lru_cache

PBKDF2_ITERATIONS = 600_000
STARTING_BALANCE_CENTS = 15_000  # demo money: every new account starts with 150.00
DEFAULT_DESCRIPTION = "personal transfer"
MAX_DESCRIPTION_LENGTH = 200
MAX_ACCOUNT_NAME_LENGTH = 50
MAX_AMOUNT_CENTS = 10**12
MIN_PASSWORD_LENGTH = 8
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,32}$")


class BankError(ValueError):
    """Raised for any rule violation (bad input, insufficient funds, ...)."""


# --------------------------------------------------------------------------
# Passwords
# --------------------------------------------------------------------------
def _hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt if salt is not None else os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt_hex, hash_hex = stored.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), hash_hex)


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    # Verified when the username does not exist, so a failed login takes about
    # the same time whether or not the user exists.
    return _hash_password("not-a-real-password")


# --------------------------------------------------------------------------
# Money helpers
# --------------------------------------------------------------------------
def parse_amount(text: str) -> int:
    """Convert user input such as '12.50' to integer cents (1250)."""
    try:
        value = Decimal(str(text).strip())
    except InvalidOperation:
        raise BankError("invalid amount") from None
    if not value.is_finite():
        raise BankError("invalid amount")
    if value <= 0:
        raise BankError("amount must be greater than zero")
    cents = value * 100
    if cents != cents.to_integral_value():
        raise BankError("amount can have at most 2 decimal places")
    cents = int(cents)
    if cents > MAX_AMOUNT_CENTS:
        raise BankError("amount is too large")
    return cents


def format_cents(cents: int) -> str:
    """Format integer cents as '12.50'."""
    sign = "-" if cents < 0 else ""
    cents = abs(int(cents))
    return f"{sign}{cents // 100}.{cents % 100:02d}"


# --------------------------------------------------------------------------
# Bank
# --------------------------------------------------------------------------
class Bank:
    def __init__(self, db_path: str = "bank.db"):
        self.db_path = db_path
        # isolation_level=None -> autocommit; transactions are explicit below.
        self.con = sqlite3.connect(db_path, isolation_level=None)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys = ON")
        try:
            self._setup()
        except Exception:
            self.con.close()
            raise

    def __enter__(self) -> "Bank":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    # ----- internals -----
    @contextmanager
    def _transaction(self):
        """Run a block atomically; roll back if it raises."""
        self.con.execute("BEGIN IMMEDIATE")
        try:
            yield self.con.cursor()
        except BaseException:
            self.con.execute("ROLLBACK")
            raise
        else:
            self.con.execute("COMMIT")

    def _columns(self, table: str) -> set[str]:
        rows = self.con.execute(f"PRAGMA table_info({table})").fetchall()
        return {row["name"] for row in rows}

    def _setup(self) -> None:
        if "balance" in self._columns("accounts") or "password" in self._columns("users"):
            raise RuntimeError(
                f"{self.db_path} uses the old database format (float balances, "
                "plain-text passwords). Move or delete it and start again."
            )
        cur = self.con.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT    NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT    NOT NULL
            )
            """
        )
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS accounts (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT    NOT NULL,
                user_id       INTEGER NOT NULL REFERENCES users(id),
                balance_cents INTEGER NOT NULL DEFAULT {STARTING_BALANCE_CENTS}
                              CHECK (balance_cents >= 0),
                UNIQUE (name, user_id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id              INTEGER  PRIMARY KEY AUTOINCREMENT,
                src_account_id  INTEGER  NOT NULL REFERENCES accounts(id),
                dest_account_id INTEGER  NOT NULL REFERENCES accounts(id),
                amount_cents    INTEGER  NOT NULL CHECK (amount_cents > 0),
                description     TEXT     NOT NULL DEFAULT 'personal transfer',
                created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_accounts_user ON accounts(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_txn_src ON transactions(src_account_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_txn_dest ON transactions(dest_account_id)")

    @staticmethod
    def _insert_account(cur: sqlite3.Cursor, user_id: int, name: str) -> int:
        cur.execute(
            "INSERT INTO accounts (name, user_id, balance_cents) VALUES (?, ?, ?)",
            (name, user_id, STARTING_BALANCE_CENTS),
        )
        return cur.lastrowid

    # ----- users -----
    def register(self, username: str, password: str) -> int:
        username = (username or "").strip()
        password = password or ""
        if not USERNAME_RE.match(username):
            raise BankError(
                "username must be 3-32 characters: letters, digits or underscore"
            )
        if len(password) < MIN_PASSWORD_LENGTH:
            raise BankError(
                f"password must be at least {MIN_PASSWORD_LENGTH} characters"
            )

        password_hash = _hash_password(password)  # slow, so done before locking
        try:
            with self._transaction() as cur:
                cur.execute(
                    "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                    (username, password_hash),
                )
                user_id = cur.lastrowid
                self._insert_account(cur, user_id, "default")
        except sqlite3.IntegrityError:
            raise BankError("username already exists") from None
        return user_id

    def login(self, username: str, password: str) -> dict:
        row = self.con.execute(
            "SELECT id, username, password_hash FROM users WHERE username = ?",
            ((username or "").strip(),),
        ).fetchone()
        if row is None:
            _verify_password(password or "", _dummy_hash())
            raise BankError("username or password incorrect")
        if not _verify_password(password or "", row["password_hash"]):
            raise BankError("username or password incorrect")
        return {"id": row["id"], "username": row["username"]}

    # ----- accounts -----
    def open_account(self, user_id: int, account_name: str) -> int:
        account_name = (account_name or "").strip()
        if not account_name or len(account_name) > MAX_ACCOUNT_NAME_LENGTH:
            raise BankError(
                f"account name must be 1-{MAX_ACCOUNT_NAME_LENGTH} characters"
            )
        try:
            with self._transaction() as cur:
                cur.execute("SELECT id FROM users WHERE id = ?", (user_id,))
                if cur.fetchone() is None:
                    raise BankError("user does not exist")
                return self._insert_account(cur, user_id, account_name)
        except sqlite3.IntegrityError:
            raise BankError("account with this name already exists") from None

    def get_accounts(self, user_id: int) -> list[sqlite3.Row]:
        return self.con.execute(
            "SELECT * FROM accounts WHERE user_id = ? ORDER BY id", (user_id,)
        ).fetchall()

    def get_account(self, account_id: int) -> sqlite3.Row | None:
        return self.con.execute(
            "SELECT * FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()

    def get_username(self, account_id: int) -> str:
        row = self.con.execute(
            """
            SELECT u.username FROM accounts a
            JOIN users u ON u.id = a.user_id
            WHERE a.id = ?
            """,
            (account_id,),
        ).fetchone()
        return row["username"] if row else "Unknown"

    # ----- transfers -----
    def transfer(
        self,
        user_id: int,
        src_account_id: int,
        dest_account_id: int,
        amount_cents: int,
        description: str = DEFAULT_DESCRIPTION,
    ) -> None:
        """Move money between accounts. Amounts are integer cents."""
        if (
            not isinstance(amount_cents, int)
            or isinstance(amount_cents, bool)
            or amount_cents <= 0
        ):
            raise BankError("amount must be a positive number of cents")
        if amount_cents > MAX_AMOUNT_CENTS:
            raise BankError("amount is too large")
        if src_account_id == dest_account_id:
            raise BankError("cannot transfer to the same account")
        description = (description or "").strip() or DEFAULT_DESCRIPTION
        if len(description) > MAX_DESCRIPTION_LENGTH:
            raise BankError(
                f"description is too long (max {MAX_DESCRIPTION_LENGTH} characters)"
            )

        with self._transaction() as cur:
            cur.execute("SELECT id FROM accounts WHERE id = ?", (dest_account_id,))
            if cur.fetchone() is None:
                raise BankError("destination account does not exist")

            cur.execute(
                "SELECT user_id FROM accounts WHERE id = ?", (src_account_id,)
            )
            src = cur.fetchone()
            if src is None:
                raise BankError("source account does not exist")
            if src["user_id"] != user_id:
                raise BankError("source account does not belong to user")

            # The WHERE clause makes the balance check and the debit one step.
            cur.execute(
                """
                UPDATE accounts SET balance_cents = balance_cents - ?
                WHERE id = ? AND balance_cents >= ?
                """,
                (amount_cents, src_account_id, amount_cents),
            )
            if cur.rowcount != 1:
                raise BankError("insufficient funds")
            cur.execute(
                "UPDATE accounts SET balance_cents = balance_cents + ? WHERE id = ?",
                (amount_cents, dest_account_id),
            )
            cur.execute(
                """
                INSERT INTO transactions
                    (src_account_id, dest_account_id, amount_cents, description)
                VALUES (?, ?, ?, ?)
                """,
                (src_account_id, dest_account_id, amount_cents, description),
            )

    def get_transactions(self, user_id: int) -> list[sqlite3.Row]:
        """All transfers into or out of the user's accounts, newest first."""
        return self.con.execute(
            """
            SELECT t.id, t.src_account_id, t.dest_account_id, t.amount_cents,
                   t.description, t.created_at,
                   sa.user_id  AS src_user_id,  su.username AS src_username,
                   da.user_id  AS dest_user_id, du.username AS dest_username
            FROM transactions t
            JOIN accounts sa ON sa.id = t.src_account_id
            JOIN users    su ON su.id = sa.user_id
            JOIN accounts da ON da.id = t.dest_account_id
            JOIN users    du ON du.id = da.user_id
            WHERE sa.user_id = ? OR da.user_id = ?
            ORDER BY t.created_at DESC, t.id DESC
            """,
            (user_id, user_id),
        ).fetchall()

    def close(self) -> None:
        self.con.close()
