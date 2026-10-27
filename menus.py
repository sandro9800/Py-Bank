def reg_menu (bank ):
    while True :
        print ('--- REGISTRATION MENU ---')
        username =input ('enter username: ')
        password =input ('enter password: ')

        if not username and not password :
            raise ValueError ('username or password cant be empty')
        try :
            bank .register (username ,password )
            user =bank .login (username ,password )
            return user 
        except ValueError as e :
            print (f'\nerror: {e }')
            continue 


def login_menu (bank ):
    while True :
        print ('--- LOGIN MENU ---')
        username =input ('enter username: ')
        password =input ('enter password: ')

        if not username and not password :
            raise ValueError ('username or password cant be empty')
        try :
            user =bank .login (username ,password )
            return user 
        except ValueError :
            print ('\nerror: incorrect username or password !!!')
            continue 


def show_accounts (bank ,user ):
    accounts =bank .get_accounts (user ['id'])
    if not accounts :
        print ('\nNo accounts found')
        return 
    print ('\n--- YOUR ACCOUNTS ---')
    for account in accounts :
        print (f"ID {account ['id']}: {account ['name']} - ${account ['balance']:.2f}")


def show_balance (bank ,user ):
    accounts =bank .get_accounts (user ['id'])
    total_balance =sum (account ['balance']for account in accounts )
    print (f"Balance: {total_balance :.2f}")


def show_transactions (bank ,user ):
    transactions =bank .get_transactions (user ['id'])
    if not transactions :
        print ('\nNo transactions found')
        return 
    print ('\n--- YOUR TRANSACTIONS ---')
    user_account_ids =[acc ['id']for acc in bank .get_accounts (user ['id'])]
    for txn in transactions :
        src_user =bank .get_username (txn ['src_account_id'])
        dest_user =bank .get_username (txn ['dest_account_id'])
        is_outgoing =txn ['src_account_id']in user_account_ids 
        if is_outgoing :
            print (f"- ${txn ['amount']:.2f} | to {dest_user } | {txn ['description']} | {txn ['created_at']}")
        else :
            print (f"+ ${txn ['amount']:.2f} | from {src_user } | {txn ['description']} | {txn ['created_at']}")


def transaction_menu (bank ,user ):
    accounts =bank .get_accounts (user ['id'])
    if not accounts :
        print ('\nYou have no accounts')
        return 
    print ('\n--- TRANSFER MENU ---')
    print ('Your accounts:')
    for acc in accounts :
        print (f"ID {acc ['id']} - ${acc ['balance']:.2f}")

    cur =bank .con .cursor ()
    sender_account =None 
    recipient_account =None 
    src_id =None 
    dest_id =None 

    print ("\nType 'back' to return to the main menu at any prompt.")
    while True :
        src_id_input =input ('\nFrom account ID: ')
        if src_id_input .strip ().lower ()in ('back','exit'):
            return 
        try :
            src_id =int (src_id_input )
        except ValueError :
            print ('Invalid account ID.')
            continue 

        cur .execute ("SELECT * FROM accounts WHERE id = ?",(src_id ,))
        sender_row =cur .fetchone ()
        if not sender_row :
            print ('Account not found.')
            continue 

        sender_account =dict (sender_row )
        if sender_account ['user_id']!=user ['id']:
            print ("This is not your account. You can't transfer money from it.")
            sender_account =None 
            continue 

        break 

    while True :
        dest_id_input =input ('To account ID: ')
        if dest_id_input .strip ().lower ()in ('back','exit'):
            return 
        try :
            dest_id =int (dest_id_input )
        except ValueError :
            print ('Invalid account ID.')
            continue 

        if dest_id ==src_id :
            print ('Cannot transfer to the same account')
            continue 

        cur .execute ("SELECT * FROM accounts WHERE id = ?",(dest_id ,))
        recipient_row =cur .fetchone ()
        if not recipient_row :
            print ('Recipient account not found.')
            continue 

        recipient_account =dict (recipient_row )
        recipient_username =bank .get_username (dest_id )
        print (f'\nYou are transferring money to: {recipient_username }')
        break 

    while True :
        while True :
            amount_input =input ('Amount: ')
            if amount_input .strip ().lower ()in ('back','exit'):
                print ('Transaction cancelled.')
                return 
            try :
                amount =float (amount_input )
                if amount <=0 :
                    print ('Amount must be greater than zero.')
                    continue 
                if amount >sender_account ['balance']:
                    print ("You don't have enough money in this account.")
                    continue 
                break 
            except ValueError :
                print ('Invalid amount.')
                continue 

        description =input ('Description (optional, press enter to skip): ')
        if description .strip ().lower ()in ('back','exit'):
            print ('Transaction cancelled.')
            return 
        if not description :
            description ='personal transfer'

        while True :
            confirm =input ('Confirm transfer? (yes/no): ').strip ().lower ()
            if confirm in ('yes','y'):
                break 
            if confirm in ('no','n','back','exit'):
                print ('Transfer cancelled.')
                return 
            print ('Please enter yes or no.')

        try :
            bank .transfer (user ['id'],src_id ,dest_id ,amount ,description )
            print (f'\nTransfer successful! ${amount :.2f} sent from account {src_id } to account {dest_id }.')
            return 
        except ValueError as e :
            print (f'Transfer failed: {e }')
            print ('Please try a different amount or type back to cancel.')


def bank_menu (bank ,user ):
    while True :
        print ("\n--- BANK MENU ---")
        print (f"Welcome to pybank {user ['username']} ^_^")
        show_balance (bank ,user )
        print ("CHOOSE OPERATION YOU WISH TO PERFORM")
        print ("1. SHOW MY ACCOUNTS")
        print ("2. SHOW MY TRANSACTIONS")
        print ("3. MAKE TRANSACTION")
        print ("4. LOG OUT")
        print ("5. QUIT")

        op =input ('> ')
        if op =='1':
            show_accounts (bank ,user )
        elif op =='2':
            show_transactions (bank ,user )
        elif op =='3':
            transaction_menu (bank ,user )
        elif op =='4':
            return None 
        elif op =='5':
            return 'quit'
        else :
            print ('please enter 1, 2, 3, 4 or 5')


def auth_menu (bank ):
    while True :
        print ('\n--- AUTH MENU ---')
        print ('1. REGISTER')
        print ('2. LOGIN')
        print ('3. QUIT')
        op =input ('> ')
        if op =='1':
            return reg_menu (bank )
        elif op =='2':
            return login_menu (bank )
        elif op =='3':
            return 'quit'
        else :
            print ('please enter 1, 2 or 3')
