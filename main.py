"""PyBank entry point: python main.py"""

from bank import Bank
from menus import auth_menu, bank_menu


def main():
    with Bank() as bank:
        try:
            while True:
                user = auth_menu(bank)
                if user == "quit":
                    break
                if user is None:
                    continue
                if bank_menu(bank, user) == "quit":
                    break
        except (KeyboardInterrupt, EOFError):
            print()
        finally:
            print("bye :)")


if __name__ == "__main__":
    main()
