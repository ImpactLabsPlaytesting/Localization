import os
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv('SECRET_KEY', 'change-me-in-production')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', '')
TOTP_SECRET = os.getenv('TOTP_SECRET', '')
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', '')
BASE_URL = os.getenv('BASE_URL', 'http://localhost:6767')
