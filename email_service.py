import base64
import os
from email.mime.text import MIMEText
from googleapiclient.discovery import build
from google_auth import get_credentials

SMTP_USER = os.environ.get('SMTP_USER', '')
FROM_NAME = 'Todd Jackson (Impact Labs)'

LOGIN_URL = os.environ.get('BASE_URL', 'http://localhost:6767') + '/login'


def _get_gmail_service():
    creds = get_credentials()
    return build('gmail', 'v1', credentials=creds)


def send_email(to_email, subject, body_html):
    service = _get_gmail_service()
    message = MIMEText(body_html, 'html')
    message['to'] = to_email
    message['from'] = f'{FROM_NAME} <{SMTP_USER}>'
    message['subject'] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().messages().send(
        userId='me',
        body={'raw': raw}
    ).execute()


def _wrap_email(content, button_text=None, button_url=None):
    button_html = ''
    if button_text and button_url:
        button_html = f'''
            <tr><td style="padding: 24px 0 8px 0; text-align: center;">
                <a href="{button_url}" style="background-color: #00e68a; color: #0d0d0d; padding: 14px 32px; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 16px; display: inline-block;">
                    {button_text}
                </a>
            </td></tr>'''

    return f'''
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin: 0; padding: 0; background-color: #111111; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background-color: #111111; padding: 32px 0;">
<tr><td align="center">
<table width="560" cellpadding="0" cellspacing="0" style="background-color: #1a1a1a; border-radius: 12px; border: 1px solid #2a2a2a;">
    <tr><td style="padding: 32px 40px 0 40px; text-align: center;">
        <div style="font-size: 22px; font-weight: bold; color: #00e68a; letter-spacing: 1px;">IMPACT LABS</div>
        <div style="font-size: 13px; color: #666; margin-top: 4px; letter-spacing: 2px;">LOCALIZATION</div>
    </td></tr>
    <tr><td style="padding: 24px 40px 0 40px;">
        <hr style="border: none; border-top: 1px solid #2a2a2a; margin: 0;">
    </td></tr>
    <tr><td style="padding: 24px 40px; color: #e0e0e0; font-size: 15px; line-height: 1.7;">
        {content}
    </td></tr>
    {button_html}
    <tr><td style="padding: 24px 40px; text-align: center;">
        <hr style="border: none; border-top: 1px solid #2a2a2a; margin: 0 0 16px 0;">
        <div style="color: #555; font-size: 12px;">Impact Labs Playtesting Division</div>
    </td></tr>
</table>
</td></tr>
</table>
</body>
</html>'''


def send_invitation(translator_name, translator_email, project_name, language, dashboard_url):
    subject = f"You've been invited to review {language} translations - {project_name}"
    content = f'''
        <p style="margin: 0 0 16px 0;">Hi {translator_name},</p>
        <p style="margin: 0 0 16px 0;">You've been invited to review <strong style="color: #00e68a;">{language}</strong> translations for <strong style="color: #ffffff;">{project_name}</strong>.</p>
        <p style="margin: 0;">Log in with your email to get started. Your translation tasks will be waiting for you.</p>'''
    body = _wrap_email(content, 'Open Dashboard', LOGIN_URL)
    send_email(translator_email, subject, body)


def send_new_rows_notification(translator_name, translator_email, project_name, language, count, dashboard_url):
    subject = f"Translations pending - {project_name} ({language})"
    content = f'''
        <p style="margin: 0 0 16px 0;">Hi {translator_name},</p>
        <p style="margin: 0 0 16px 0;">You have <strong style="color: #00e68a;">{count}</strong> rows pending review for <strong style="color: #ffffff;">{language}</strong> on <strong style="color: #ffffff;">{project_name}</strong>.</p>
        <p style="margin: 0;">Log in to continue your review.</p>'''
    body = _wrap_email(content, 'Review Now', LOGIN_URL)
    send_email(translator_email, subject, body)


def send_magic_link(translator_name, translator_email, login_url):
    subject = "Your Impact Labs Login Link"
    content = f'''
        <p style="margin: 0 0 16px 0;">Hi {translator_name},</p>
        <p style="margin: 0 0 16px 0;">Click the button below to log in to the Localization Dashboard.</p>
        <p style="margin: 0; color: #888; font-size: 13px;">This link expires in 15 minutes and can only be used once.</p>'''
    body = _wrap_email(content, 'Log In', login_url)
    send_email(translator_email, subject, body)


def send_done_notification(translator_name, project_name, language, reviewed, total, correct, corrected):
    admin_email = os.environ.get('ADMIN_EMAIL', '')
    if not admin_email:
        return
    subject = f"{translator_name} completed {language} review - {project_name}"
    content = f'''
        <p style="margin: 0 0 16px 0;"><strong style="color: #ffffff;">{translator_name}</strong> has marked their <strong style="color: #00e68a;">{language}</strong> review as complete for <strong style="color: #ffffff;">{project_name}</strong>.</p>
        <table style="width: 100%; border-collapse: collapse; margin-top: 8px;">
            <tr>
                <td style="padding: 8px 12px; border: 1px solid #2a2a2a; color: #888;">Reviewed</td>
                <td style="padding: 8px 12px; border: 1px solid #2a2a2a; color: #e0e0e0; font-weight: bold;">{reviewed}/{total}</td>
            </tr>
            <tr>
                <td style="padding: 8px 12px; border: 1px solid #2a2a2a; color: #888;">Correct</td>
                <td style="padding: 8px 12px; border: 1px solid #2a2a2a; color: #00e68a; font-weight: bold;">{correct}</td>
            </tr>
            <tr>
                <td style="padding: 8px 12px; border: 1px solid #2a2a2a; color: #888;">Corrected</td>
                <td style="padding: 8px 12px; border: 1px solid #2a2a2a; color: #f0ad4e; font-weight: bold;">{corrected}</td>
            </tr>
        </table>'''
    body = _wrap_email(content)
    send_email(admin_email, subject, body)
