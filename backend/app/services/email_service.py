# app/services/email_service.py
"""
Email service for sending OTPs, notifications, and verification emails.

Changes in this revision
------------------------
- Added `send_password_reset_otp` — the desktop client now uses a
  6-digit code, not a clickable link, for password reset. Users type
  the code straight into the app.
- Added `send_password_changed_confirmation` — a plain confirmation
  with no buttons or links, matching the new flow.
- Kept `send_reset_email` / `send_reset_confirmation` for backward
  compatibility, but they are no longer used by the current UI.
"""
import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the correct path
env_path = Path(__file__).parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)
load_dotenv()

# Configure logger
logger = logging.getLogger(__name__)


def get_utc_now() -> datetime:
    """Get current UTC datetime with timezone awareness."""
    return datetime.now(timezone.utc)


class EmailService:
    """Enterprise email service with SMTP support."""

    def __init__(self):
        from app.config import settings

        env = os.getenv("ENV", "development")

        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.from_email = settings.SMTP_FROM
        self.app_name = settings.APP_NAME

        # Enable/disable email in development
        self.dev_mode = env == "development"

        # Check if email is configured
        self.is_configured = bool(self.smtp_user and self.smtp_password)

        if not self.is_configured:
            logger.warning(
                "Email service not configured. Emails will be logged to console."
            )

        logger.info(
            f"Email service initialized "
            f"(dev_mode={self.dev_mode}, configured={self.is_configured})"
        )

    # ------------------------------------------------------------------
    # Public async API
    # ------------------------------------------------------------------

    async def send_otp_email(
        self, to_email: str, otp_code: str, purpose: str = "verification"
    ) -> bool:
        """Send a generic OTP verification email."""
        purpose_display = purpose.replace('_', ' ').title()
        subject = f"{self.app_name} - {purpose_display} Code"

        logger.info(
            f"Sending OTP email to {to_email} for purpose: {purpose}"
        )
        logger.info(f"OTP Code: {otp_code}")

        html_content = self._get_otp_html_template(otp_code, purpose)
        text_content = self._get_otp_text_template(otp_code, purpose)

        if self.dev_mode:
            logger.info(f"[DEV MODE] OTP for {to_email}: {otp_code}")
            logger.info(
                f"[DEV MODE] Email would be sent with subject: {subject}"
            )
            return True

        return await self._send_email(
            to_email, subject, text_content, html_content
        )

    async def send_welcome_email(self, to_email: str, full_name: str) -> bool:
        """Send welcome email after successful signup."""
        subject = f"Welcome to {self.app_name}"

        logger.info(f"Sending welcome email to {to_email}")

        html_content = self._get_welcome_html_template(full_name)
        text_content = self._get_welcome_text_template(full_name)

        if self.dev_mode:
            logger.info(f"[DEV MODE] Welcome email sent to {to_email}")
            return True

        return await self._send_email(
            to_email, subject, text_content, html_content
        )

    async def send_password_reset_otp(
        self, to_email: str, otp_code: str
    ) -> bool:
        """
        Send the password-reset verification code.

        This is the desktop-appropriate replacement for the old
        link-based reset email. The user types this code into the
        running desktop app — no browser, no link, no context switch.
        """
        subject = f"{self.app_name} - Password Reset Code"

        logger.info(f"Sending password reset OTP to {to_email}")
        logger.info(f"Reset OTP: {otp_code}")

        html_content = self._get_reset_otp_html_template(otp_code)
        text_content = self._get_reset_otp_text_template(otp_code)

        if self.dev_mode:
            logger.info(
                f"[DEV MODE] Password reset OTP for {to_email}: {otp_code}"
            )
            return True

        return await self._send_email(
            to_email, subject, text_content, html_content
        )

    async def send_password_changed_confirmation(self, to_email: str) -> bool:
        """
        Send a confirmation that the password was changed. No buttons,
        no links — purely informational.
        """
        subject = f"{self.app_name} - Password Changed"

        logger.info(f"Sending password-changed confirmation to {to_email}")

        html_content = self._get_reset_confirmation_html_template()
        text_content = self._get_reset_confirmation_text_template()

        if self.dev_mode:
            logger.info(
                f"[DEV MODE] Password-changed confirmation sent to {to_email}"
            )
            return True

        return await self._send_email(
            to_email, subject, text_content, html_content
        )

    # ------------------------------------------------------------------
    # Legacy API (kept for backward compatibility — not used by the
    # current desktop UI)
    # ------------------------------------------------------------------

    async def send_reset_email(self, to_email: str, reset_token: str) -> bool:
        """Legacy: link/token-based reset email."""
        subject = f"{self.app_name} - Password Reset Request"
        logger.info(f"Sending legacy reset email to {to_email}")

        html_content = self._get_reset_html_template(reset_token)
        text_content = self._get_reset_text_template(reset_token)

        if self.dev_mode:
            logger.info(
                f"[DEV MODE] Password reset token for {to_email}: "
                f"{reset_token[:20]}..."
            )
            return True

        return await self._send_email(
            to_email, subject, text_content, html_content
        )

    async def send_reset_confirmation(self, to_email: str) -> bool:
        """Legacy alias for the new confirmation method."""
        return await self.send_password_changed_confirmation(to_email)

    # ------------------------------------------------------------------
    # Templates — generic OTP
    # ------------------------------------------------------------------

    def _get_otp_html_template(self, otp_code: str, purpose: str) -> str:
        purpose_display = purpose.replace('_', ' ').title()
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Verification Code</title>
            <style>
                body {{
                    font-family: 'Segoe UI', Arial, Helvetica, sans-serif;
                    background-color: #f5f7fa;
                    margin: 0;
                    padding: 0;
                    color: #1a202c;
                }}
                .container {{
                    max-width: 600px;
                    margin: 40px auto;
                    background-color: #ffffff;
                    border-radius: 8px;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                    overflow: hidden;
                }}
                .header {{
                    background-color: #1a2332;
                    padding: 32px 20px 28px;
                    text-align: center;
                }}
                .header h1 {{
                    color: #ffffff;
                    font-size: 22px;
                    margin: 0;
                    font-weight: 600;
                    letter-spacing: 0.5px;
                }}
                .header p {{
                    color: #9aa9c0;
                    margin: 6px 0 0;
                    font-size: 14px;
                }}
                .content {{
                    padding: 36px 32px 28px;
                }}
                .greeting {{
                    font-size: 16px;
                    color: #2d3748;
                    margin: 0 0 16px;
                    line-height: 1.5;
                }}
                .message {{
                    font-size: 15px;
                    color: #4a5568;
                    line-height: 1.6;
                    margin: 0 0 20px;
                }}
                .otp-code {{
                    font-size: 42px;
                    font-weight: 700;
                    color: #1a2332;
                    text-align: center;
                    padding: 18px 0;
                    background: #f0f4f8;
                    border-radius: 6px;
                    letter-spacing: 10px;
                    margin: 18px 0 22px;
                    font-family: 'Courier New', monospace;
                    border: 1px solid #e2e8f0;
                }}
                .info-text {{
                    color: #4a5568;
                    font-size: 14px;
                    line-height: 1.6;
                    margin: 0 0 16px;
                }}
                .warning-box {{
                    background: #fefcf0;
                    border-left: 4px solid #d69e2e;
                    padding: 14px 18px;
                    margin: 18px 0 10px;
                    font-size: 13px;
                    color: #744210;
                    border-radius: 0 4px 4px 0;
                }}
                .footer {{
                    padding: 20px 32px 24px;
                    text-align: center;
                    font-size: 12px;
                    color: #718096;
                    border-top: 1px solid #e2e8f0;
                    background-color: #f7fafc;
                }}
                .footer p {{ margin: 4px 0; }}
                .footer .company {{
                    font-weight: 600;
                    color: #2d3748;
                }}
                .footer .copyright {{
                    color: #a0aec0;
                    font-size: 11px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{self.app_name}</h1>
                    <p>Access Control System</p>
                </div>
                <div class="content">
                    <p class="greeting">Dear User,</p>
                    <p class="message">
                        Please use the verification code below to complete your {purpose_display.lower()}:
                    </p>
                    <div class="otp-code">{otp_code}</div>
                    <p class="info-text">
                        This code will expire in <strong>10 minutes</strong>.<br>
                        If you did not request this, please ignore this email.
                    </p>
                    <div class="warning-box">
                        <strong>Security Notice:</strong> Never share this code with anyone. {self.app_name} will never ask for this code.
                    </div>
                </div>
                <div class="footer">
                    <p class="company">{self.app_name}</p>
                    <p>Access Control System</p>
                    <p class="copyright">&copy; {get_utc_now().year} {self.app_name}. All rights reserved.</p>
                    <p style="color: #a0aec0; font-size: 11px; margin-top: 6px;">
                        This is an automated message, please do not reply.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

    def _get_otp_text_template(self, otp_code: str, purpose: str) -> str:
        purpose_display = purpose.replace('_', ' ').title()
        return f"""
{self.app_name} - Verification Code

Dear User,

Please use the verification code below to complete your {purpose_display.lower()}:

{otp_code}

This code will expire in 10 minutes.
If you did not request this, please ignore this email.

Security Notice: Never share this code with anyone. {self.app_name} will never ask for this code.

---
{self.app_name} - Access Control System
This is an automated message, please do not reply.
        """

    # ------------------------------------------------------------------
    # Templates — welcome
    # ------------------------------------------------------------------

    def _get_welcome_html_template(self, full_name: str) -> str:
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Welcome to {self.app_name}</title>
            <style>
                body {{
                    font-family: 'Segoe UI', Arial, Helvetica, sans-serif;
                    background-color: #f5f7fa;
                    margin: 0;
                    padding: 0;
                    color: #1a202c;
                }}
                .container {{
                    max-width: 600px;
                    margin: 40px auto;
                    background: #ffffff;
                    border-radius: 8px;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                    overflow: hidden;
                }}
                .header {{
                    background-color: #1a2332;
                    padding: 32px 20px 28px;
                    text-align: center;
                }}
                .header h1 {{
                    color: #ffffff;
                    font-size: 22px;
                    margin: 0;
                    font-weight: 600;
                    letter-spacing: 0.5px;
                }}
                .header p {{
                    color: #9aa9c0;
                    margin: 6px 0 0;
                    font-size: 14px;
                }}
                .content {{
                    padding: 36px 32px 28px;
                }}
                .greeting {{
                    font-size: 18px;
                    color: #2d3748;
                    margin: 0 0 16px;
                    font-weight: 600;
                }}
                .message {{
                    font-size: 15px;
                    color: #4a5568;
                    line-height: 1.7;
                    margin: 0 0 18px;
                }}
                .features {{
                    background: #f7fafc;
                    border-radius: 6px;
                    padding: 16px 22px;
                    margin: 16px 0 22px;
                    border: 1px solid #e2e8f0;
                }}
                .features li {{
                    font-size: 14px;
                    color: #2d3748;
                    line-height: 1.8;
                }}
                .footer {{
                    padding: 20px 32px 24px;
                    text-align: center;
                    font-size: 12px;
                    color: #718096;
                    border-top: 1px solid #e2e8f0;
                    background-color: #f7fafc;
                }}
                .footer p {{ margin: 4px 0; }}
                .footer .company {{
                    font-weight: 600;
                    color: #2d3748;
                }}
                .footer .copyright {{
                    color: #a0aec0;
                    font-size: 11px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{self.app_name}</h1>
                    <p>Access Control System</p>
                </div>
                <div class="content">
                    <p class="greeting">Welcome, {full_name}!</p>
                    <p class="message">
                        Your account has been successfully created for the {self.app_name}. You now have secure access to the system.
                    </p>
                    <div class="features">
                        <p style="font-weight: 600; color: #2d3748; margin: 0 0 8px;">With your account, you can:</p>
                        <ul style="padding-left: 20px; margin: 4px 0;">
                            <li>Log in to the system securely</li>
                            <li>Manage your profile and preferences</li>
                            <li>Access authorized features and modules</li>
                        </ul>
                    </div>
                </div>
                <div class="footer">
                    <p class="company">{self.app_name}</p>
                    <p>Access Control System</p>
                    <p class="copyright">&copy; {get_utc_now().year} {self.app_name}. All rights reserved.</p>
                    <p style="color: #a0aec0; font-size: 11px; margin-top: 6px;">
                        This is an automated message, please do not reply.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

    def _get_welcome_text_template(self, full_name: str) -> str:
        return f"""
Welcome to {self.app_name}

Dear {full_name},

Your account has been successfully created for the {self.app_name}. You now have secure access to the system.

With your account, you can:
- Log in to the system securely
- Manage your profile and preferences
- Access authorized features and modules

---
{self.app_name} - Access Control System
This is an automated message, please do not reply.
        """

    # ------------------------------------------------------------------
    # Templates — password reset OTP (desktop flow)
    # ------------------------------------------------------------------

    def _get_reset_otp_html_template(self, otp_code: str) -> str:
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Password Reset Code</title>
            <style>
                body {{
                    font-family: 'Segoe UI', Arial, Helvetica, sans-serif;
                    background-color: #f5f7fa;
                    margin: 0;
                    padding: 0;
                    color: #1a202c;
                }}
                .container {{
                    max-width: 600px;
                    margin: 40px auto;
                    background: #ffffff;
                    border-radius: 8px;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                    overflow: hidden;
                }}
                .header {{
                    background-color: #1a2332;
                    padding: 32px 20px 28px;
                    text-align: center;
                }}
                .header h1 {{
                    color: #ffffff;
                    font-size: 22px;
                    margin: 0;
                    font-weight: 600;
                    letter-spacing: 0.5px;
                }}
                .header p {{
                    color: #9aa9c0;
                    margin: 6px 0 0;
                    font-size: 14px;
                }}
                .content {{
                    padding: 36px 32px 28px;
                }}
                .greeting {{
                    font-size: 16px;
                    color: #2d3748;
                    margin: 0 0 16px;
                    line-height: 1.5;
                }}
                .message {{
                    font-size: 15px;
                    color: #4a5568;
                    line-height: 1.7;
                    margin: 0 0 18px;
                }}
                .otp-code {{
                    font-size: 42px;
                    font-weight: 700;
                    color: #1a2332;
                    text-align: center;
                    padding: 18px 0;
                    background: #f0f4f8;
                    border-radius: 6px;
                    letter-spacing: 10px;
                    margin: 18px 0 22px;
                    font-family: 'Courier New', monospace;
                    border: 1px solid #e2e8f0;
                }}
                .info-text {{
                    color: #4a5568;
                    font-size: 14px;
                    line-height: 1.6;
                    margin: 0 0 16px;
                }}
                .warning-box {{
                    background: #fefcf0;
                    border-left: 4px solid #d69e2e;
                    padding: 14px 18px;
                    margin: 18px 0 10px;
                    font-size: 13px;
                    color: #744210;
                    border-radius: 0 4px 4px 0;
                }}
                .footer {{
                    padding: 20px 32px 24px;
                    text-align: center;
                    font-size: 12px;
                    color: #718096;
                    border-top: 1px solid #e2e8f0;
                    background-color: #f7fafc;
                }}
                .footer p {{ margin: 4px 0; }}
                .footer .company {{
                    font-weight: 600;
                    color: #2d3748;
                }}
                .footer .copyright {{
                    color: #a0aec0;
                    font-size: 11px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{self.app_name}</h1>
                    <p>Password Reset Request</p>
                </div>
                <div class="content">
                    <p class="greeting">Dear User,</p>
                    <p class="message">
                        We received a request to reset the password for your account.
                        Open the Access Control desktop app, click
                        <strong>Forgot password</strong>, and enter this code:
                    </p>
                    <div class="otp-code">{otp_code}</div>
                    <p class="info-text">
                        This code will expire in <strong>15 minutes</strong>.<br>
                        If you did not request a password reset, please ignore this email — your password has not been changed.
                    </p>
                    <div class="warning-box">
                        <strong>Security Notice:</strong> Never share this code with anyone. {self.app_name} will never ask for this code.
                    </div>
                </div>
                <div class="footer">
                    <p class="company">{self.app_name}</p>
                    <p>Access Control System</p>
                    <p class="copyright">&copy; {get_utc_now().year} {self.app_name}. All rights reserved.</p>
                    <p style="color: #a0aec0; font-size: 11px; margin-top: 6px;">
                        This is an automated message, please do not reply.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

    def _get_reset_otp_text_template(self, otp_code: str) -> str:
        return f"""
{self.app_name} - Password Reset Code

Dear User,

We received a request to reset the password for your account.
Open the Access Control desktop app, click "Forgot password", and enter this code:

{otp_code}

This code will expire in 15 minutes.
If you did not request a password reset, please ignore this email.

Security Notice: Never share this code with anyone. {self.app_name} will never ask for this code.

---
{self.app_name} - Access Control System
This is an automated message, please do not reply.
        """

    # ------------------------------------------------------------------
    # Templates — password changed confirmation
    # ------------------------------------------------------------------

    def _get_reset_confirmation_html_template(self) -> str:
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Password Changed</title>
            <style>
                body {{
                    font-family: 'Segoe UI', Arial, Helvetica, sans-serif;
                    background-color: #f5f7fa;
                    margin: 0;
                    padding: 0;
                    color: #1a202c;
                }}
                .container {{
                    max-width: 600px;
                    margin: 40px auto;
                    background: #ffffff;
                    border-radius: 8px;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                    overflow: hidden;
                }}
                .header {{
                    background-color: #1a2332;
                    padding: 32px 20px 28px;
                    text-align: center;
                }}
                .header h1 {{
                    color: #ffffff;
                    font-size: 22px;
                    margin: 0;
                    font-weight: 600;
                    letter-spacing: 0.5px;
                }}
                .header p {{
                    color: #9aa9c0;
                    margin: 6px 0 0;
                    font-size: 14px;
                }}
                .content {{
                    padding: 36px 32px 28px;
                    text-align: center;
                }}
                .icon {{
                    font-size: 48px;
                    margin: 0 0 12px;
                }}
                .title {{
                    font-size: 22px;
                    font-weight: 600;
                    color: #2d3748;
                    margin: 0 0 12px;
                }}
                .message {{
                    font-size: 15px;
                    color: #4a5568;
                    line-height: 1.7;
                    margin: 0 0 20px;
                }}
                .footer {{
                    padding: 20px 32px 24px;
                    text-align: center;
                    font-size: 12px;
                    color: #718096;
                    border-top: 1px solid #e2e8f0;
                    background-color: #f7fafc;
                }}
                .footer p {{ margin: 4px 0; }}
                .footer .company {{
                    font-weight: 600;
                    color: #2d3748;
                }}
                .footer .copyright {{
                    color: #a0aec0;
                    font-size: 11px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{self.app_name}</h1>
                    <p>Password Changed</p>
                </div>
                <div class="content">
                    <div class="icon">&#128274;</div>
                    <p class="title">Your password has been changed</p>
                    <p class="message">
                        Your password was successfully updated. You can now
                        sign in to the Access Control desktop app with your
                        new password.
                    </p>
                    <p class="message" style="font-size: 13px; color: #718096;">
                        If you did not make this change, contact your
                        administrator immediately.
                    </p>
                </div>
                <div class="footer">
                    <p class="company">{self.app_name}</p>
                    <p>Access Control System</p>
                    <p class="copyright">&copy; {get_utc_now().year} {self.app_name}. All rights reserved.</p>
                    <p style="color: #a0aec0; font-size: 11px; margin-top: 6px;">
                        This is an automated message, please do not reply.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

    def _get_reset_confirmation_text_template(self) -> str:
        return f"""
{self.app_name} - Password Changed

Your password was successfully updated.
You can now sign in to the Access Control desktop app with your new password.

If you did not make this change, contact your administrator immediately.

---
{self.app_name} - Access Control System
This is an automated message, please do not reply.
        """

    # ------------------------------------------------------------------
    # Legacy templates (link-based reset email)
    # Kept so any external caller still works.
    # ------------------------------------------------------------------

    def _get_reset_html_template(self, reset_token: str) -> str:
        return f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="UTF-8"><title>Password Reset</title></head>
        <body style="font-family: Arial, sans-serif;">
            <h2>{self.app_name} - Password Reset Request</h2>
            <p>Use the following token to reset your password:</p>
            <p style="font-family: 'Courier New', monospace;
                      font-size: 18px; background: #f0f4f8;
                      padding: 12px; border-radius: 6px;">
                {reset_token}
            </p>
            <p>This token expires in 1 hour.</p>
        </body>
        </html>
        """

    def _get_reset_text_template(self, reset_token: str) -> str:
        return f"""
{self.app_name} - Password Reset Request

Use the following token to reset your password:
{reset_token}

This token expires in 1 hour.
        """

    # ------------------------------------------------------------------
    # SMTP send
    # ------------------------------------------------------------------

    async def _send_email(
        self, to_email: str, subject: str,
        text_content: str, html_content: str,
    ) -> bool:
        if not self.is_configured:
            logger.warning(
                f"Email not sent to {to_email} - SMTP not configured"
            )
            return False

        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = self.from_email
            msg['To'] = to_email
            msg['Subject'] = subject

            part1 = MIMEText(text_content, 'plain')
            part2 = MIMEText(html_content, 'html')
            msg.attach(part1)
            msg.attach(part2)

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, self._smtp_send, to_email, msg
            )

            logger.info(f"Email sent successfully to {to_email}")
            return True

        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"SMTP Authentication Error: {e}")
            return False
        except smtplib.SMTPException as e:
            logger.error(f"SMTP Error: {e}")
            return False
        except Exception as e:
            logger.error(f"Email error: {type(e).__name__}: {str(e)}")
            return False

    def _smtp_send(self, to_email: str, msg: MIMEMultipart):
        """Synchronous SMTP send (runs in a thread pool)."""
        try:
            with smtplib.SMTP(
                self.smtp_host, self.smtp_port, timeout=30
            ) as server:
                server.starttls()
                if self.smtp_user and self.smtp_password:
                    server.login(self.smtp_user, self.smtp_password)
                server.sendmail(
                    self.from_email, [to_email], msg.as_string()
                )
        except Exception as e:
            logger.error(f"SMTP send error: {e}")
            raise


# Global email service instance
email_service = EmailService()


# ============================================================================
# Backward Compatibility Functions
# ============================================================================

async def send_reset_email(email: str, token: str) -> bool:
    """Legacy: link/token-based reset email."""
    return await email_service.send_reset_email(email, token)


async def send_reset_confirmation(email: str) -> bool:
    """Legacy alias, now maps to the password-changed confirmation."""
    return await email_service.send_password_changed_confirmation(email)


