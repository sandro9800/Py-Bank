from bank import Bank 
from menus import auth_menu ,bank_menu 


def main ():
    bank =Bank ()
    try :
        while True :
            user =auth_menu (bank )
            if user =='quit':
                break 
            if user is None :
                continue 
            op =bank_menu (bank ,user )
            if op =='quit':
                break 
    finally :
        print ('bye :)')
        bank .close ()


if __name__ =='__main__':
    main ()
