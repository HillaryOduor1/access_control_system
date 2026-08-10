# 🏫 School Management System - Desktop Application
## to run the app
frontend; first start the virtual env by running .\venv\scripts\activate
Then to run the backend run .\venv_backend\scripts\activate then start backend server uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

A modern, feature-rich desktop application for managing school operations built with Python and PySide6.

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![PySide6](https://img.shields.io/badge/PySide6-6.5+-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)

## 📋 Features

### 🎨 Modern User Interface

- **Dark/Light Theme Toggle** - Switch between themes with one click
- **Responsive Design** - Adapts to different window sizes
- **Clean Dashboard** - Modern card-based statistics display
- **Intuitive Navigation** - Easy-to-use sidebar menu

### 📊 Dashboard

- Real-time statistics overview
- Four key metrics cards:
  - Total Students
  - Active Classes
  - Total Teachers
  - Pending Fees
- Recent activity tracking table
- Percentage change indicators (positive/negative/neutral)

### 🔧 Technical Features

- Modular architecture with separate components
- Theme manager with CSS-based styling
- Object-oriented design patterns
- Custom widget system
- Data persistence ready

## 🚀 Getting Started

### Prerequisites

- Python 3.8 or higher
- pip (Python package manager)

### Installation

1. **Clone the repository**

```bash
git clone https://github.com/yourusername/school-management-system.git
cd school-management-system
2. ** Create a virtual environment (recommended)**
# On Windows
python -m venv venv
venv\Scripts\activate

# On macOS/Linux
python3 -m venv venv
source venv/bin/activate

3. install dependencies
pip install PySide6

4.Run the application
python main.py

📁 Project Structure
school-management-system/
├── main.py                    # Application entry point
├── config.py                  # Configuration settings
├── data/
│   └── app_data.json         # Application data storage
├── core/
│   ├── __init__.py
│   ├── app.py                # Main application window
│   └── theme_manager.py      # Theme management system
├── pages/
│   ├── __init__.py
│   ├── base_page.py          # Base page class
│   ├── dashboard_page.py     # Dashboard page implementation
│   └── students_page.py      # Students management page
├── widgets/
│   ├── __init__.py
│   ├── sidebar.py            # Sidebar navigation
│   └── header.py             # Application header
├── themes/
│   ├── dark.qss              # Dark theme styles
│   └── light.qss             # Light theme styles
└── utils/
    ├── __init__.py
    └── data_loader.py        # Data loading utilities

Key Components
1. Main Application (core/app.py)

    Creates the main window

    Manages navigation between pages

    Handles window geometry and positioning

    Integrates theme system

2. Theme Manager (core/theme_manager.py)

    Handles dark/light theme switching

    CSS-based styling system

    Dynamic style application

    Fallback styling support

3. Dashboard Page (pages/dashboard_page.py)

    Displays key statistics in card format

    Shows recent activity in a table

    Responsive grid layout

    Custom card widgets with icons

4. Sidebar Navigation

    Collapsible menu

    Active state highlighting

    Icon support

    Smooth navigation

🎨 UI Features
Themes

    Light Theme: Clean, professional look for daytime use

    Dark Theme: Eye-friendly dark mode for extended use

    Customizable: Easy to add new themes via CSS

Dashboard Cards

    Colored icons for quick recognition

    Large, readable values

    Trend indicators with color coding

    Hover effects for interactivity

Table Features

    Alternating row colors for readability

    Clean, modern borders

    Responsive column sizing

    Selection highlighting

🛠️ Development
Adding New Pages

    Create a new file in pages/ directory

    Extend the QWidget class

    Implement your UI in the init_ui() method

    Add navigation entry in core/app.py

Customizing Themes

    Edit CSS files in themes/ directory

    Add new color variables

    Apply styles to widget classes

    Test theme switching

Extending Functionality

    Add new data models in models/ directory

    Create custom widgets in widgets/ directory

    Implement utilities in utils/ directory

    Add data persistence in data/ directory

📝 Usage Guide
Navigation

    Use the sidebar to switch between different sections

    The active page is highlighted in the sidebar

    Page title updates automatically in the header

Theme Switching

    Click the theme toggle button in the sidebar

    Button shows current theme (🌙 for dark, ☀️ for light)

    Styles apply immediately without restart

Dashboard

    View key metrics at a glance

    Check percentage changes for trends

    Review recent activities in the table

    Click "View All" for detailed activity logs

Code Examples
Creating a Card Widget
def create_card(self, title, value, change, change_type, icon):
    card = QFrame()
    card.setObjectName("card")

    # Add icon, title, value, and change label
    # Apply styling via QSS classes

    return card

Theme Switching
def toggle_theme(self):
    self.theme_manager.toggle_theme()
    self.apply_theme()

Navigation
def navigate_to(self, page_name):
    self.page_title.setText(page_name.capitalize())
    self.content_stack.setCurrentIndex(page_index)

Troubleshooting
Common Issues

    "ModuleNotFoundError: No module named 'PySide6'"

        Run: pip install PySide6

    "Could not parse stylesheet" errors

        Check CSS syntax in theme files

        Ensure no missing semicolons or brackets

    Window not showing

        Check if window.show() is called

        Verify no exceptions in initialization

    Theme toggle not working

        Ensure theme files exist in themes/ directory

        Check button connection in app.py

Debug Mode

Run with verbose output:
bash

python main.py --debug

📈 Future Enhancements
Planned Features

    Student management system

    Teacher management system

    Class scheduling

    Fee payment tracking

    Report generation

    Data import/export

    User authentication

    Database integration

    Backup system

Technical Improvements

    Unit tests

    Documentation

    Performance optimization

    Multi-language support

    Plugin system

🤝 Contributing

    Fork the repository

    Create a feature branch (git checkout -b feature/AmazingFeature)

    Commit your changes (git commit -m 'Add some AmazingFeature')

    Push to the branch (git push origin feature/AmazingFeature)

    Open a Pull Request

Development Guidelines

    Follow PEP 8 style guide

    Write meaningful commit messages

    Add comments for complex logic

    Update documentation for new features

📄 License

This project is licensed under the MIT License - see the LICENSE file for details.
🙏 Acknowledgments

    PySide6 - Qt for Python bindings

    Qt Company - Qt framework

    Python Software Foundation - Python programming language

 Support

For support, email: support@example.com or open an issue on GitHub.

Note: This is a demo application. For production use, additional security measures and data validation should be implemented.


