# backend/app/services/email_service.py
import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from ..config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, APP_NAME

logger = logging.getLogger(__name__)

async def send_reset_email(email: str, full_name: str, otp: str):
    """
    Send password reset OTP via email.
    """
    try:
        if not SMTP_USER or not SMTP_PASSWORD:
            logger.warning("SMTP not configured. Printing OTP instead.")
            print(f"PASSWORD RESET OTP for {email}: {otp}")
            return
        
        subject = f"{APP_NAME} - Password Reset Code"
        
        html_content = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #0F172A; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
                .content {{ background: #F8FAFC; padding: 30px; border-radius: 0 0 8px 8px; border: 1px solid #E2E8F0; }}
                .otp-box {{ background: white; border: 2px dashed #0EA5E9; border-radius: 8px; padding: 20px; text-align: center; margin: 20px 0; }}
                .otp-code {{ font-size: 36px; font-weight: bold; letter-spacing: 8px; color: #0EA5E9; font-family: monospace; }}
                .footer {{ text-align: center; margin-top: 20px; font-size: 12px; color: #94A3B8; }}
                .warning {{ color: #EF4444; font-weight: bold; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>{APP_NAME}</h2>
                <p>Password Reset</p>
            </div>
            <div class="content">
                <p>Hello <strong>{full_name}</strong>,</p>
                <p>We received a request to reset your password for your {APP_NAME} account.</p>
                <p>Use the following One-Time Password (OTP) to reset your password:</p>
                <div class="otp-box">
                    <div class="otp-code">{otp}</div>
                    <p style="margin: 10px 0 0 0; font-size: 14px; color: #64748B;">
                        This code is valid for <strong>15 minutes</strong>
                    </p>
                </div>
                <p class="warning">If you did not request this, please ignore this email and ensure your account is secure.</p>
                <p>For security reasons, never share this OTP with anyone.</p>
                <hr style="border: none; border-top: 1px solid #E2E8F0; margin: 20px 0;">
                <p style="font-size: 14px; color: #64748B;">
                    Need help? Contact your system administrator.
                </p>
            </div>
            <div class="footer">
                <p>&copy; 2024 {APP_NAME}. All rights reserved.</p>
                <p>This is an automated message, please do not reply.</p>
            </div>
        </body>
        </html>
        """
        
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = SMTP_FROM
        msg['To'] = email
        
        # Attach HTML content
        msg.attach(MIMEText(html_content, 'html'))
        
        # Send email
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        
        logger.info(f"Password reset email sent to {email}")
        
    except Exception as e:
        logger.error(f"Failed to send reset email: {str(e)}")
        # Fallback: print OTP for development
        print(f"PASSWORD RESET OTP for {email}: {otp}")

async def send_reset_confirmation(email: str):
    """Send confirmation email after password reset."""
    try:
        if not SMTP_USER or not SMTP_PASSWORD:
            return
        
        subject = f"{APP_NAME} - Password Reset Confirmation"
        
        html_content = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #0F172A; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
                .content {{ background: #F8FAFC; padding: 30px; border-radius: 0 0 8px 8px; border: 1px solid #E2E8F0; }}
                .success {{ color: #10B981; font-weight: bold; }}
                .footer {{ text-align: center; margin-top: 20px; font-size: 12px; color: #94A3B8; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>{APP_NAME}</h2>
                <p>Password Reset Successful</p>
            </div>
            <div class="content">
                <p class="success">Your password has been successfully reset.</p>
                <p>You can now log in to your account with your new password.</p>
                <p>If you did not perform this action, please contact your system administrator immediately.</p>
                <hr style="border: none; border-top: 1px solid #E2E8F0; margin: 20px 0;">
                <p style="font-size: 14px; color: #64748B;">
                    Need help? Contact your system administrator.
                </p>
            </div>
            <div class="footer">
                <p>&copy; 2024 {APP_NAME}. All rights reserved.</p>
            </div>
        </body>
        </html>
        """
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = SMTP_FROM
        msg['To'] = email
        msg.attach(MIMEText(html_content, 'html'))
        
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
            
        logger.info(f"Password reset confirmation sent to {email}")
        
    except Exception as e:
        logger.error(f"Failed to send confirmation email: {str(e)}")