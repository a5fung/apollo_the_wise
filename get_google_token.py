from google_auth_oauthlib.flow import InstalledAppFlow
import json

flow = InstalledAppFlow.from_client_secrets_file(
    'credentials.json',
    ['https://www.googleapis.com/auth/calendar']
)
creds = flow.run_local_server(port=0)
print(json.dumps(json.loads(creds.to_json())))
