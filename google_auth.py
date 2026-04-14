import os
import json
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

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
        return _creds

    token_json = os.environ.get('GOOGLE_TOKEN_JSON', '')
    if token_json:
        info = json.loads(token_json)
        _creds = Credentials.from_authorized_user_info(info, SCOPES)
        if _creds and _creds.expired and _creds.refresh_token:
            _creds.refresh(Request())
        return _creds

    token_path = os.environ.get('GOOGLE_TOKEN_PATH', 'token.json')
    if os.path.exists(token_path):
        _creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        if _creds and _creds.expired and _creds.refresh_token:
            _creds.refresh(Request())
        return _creds

    raise RuntimeError('No Google credentials found. Set GOOGLE_TOKEN_JSON env var.')
