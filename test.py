a=int(input("Enter Your marks:"))
if(a>=80):
    print("You Scored an A")
elif(a>=70 and a<80):
    print("You Scored an B")
    
elif(a>=60 and a<70):
    print("You Scored an C")
elif(a>=50 and a<60):  
    print("You Scored an D")
elif(a<=50):
    print("You Scored an F")
else:
    print("Invalid Input")