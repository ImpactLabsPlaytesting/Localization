import secrets
from datetime import datetime, timedelta
from db import get_db
import email_service
import config

TOKEN_EXPIRY_MINUTES = 15


def generate_magic_link(email):
    email = email.strip().lower()
    db = get_db()
    translator = db.execute('SELECT * FROM translators WHERE LOWER(email) = ?', (email,)).fetchone()
    if not translator:
        db.close()
        return None

    token = secrets.token_urlsafe(48)
    expires_at = (datetime.utcnow() + timedelta(minutes=TOKEN_EXPIRY_MINUTES)).isoformat()
    db.execute('INSERT INTO magic_links (token, translator_id, expires_at) VALUES (?, ?, ?)',
               (token, translator['id'], expires_at))
    db.commit()
    db.close()

    login_url = f"{config.BASE_URL}/login/verify?token={token}"
    email_service.send_magic_link(translator['name'], email, login_url)
    return True


def verify_token(token):
    db = get_db()
    row = db.execute('SELECT * FROM magic_links WHERE token = ? AND used = 0', (token,)).fetchone()
    if not row:
        db.close()
        return None

    expires_at = datetime.fromisoformat(row['expires_at'])
    if datetime.utcnow() > expires_at:
        db.close()
        return None

    db.execute('UPDATE magic_links SET used = 1 WHERE id = ?', (row['id'],))
    db.commit()

    translator = db.execute('SELECT * FROM translators WHERE id = ?', (row['translator_id'],)).fetchone()
    db.close()
    return translator


def cleanup_expired():
    db = get_db()
    db.execute('DELETE FROM magic_links WHERE expires_at < ? OR used = 1',
               (datetime.utcnow().isoformat(),))
    db.commit()
    db.close()
