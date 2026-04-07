import pyotp
import qrcode
import io
import base64
from functools import wraps
from flask import session, redirect, url_for
import config


def verify_admin_password(password):
    return password == config.ADMIN_PASSWORD


def get_totp():
    if not config.TOTP_SECRET:
        return None
    return pyotp.TOTP(config.TOTP_SECRET)


def verify_totp(code):
    totp = get_totp()
    if not totp:
        return False
    return totp.verify(code)


def generate_totp_secret():
    return pyotp.random_base32()


def get_totp_qr_base64(secret, account_name='Impact Labs Localization'):
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=account_name, issuer_name='Impact Labs')
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode('utf-8')


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_authenticated'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated
