# widgets/__init__.py
"""
Widgets package for the ICT Authority Access Control System.
"""

from widgets.components import (
    ShadcnButton,
    ShadcnInput,
    ShadcnTextArea,
    ShadcnComboBox,
    ShadcnCheckBox,
    ShadcnRadioButton,
    ShadcnLabel,
    ShadcnCaption,
    ShadcnHeading,
    ShadcnSeparator,
    ShadcnCard,
    CardHeader,
    CardContent,
    CardFooter,
    ShadcnAvatar,
    ShadcnBadge,
    ShadcnAlert,
    ShadcnAlertDialog,
    ShadcnSkeleton,
    ShadcnToast,
    ShadcnSheet,
    ShadcnPagination,
    ShadcnField,
    ShadcnFieldGroup,
    ShadcnItem,
    ShadcnMenubar,
    ShadcnNavigationMenu,
)

# Import DataTable from the standalone module
from widgets.data_table import ShadcnDataTable as EnterpriseDataTable, SelectionMode, SortOrder

# Import widgets
from widgets.sidebar import Sidebar
from widgets.header import Header
from widgets.floating_label_input import FloatingLabelInput
from widgets.password_strength_meter import PasswordStrengthMeter
from widgets.splash_screen import SplashScreen

# ThemeToggle is part of Header - we export it for convenience
# If you have a separate theme_toggle.py, uncomment the line below
# from widgets.theme_toggle import ThemeToggle

__all__ = [
    # Components
    "ShadcnButton",
    "ShadcnInput",
    "ShadcnTextArea",
    "ShadcnComboBox",
    "ShadcnCheckBox",
    "ShadcnRadioButton",
    "ShadcnLabel",
    "ShadcnCaption",
    "ShadcnHeading",
    "ShadcnSeparator",
    "ShadcnCard",
    "CardHeader",
    "CardContent",
    "CardFooter",
    "ShadcnAvatar",
    "ShadcnBadge",
    "ShadcnAlert",
    "ShadcnAlertDialog",
    "ShadcnSkeleton",
    "ShadcnToast",
    "ShadcnSheet",
    "ShadcnPagination",
    "ShadcnField",
    "ShadcnFieldGroup",
    "ShadcnItem",
    "ShadcnMenubar",
    "ShadcnNavigationMenu",
    # Enterprise Data Table
    "EnterpriseDataTable",
    "SelectionMode",
    "SortOrder",
    # Widgets
    "Sidebar",
    "Header",
    "FloatingLabelInput",
    "PasswordStrengthMeter",
    "SplashScreen",
]