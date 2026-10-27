# Py-Bank

A command-line banking app written in plain Python with SQLite. Users can register, log in, hold several accounts and transfer money to other users, with a full transaction history. Built as my main project while learning Python.

It uses only the standard library, so there is nothing to install.

> This is a learning/demo project, not real banking software. Every new account starts with 150.00 of demo money.

## Features

- Register and log in (passwords are hashed, input is hidden while typing)
- Multiple accounts per user, each with its own balance
- Transfers between any two accounts with an optional description and a confirmation step
- Transaction history (incoming and outgoing), newest first
- Type `back` at any transfer prompt to cancel

## Run it

Requires Python 3.9 or newer.

```bash
git clone https://github.com/sandro9800/Py-Bank.git
cd Py-Bank
python main.py
```

The database file `bank.db` is created next to the program on first run. If you have a `bank.db` from an older version of this project, move or delete it first: the format changed (see below) and the program will tell you so.

## Example session

```
--- AUTH MENU ---
1. REGISTER
2. LOGIN
3. QUIT
> 1

--- BANK MENU ---
Welcome to pybank alice ^_^
Balance: 150.00
1. SHOW MY ACCOUNTS
2. SHOW MY TRANSACTIONS
3. MAKE TRANSACTION
4. LOG OUT
5. QUIT
> 3

From account ID: 1
To account ID: 2
You are transferring money to: bobby
Amount: 25.50
Confirm transfer? (yes/no): yes

Transfer successful! $25.50 sent from account 1 to account 2.
```

## How it works

| File | Purpose |
| ---- | ------- |
| `bank.py` | All business rules and database access (`Bank` class) |
| `menus.py` | Console menus and input handling |
| `main.py` | Program entry point |
| `tests/` | Unit tests for the banking logic |

The UI never touches SQL: `menus.py` only calls methods on `Bank`, so the logic can be tested without a terminal.

### Design decisions

- **Passwords:** stored as salted PBKDF2-HMAC-SHA256 hashes (600,000 iterations), compared in constant time. Unknown users and wrong passwords produce the same error, and a failed login for an unknown user takes about as long as a real one.
- **Money as integers:** balances and amounts are stored as integer cents, never floats, so there are no rounding errors. User input like `12.50` is parsed with `Decimal`, and `nan`, `inf`, negative numbers and more than 2 decimal places are rejected.
- **Atomic transfers:** each transfer runs in a single `BEGIN IMMEDIATE` transaction. The balance check and the debit are one SQL statement (`UPDATE ... WHERE balance_cents >= ?`), so an account cannot be overdrawn, even by two programs using the same database file, and a failure rolls everything back.
- **Rules live in the `Bank` class, not only in the UI:** negative amounts, transferring to the same account, spending from someone else's account and so on are rejected by `Bank.transfer` itself.
- **Database constraints** as a second safety net: foreign keys, `CHECK (balance_cents >= 0)`, `CHECK (amount_cents > 0)`, unique usernames (case-insensitive).

## Tests

```bash
python -m unittest -v
```

The tests cover registration and login, password hashing, amount parsing, transfers (including insufficient funds, other users' accounts and rollback) and transaction ordering.

## Known limitations

- Single-machine console app; there is no network layer.
- No account lockout after repeated failed logins.
- No way to close accounts or change passwords yet.

## License

Released under the MIT License. See [LICENSE](LICENSE).
