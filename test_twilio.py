import os
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()

account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
auth_token  = os.environ.get("TWILIO_AUTH_TOKEN")
from_number = os.environ.get("TWILIO_PHONE_NUMBER")
to_number   = "+917758970929" # Replace with your test phone number

print(f"Twilio SID: {account_sid}")
print(f"From Number: {from_number}")
print(f"To Number: {to_number}")
print("-" * 50)

if not account_sid or not auth_token:
    print("ERROR: Twilio credentials missing in .env")
    exit(1)

try:
    client = Client(account_sid, auth_token)
    
    # Test SMS
    print("Sending test SMS...")
    message = client.messages.create(
        body="WSAS: Twilio setup successful! This is a test alert.",
        from_=from_number,
        to=to_number
    )
    print(f"SMS SUCCESS! Message SID: {message.sid}")
    
    # Test Call
    print("\nInitiating test call...")
    call = client.calls.create(
        twiml="<Response><Say>SOS! Emergency alert test. Twilio is working correctly.</Say></Response>",
        to=to_number,
        from_=from_number
    )
    print(f"CALL SUCCESS! Call SID: {call.sid}")

except Exception as e:
    print(f"FAILED! Error: {str(e)}")
