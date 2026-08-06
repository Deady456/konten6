from google_auth_oauthlib.flow import InstalledAppFlow
from src.upload import SCOPES, CLIENT_SECRET, _token_path

def run():
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
    creds = flow.run_local_server(port=0, open_browser=False)
    token_path = _token_path()
    token_path.write_text(creds.to_json(), encoding="utf-8")
    print("Done!")

if __name__ == "__main__":
    run()
