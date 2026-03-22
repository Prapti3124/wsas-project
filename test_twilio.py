import os
from dotenv import load_dotenv
from twilio.rest import Client

load_dotenv()

account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
from_number = os.environ.get("TWILIO_PHONE_NUMBER")
to_phone = "+917758970929"

print(f"SID: {account_sid}")
print(f"From Number: {from_number}")
print(f"To Number: {to_phone}")
print("-" * 50)

try:
    client = Client(account_sid, auth_token)
    msg = client.messages.create(
        body="TEST: WSAS Emergency Alert working correctly!",
        from_=from_number,
        to=to_phone
    )
    print(f"SUCCESS! SMS SID: {msg.sid}")
    print(f"Status: {msg.status}")
except Exception as e:
    print(f"FAILED! Full error:")
    print(str(e))
