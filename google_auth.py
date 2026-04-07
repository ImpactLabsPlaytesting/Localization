import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
import config

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/gmail.send',
]

_creds = None


def get_credentials():
    global _creds
    if _creds and _creds.valid:
        return _creds
    if _creds and _creds.expired and _creds.refresh_token:
        _creds.refresh(Request())
        _save_token(_creds)
        return _creds

    token_path = config.GOOGLE_TOKEN_PATH
    creds_path = config.GOOGLE_CREDENTIALS_PATH

    if os.path.exists(token_path):
        _creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        if _creds and _creds.valid:
            return _creds
        if _creds and _creds.expired and _creds.refresh_token:
            _creds.refresh(Request())
            _save_token(_creds)
            return _creds

    flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
    _creds = flow.run_local_server(port=0)
    _save_token(_creds)
    return _creds


def _save_token(creds):
    with open(config.GOOGLE_TOKEN_PATH, 'w') as f:
        f.write(creds.to_json())
