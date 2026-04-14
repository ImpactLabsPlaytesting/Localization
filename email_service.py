import smtplib
import os
from email.mime.text import MIMEText

SMTP_USER = os.environ.get('SMTP_USER', '')
SMTP_PASS = os.environ.get('SMTP_PASS', '')
SMTP_HOST = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', '465'))
FROM_NAME = 'Todd Jackson (Impact Labs)'

BITLY_LOGIN = 'https://bit.ly/LabsLocalization'


def send_email(to_email, subject, body_html):
    message = MIMEText(body_html, 'html')
    message['to'] = to_email
    message['from'] = f'{FROM_NAME} <{SMTP_USER}>'
    message['subject'] = subject
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(message)


def send_invitation(translator_name, translator_email, project_name, language, dashboard_url):
    subject = f"You've been invited to review {language} translations - {project_name}"
    body = f"""<p>Hi {translator_name},</p>
<p>You've been invited to review <strong>{language}</strong> translations for <strong>{project_name}</strong>.</p>
<p>Log in to get started: <a href="{BITLY_LOGIN}">{BITLY_LOGIN}</a></p>
<p>- Impact Labs</p>"""
    send_email(translator_email, subject, body)


def send_new_rows_notification(translator_name, translator_email, project_name, language, count, dashboard_url):
    subject = f"Translations pending - {project_name} ({language})"
    body = f"""<p>Hi {translator_name},</p>
<p>You have <strong>{count}</strong> rows pending review for <strong>{language}</strong> on <strong>{project_name}</strong>.</p>
<p>Log in to review: <a href="{BITLY_LOGIN}">{BITLY_LOGIN}</a></p>
<p>- Impact Labs</p>"""
    send_email(translator_email, subject, body)


def send_magic_link(translator_name, translator_email, login_url):
    subject = "Your Impact Labs Login Link"
    body = f"""<p>Hi {translator_name},</p>
<p>Click the link below to log in to the Localization Dashboard:</p>
<p><a href="{login_url}">{login_url}</a></p>
<p>This link expires in 15 minutes.</p>
<p>- Impact Labs</p>"""
    send_email(translator_email, subject, body)


def send_done_notification(translator_name, project_name, language, reviewed, total, correct, corrected):
    admin_email = os.environ.get('ADMIN_EMAIL', '')
    if not admin_email:
        return
    subject = f"{translator_name} completed {language} review - {project_name}"
    body = f"""<p>{translator_name} has marked their <strong>{language}</strong> review as complete for <strong>{project_name}</strong>.</p>
<p>{reviewed}/{total} rows reviewed ({correct} correct, {corrected} corrected).</p>"""
    send_email(admin_email, subject, body)
