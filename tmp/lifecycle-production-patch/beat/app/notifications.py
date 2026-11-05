"""Pluggable alert delivery. Database alert events remain authoritative."""
import os
import smtplib
from email.message import EmailMessage


def send_email(subject: str, body: str, recipients: list[str]) -> None:
    host=os.environ["SMTP_HOST"];port=int(os.getenv("SMTP_PORT","587"));sender=os.environ["SMTP_FROM"]
    message=EmailMessage();message["Subject"]=subject;message["From"]=sender;message["To"] = ", ".join(recipients);message.set_content(body)
    with smtplib.SMTP(host,port,timeout=20) as client:
        if os.getenv("SMTP_TLS","true").lower()=="true":client.starttls()
        username=os.getenv("SMTP_USERNAME");password=os.getenv("SMTP_PASSWORD")
        if username:client.login(username,password or "")
        client.send_message(message)
