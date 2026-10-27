"""Console menus for PyBank."""

from getpass import getpass

from bank import BankError, format_cents, parse_amount

BACK_WORDS = ("back", "exit")


def _is_back(text: str) -> bool:
    return text.strip().lower() in BACK_WORDS


# --------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------
def reg_menu(bank):
    print("--- REGISTRATION MENU ---")
    print("(leave the username empty to go back)")
    while True:
        username = input("enter username: ").strip()
        if not username:
            return None
        password = getpass("enter password (min 8 characters): ")
        try:
            bank.register(username, password)
            return bank.login(username, password)
        except BankError as e:
            print(f"\nerror: {e}\n")


def login_menu(bank):
    print("--- LOGIN MENU ---")
    print("(leave the username empty to go back)")
    while True:
        username = input("enter username: ").strip()
        if not username:
            return None
        password = getpass("enter password: ")
        try:
            return bank.login(username, password)
        except BankError:
            print("\nerror: incorrect username or password !!!\n")


# --------------------------------------------------------------------------
# Read-only views
# --------------------------------------------------------------------------
def show_accounts(bank, user):
    accounts = bank.get_accounts(user["id"])
    if not accounts:
        print("\nNo accounts found")
        return
    print("\n--- YOUR ACCOUNTS ---")
    for account in accounts:
        print(
            f"ID {account['id']}: {account['name']} - "
            f"${format_cents(account['balance_cents'])}"
        )


def show_balance(bank, user):
    accounts = bank.get_accounts(user["id"])
    total = sum(account["balance_cents"] for account in accounts)
    print(f"Balance: {format_cents(total)}")


def show_transactions(bank, user):
    transactions = bank.get_transactions(user["id"])
    if not transactions:
        print("\nNo transactions found")
        return
    print("\n--- YOUR TRANSACTIONS ---")
    for txn in transactions:
        amount = format_cents(txn["amount_cents"])
        if txn["src_user_id"] == user["id"]:
            print(
                f"- ${amount} | to {txn['dest_username']} | "
                f"{txn['description']} | {txn['created_at']}"
            )
        else:
            print(
                f"+ ${amount} | from {txn['src_username']} | "
                f"{txn['description']} | {txn['created_at']}"
            )


# --------------------------------------------------------------------------
# Transfer flow
# --------------------------------------------------------------------------
def _ask_source(bank, user):
    """Ask for one of the user's own accounts. Returns its id, or None for 'back'."""
    while True:
        text = input("\nFrom account ID: ")
        if _is_back(text):
            return None
        try:
            account_id = int(text)
        except ValueError:
            print("Invalid account ID.")
            continue
        account = bank.get_account(account_id)
        if account is None:
            print("Account not found.")
        elif account["user_id"] != user["id"]:
            print("This is not your account. You can't transfer money from it.")
        else:
            return account_id


def _ask_destination(bank, src_id):
    """Ask for the destination account. Returns its id, or None for 'back'."""
    while True:
        text = input("To account ID: ")
        if _is_back(text):
            return None
        try:
            dest_id = int(text)
        except ValueError:
            print("Invalid account ID.")
            continue
        if dest_id == src_id:
            print("Cannot transfer to the same account")
        elif bank.get_account(dest_id) is None:
            print("Recipient account not found.")
        else:
            return dest_id


def _ask_amount(bank, src_id):
    """Ask for an amount (in cents). Returns None for 'back'."""
    while True:
        text = input("Amount: ")
        if _is_back(text):
            return None
        try:
            amount = parse_amount(text)
        except BankError as e:
            print(f"{str(e).capitalize()}.")
            continue
        account = bank.get_account(src_id)
        if account is None or amount > account["balance_cents"]:
            print("You don't have enough money in this account.")
            continue
        return amount


def _confirm():
    while True:
        answer = input("Confirm transfer? (yes/no): ").strip().lower()
        if answer in ("yes", "y"):
            return True
        if answer in ("no", "n", "back", "exit"):
            return False
        print("Please enter yes or no.")


def transaction_menu(bank, user):
    accounts = bank.get_accounts(user["id"])
    if not accounts:
        print("\nYou have no accounts")
        return
    print("\n--- TRANSFER MENU ---")
    print("Your accounts:")
    for acc in accounts:
        print(f"ID {acc['id']} - ${format_cents(acc['balance_cents'])}")
    print("\nType 'back' to return to the main menu at any prompt.")

    src_id = _ask_source(bank, user)
    if src_id is None:
        return
    dest_id = _ask_destination(bank, src_id)
    if dest_id is None:
        return
    print(f"\nYou are transferring money to: {bank.get_username(dest_id)}")

    while True:
        amount = _ask_amount(bank, src_id)
        if amount is None:
            print("Transaction cancelled.")
            return

        description = input("Description (optional, press enter to skip): ").strip()
        if _is_back(description):
            print("Transaction cancelled.")
            return

        if not _confirm():
            print("Transfer cancelled.")
            return

        try:
            bank.transfer(user["id"], src_id, dest_id, amount, description)
        except BankError as e:
            print(f"Transfer failed: {e}")
            print("Please try a different amount or type back to cancel.")
            continue

        print(
            f"\nTransfer successful! ${format_cents(amount)} sent "
            f"from account {src_id} to account {dest_id}."
        )
        return


# --------------------------------------------------------------------------
# Top-level menus
# --------------------------------------------------------------------------
def bank_menu(bank, user):
    while True:
        print("\n--- BANK MENU ---")
        print(f"Welcome to pybank {user['username']} ^_^")
        show_balance(bank, user)
        print("CHOOSE OPERATION YOU WISH TO PERFORM")
        print("1. SHOW MY ACCOUNTS")
        print("2. SHOW MY TRANSACTIONS")
        print("3. MAKE TRANSACTION")
        print("4. LOG OUT")
        print("5. QUIT")

        op = input("> ").strip()
        if op == "1":
            show_accounts(bank, user)
        elif op == "2":
            show_transactions(bank, user)
        elif op == "3":
            transaction_menu(bank, user)
        elif op == "4":
            return None
        elif op == "5":
            return "quit"
        else:
            print("please enter 1, 2, 3, 4 or 5")


def auth_menu(bank):
    while True:
        print("\n--- AUTH MENU ---")
        print("1. REGISTER")
        print("2. LOGIN")
        print("3. QUIT")
        op = input("> ").strip()
        if op == "1":
            return reg_menu(bank)
        elif op == "2":
            return login_menu(bank)
        elif op == "3":
            return "quit"
        else:
            print("please enter 1, 2 or 3")
