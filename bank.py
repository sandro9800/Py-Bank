import sqlite3 

class Bank :

    def __init__ (self ,db_path ='bank.db'):
        self .con =sqlite3 .connect (db_path )
        self .con .row_factory =sqlite3 .Row 
        self .setup ()

    def setup (self ):
        cur =self .con .cursor ()

        cur .execute ("""
            CREATE TABLE IF NOT EXISTS users (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT    UNIQUE NOT NULL,
                password TEXT    NOT NULL
            )
        """)

        cur .execute ("""
            CREATE TABLE IF NOT EXISTS accounts (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                name    TEXT    NOT NULL,
                user_id INTEGER NOT NULL REFERENCES users(id),
                balance REAL    NOT NULL DEFAULT 150,
                UNIQUE(name, user_id)
            )
        """)

        cur .execute ("""
            CREATE TABLE IF NOT EXISTS transactions (
                id              INTEGER  PRIMARY KEY AUTOINCREMENT,
                src_account_id  INTEGER  NOT NULL,
                dest_account_id INTEGER  NOT NULL,
                amount          REAL     NOT NULL,
                description     TEXT     NOT NULL DEFAULT 'personal transfer',
                created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self .con .commit ()

    def register (self ,username ,password ):
        cur =self .con .cursor ()

        cur .execute ("SELECT id FROM users WHERE username = ?",(username ,))
        if cur .fetchone ():
            raise ValueError ('username already exists')

        cur .execute (
        "INSERT INTO users (username, password) VALUES (?, ?)",
        (username ,password )
        )
        u_id =cur .lastrowid 

        self .open_account (u_id ,'default')

        self .con .commit ()
        return u_id 

    def login (self ,username ,password ):
        cur =self .con .cursor ()

        cur .execute (
        "SELECT * FROM users WHERE username = ? AND password = ?",
        (username ,password )
        )
        user =cur .fetchone ()

        if not user :
            raise ValueError ('username or password incorrect')

        return dict (user )

    def open_account (self ,user_id ,account_name ):
        cur =self .con .cursor ()

        cur .execute (
        "SELECT id FROM accounts WHERE name = ? AND user_id = ?",
        (account_name ,user_id )
        )
        if cur .fetchone ():
            raise ValueError ('account with this name already exists')

        cur .execute (
        "INSERT INTO accounts (name, user_id) VALUES (?, ?)",
        (account_name ,user_id )
        )
        account_id =cur .lastrowid 

        self .con .commit ()
        return account_id 

    def transfer (self ,user_id ,src_account_id ,dest_account_id ,amount ,description ='personal transfer'):
        cur =self .con .cursor ()

        cur .execute ("SELECT * FROM accounts WHERE id = ?",(dest_account_id ,))
        dest_row =cur .fetchone ()
        if not dest_row :
            raise ValueError ('destination account does not exist')
        dest =dict (dest_row )

        cur .execute ("SELECT * FROM accounts WHERE id = ?",(src_account_id ,))
        src_row =cur .fetchone ()
        if not src_row :
            raise ValueError ('source account does not exist')
        src =dict (src_row )

        if src ['user_id']!=user_id :
            raise ValueError ('source account does not belong to user')

        if src ['balance']<amount :
            raise ValueError ('insufficient funds')

        cur .execute (
        """INSERT INTO transactions (src_account_id, dest_account_id, amount, description)
               VALUES (?, ?, ?, ?)""",
        (src_account_id ,dest_account_id ,amount ,description )
        )

        cur .execute (
        "UPDATE accounts SET balance = balance + ? WHERE id = ?",
        (amount ,dest_account_id )
        )

        cur .execute (
        "UPDATE accounts SET balance = balance - ? WHERE id = ?",
        (amount ,src_account_id )
        )

        self .con .commit ()

    def get_accounts (self ,user_id ):
        cur =self .con .cursor ()
        cur .execute ("SELECT * FROM accounts WHERE user_id = ?",(user_id ,))
        return cur .fetchall ()

    def get_username (self ,account_id ):
        cur =self .con .cursor ()

        cur .execute ("SELECT user_id FROM accounts WHERE id = ?",(account_id ,))
        acc_row =cur .fetchone ()
        if not acc_row :
            return 'Unknown'

        user_id =acc_row ['user_id']

        cur .execute ("SELECT username FROM users WHERE id = ?",(user_id ,))
        user_row =cur .fetchone ()
        if not user_row :
            return 'Unknown'

        return user_row ['username']

    def get_transactions (self ,user_id ):
        cur =self .con .cursor ()

        cur .execute ("SELECT id FROM accounts WHERE user_id = ?",(user_id ,))
        account_ids =[row ['id']for row in cur .fetchall ()]

        raw_transactions =[]
        for account_id in account_ids :
            cur .execute (
            """SELECT * FROM transactions
                   WHERE src_account_id = ? OR dest_account_id = ?
                   ORDER BY created_at DESC""",
            (account_id ,account_id )
            )
            raw_transactions .extend (cur .fetchall ())

        seen =set ()
        unique_transactions =[]
        for txn in raw_transactions :
            if txn ['id']not in seen :
                seen .add (txn ['id'])
                unique_transactions .append (txn )

        return unique_transactions 

    def close (self ):
        self .con .close ()
