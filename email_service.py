import base64
from email.mime.text import MIMEText
from googleapiclient.discovery import build
from google_auth import get_credentials
import config


def _get_gmail_service():
    creds = get_credentials()
    return build('gmail', 'v1', credentials=creds)


def send_email(to_email, subject, body_html):
    service = _get_gmail_service()
    message = MIMEText(body_html, 'html')
    message['to'] = to_email
    message['subject'] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().messages().send(
        userId='me',
        body={'raw': raw}
    ).execute()


def send_invitation(translator_name, translator_email, project_name, language, dashboard_url):
    subject = f"You've been invited to review {language} translations - {project_name}"
    body = f"""<p>Hi {translator_name},</p>
<p>You've been invited to review <strong>{language}</strong> translations for <strong>{project_name}</strong>.</p>
<p>Log in to get started: <a href="{dashboard_url}">{dashboard_url}</a></p>
<p>- Impact Labs</p>"""
    send_email(translator_email, subject, body)


def send_new_rows_notification(translator_name, translator_email, project_name, language, count, dashboard_url):
    subject = f"New rows to review - {project_name} ({language})"
    body = f"""<p>Hi {translator_name},</p>
<p><strong>{count}</strong> new rows have been added to <strong>{project_name}</strong> for <strong>{language}</strong> review.</p>
<p>Log in to review: <a href="{dashboard_url}">{dashboard_url}</a></p>
<p>- Impact Labs</p>"""
    send_email(translator_email, subject, body)


def send_done_notification(translator_name, project_name, language, reviewed, total, correct, corrected):
    if not config.ADMIN_EMAIL:
        return
    subject = f"{translator_name} completed {language} review - {project_name}"
    body = f"""<p>{translator_name} has marked their <strong>{language}</strong> review as complete for <strong>{project_name}</strong>.</p>
<p>{reviewed}/{total} rows reviewed ({correct} correct, {corrected} corrected).</p>"""
    send_email(config.ADMIN_EMAIL, subject, body)
