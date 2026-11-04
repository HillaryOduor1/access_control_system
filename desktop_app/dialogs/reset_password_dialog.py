# dialogs/reset_password_dialog.py
"""
Backward-compatibility shim.

The desktop app now uses the OTP-based flow implemented in
`dialogs.forgot_password_dialog.ForgotPasswordDialog`. Any older code
that still imports ResetPasswordDialog will get the new dialog,
configured with the correct endpoints.
"""
from dialogs.forgot_password_dialog import ForgotPasswordDialog


class ResetPasswordDialog(ForgotPasswordDialog):
    """Alias for the new OTP-based reset dialog."""

    def __init__(self, api_client, parent=None):
        super().__init__(api_client=api_client, parent=parent)
        self.setWindowTitle("Reset Password")



