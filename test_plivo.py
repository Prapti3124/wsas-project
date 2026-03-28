import os
import plivo
from dotenv import load_dotenv

load_dotenv()

auth_id    = os.environ.get("PLIVO_AUTH_ID")
auth_token = os.environ.get("PLIVO_AUTH_TOKEN")
from_num  = os.environ.get("PLIVO_PHONE_NUMBER")
to_num    = "+917758970929" # Replace with your test phone number

print(f"Plivo ID: {auth_id}")
print(f"From Number: {from_num}")
print(f"To Number: {to_num}")
print("-" * 50)

if not auth_id or not auth_token:
    print("ERROR: Plivo credentials missing in .env")
    exit(1)

try:
    client = plivo.RestClient(auth_id, auth_token)
    
    # Test SMS
    print("Sending test SMS...")
    response = client.messages.create(
        src=from_num,
        dst=to_num,
        text="WSAS: Plivo setup successful!"
    )
    print(f"SMS SUCCESS! Request UUID: {response.message_uuid}")
    
    # Test Call
    print("\nInitiating test call...")
    call = client.calls.create(
        from_=from_num,
        to_=to_num,
        answer_url="https://s3.amazonaws.com/static.plivo.com/answer.xml",
        answer_method='GET'
    )
    print(f"CALL SUCCESS! Request UUID: {call.request_uuid}")

except Exception as e:
    print(f"FAILED! Error: {str(e)}")
