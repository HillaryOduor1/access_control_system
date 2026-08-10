# ICT Access Control System

A comprehensive access control and management system for the ICT Authority, featuring a modern desktop application with a FastAPI backend and MongoDB database.

## Table of Contents

* [Overview](#overview)
* [Features](#features)

  * [Authentication and Security](#authentication-and-security)
  * [User Management](#user-management)
  * [Access Control](#access-control)
  * [System Features](#system-features)
* [Tech Stack](#tech-stack)

  * [Frontend - Desktop Application](#frontend---desktop-application)
  * [Backend - API](#backend---api)
* [Project Structure](#project-structure)
* [Prerequisites](#prerequisites)
* [Installation](#installation)

  * [Backend Setup](#backend-setup)
  * [Desktop App Setup](#desktop-app-setup)
* [Configuration](#configuration)

  * [Environment Variables](#environment-variables)
  * [MongoDB Configuration](#mongodb-configuration)
  * [JWT Configuration](#jwt-configuration)
  * [Email Configuration](#email-configuration)
  * [Application Configuration](#application-configuration)
  * [Desktop App Configuration](#desktop-app-configuration)
* [Running the Application](#running-the-application)

  * [Quick Start](#quick-start)
  * [Default Credentials](#default-credentials)
* [Deployment](#deployment)

  * [Deploy Backend to Render](#deploy-backend-to-render)
  * [Build Desktop Application](#build-desktop-application)
* [API Documentation](#api-documentation)

  * [Swagger UI](#swagger-ui)
  * [ReDoc](#redoc)
  * [Main API Endpoints](#main-api-endpoints)
* [Contributing](#contributing)

  * [Development Workflow](#development-workflow)
  * [Coding Standards](#coding-standards)
* [License](#license)
* [Authors](#authors)
* [Acknowledgments](#acknowledgments)
* [Support](#support)

## Overview

The ICT Access Control System is a desktop-based application designed to manage and monitor access control for the ICT Authority. It provides a secure, user-friendly interface for managing employees, visitors, access logs, and system configurations.

### Key Capabilities

* Secure authentication with JWT tokens
* Real-time access monitoring
* Employee and visitor management
* Role-based access control (RBAC)
* Offline support with data synchronization
* Comprehensive audit logging
* Theme support for Light and Dark modes

## Features

### Authentication and Security

* **Secure Login:** JWT-based authentication with token storage
* **Password Reset:** OTP-based password recovery via email
* **Role-Based Access:** Admin, Manager, and Staff roles with different permissions
* **Session Management:** Remember-me functionality

### User Management

* **Employee Management:** Add, edit, delete, and view employees
* **Visitor Management:** Track visitors with check-in and check-out
* **User Accounts:** Manage user accounts and permissions

### Access Control

* **Access Logs:** Real-time logging of all access attempts
* **Field Configuration:** Customizable form fields
* **Reports:** Generate and export access reports

### System Features

* **Offline Mode:** Works offline with data synchronization when the connection is restored
* **Theme Support:** Light and Dark modes with automatic theme detection
* **Data Export:** Export logs and reports in various formats
* **Audit Trail:** Complete audit logging for all actions

## Tech Stack

### Frontend - Desktop Application

* **Python 3.11+**
* **PySide6** - Qt6 bindings for Python
* **SQLite** - Local database for offline mode
* **Keyring** - Secure credential storage
* **HTTPX** - Async HTTP client
* **Custom Components** - Shadcn-inspired design system

### Backend - API

* **Python 3.11+**
* **FastAPI** - Modern web framework
* **MongoDB** - Primary database
* **Motor** - Async MongoDB driver
* **PyJWT** - JWT token handling
* **Bcrypt** - Password hashing
* **Uvicorn** - ASGI server

## Project Structure

```text
access-control-system-python/
├── backend/                          # FastAPI Backend
│   ├── app/
│   │   ├── models/                  # MongoDB models
│   │   ├── routes/                  # API endpoints
│   │   ├── schemas/                 # Pydantic schemas
│   │   ├── services/                # Business logic
│   │   ├── config.py                # Configuration settings
│   │   ├── main.py                  # FastAPI application entry point
│   │   └── seed.py                  # Database seeding script
│   ├── .env.example                 # Environment variables template
│   └── requirements.txt             # Backend dependencies
│
├── desktop_app/                     # PySide6 Desktop Application
│   ├── assets/
│   │   ├── icons/                   # SVG icons
│   │   └── images/                  # Logo and background images
│   ├── core/                        # Core functionality
│   │   ├── api_client.py            # HTTP API client
│   │   ├── auth_manager.py          # Authentication management
│   │   ├── theme_manager.py         # Theme handling
│   │   ├── icon_manager.py          # Icon management
│   │   └── sync_manager.py          # Offline sync management
│   ├── database/
│   │   └── db_manager.py            # SQLite database operations
│   ├── dialogs/                     # Dialog windows
│   │   ├── reset_password_dialog.py
│   │   └── visitor_checkout_dialog.py
│   ├── pages/                       # Main application pages
│   │   ├── login_page.py
│   │   ├── dashboard_page.py
│   │   ├── employees_page.py
│   │   ├── visitors_page.py
│   │   ├── access_logs_page.py
│   │   └── settings_page.py
│   ├── widgets/                     # Reusable UI components
│   │   ├── components.py            # Custom widgets
│   │   ├── sidebar.py               # Navigation sidebar
│   │   ├── header.py                # Application header
│   │   └── floating_label_input.py
│   ├── themes/                      # QSS stylesheets
│   │   ├── base.qss
│   │   ├── light.qss
│   │   └── dark.qss
│   ├── utils/                       # Utility functions
│   │   ├── path_utils.py            # Path handling
│   │   └── access_control.py        # Permission utilities
│   ├── main.py                      # Application entry point
│   ├── config.py                    # App configuration
│   └── requirements.txt             # App dependencies
│
├── .env.example                     # Environment template
└── .gitignore                       # Git ignore file
```

## Prerequisites

Before installing the system, ensure the following are available:

* **Python** 3.11 or higher
* **MongoDB** 4.4 or higher, either local or MongoDB Atlas
* **Git** for version control

## Installation

### Backend Setup

#### Clone the Repository

```bash
git clone https://github.com/HillaryOduor1/icta_access_control_system.git
cd icta_access_control_system/backend
```

#### Create and Activate a Virtual Environment

##### Windows

```powershell
python -m venv venv
venv\Scripts\activate
```

##### Linux and macOS

```bash
python3 -m venv venv
source venv/bin/activate
```

#### Install Dependencies

```bash
pip install -r requirements.txt
```

#### Set Up Environment Variables

Copy the example environment file:

```bash
cp .env.example .env
```

Then edit `.env` with your configuration.

Required variables include:

* `ATLAS_URI` - MongoDB connection string
* `DB_NAME` - Database name
* `SECRET_KEY` - JWT secret key
* `SMTP_*` - Email configuration for OTP functionality

For example, a secure secret key can be generated with:

```bash
openssl rand -hex 32
```

#### Seed the Database

Database seeding is optional.

```bash
python -c "from app.seed import seed_database; seed_database()"
```

#### Run the Backend Server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at:

`http://localhost:8000`

### Desktop App Setup

#### Navigate to the Desktop Application

From the backend directory:

```bash
cd ../desktop_app
```

#### Create and Activate a Virtual Environment

##### Windows

```powershell
python -m venv venv
venv\Scripts\activate
```

##### Linux and macOS

```bash
python3 -m venv venv
source venv/bin/activate
```

#### Install Dependencies

```bash
pip install -r requirements.txt
```

#### Configure the API Endpoint

Open:

```text
core/api_client.py
```

Update the `base_url` to point to your backend.

##### Development

```python
client = APIClient(base_url="http://localhost:8000")
```

##### Production

```python
client = APIClient(base_url="https://your-api-domain.com")
```

#### Run the Application

```bash
python main.py
```

## Configuration

### Environment Variables

The backend uses environment variables for database, authentication, email, and application configuration.

### MongoDB Configuration

```env
ATLAS_URI=mongodb+srv://username:password@cluster.mongodb.net/
DB_NAME=icta_access_control
```

### JWT Configuration

```env
SECRET_KEY=your-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
```

### Email Configuration

Email configuration is used for OTP-based password recovery.

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM=your-email@gmail.com
```

### Application Configuration

```env
DEV_MODE=true
LOG_LEVEL=INFO
```

### Desktop App Configuration

Desktop application configuration is managed through `config.py`.

#### Development API Configuration

```python
API_URL = "http://localhost:8000"
```

#### Production API Configuration

```python
API_URL = "https://your-api.onrender.com"
```

Additional application settings:

```python
THEME = "system"
OFFLINE_MODE = True
```

The supported theme values are:

* `light`
* `dark`
* `system`

## Running the Application

### Quick Start

#### Start the Backend

From the project root:

```bash
cd backend
```

Activate the virtual environment.

##### Linux and macOS

```bash
source venv/bin/activate
```

##### Windows

```powershell
venv\Scripts\activate
```

Start the server:

```bash
uvicorn app.main:app --reload --port 8000
```

#### Start the Desktop Application

Open a new terminal and run:

```bash
cd desktop_app
```

Activate the virtual environment.

##### Linux and macOS

```bash
source venv/bin/activate
```

##### Windows

```powershell
venv\Scripts\activate
```

Then start the application:

```bash
python main.py
```

### Default Credentials

After seeding the database, you can log in with the default development credentials.

| Field    | Value       |
| -------- | ----------- |
| Username | `admin`     |
| Password | `Admin@123` |

> **Security note:** Change or disable default credentials before deploying the system to a production environment.

## Deployment

### Deploy Backend to Render

The backend can be deployed to Render as a web service.

#### Push the Code to GitHub

Ensure the project has been committed and pushed to your GitHub repository.

#### Create a Render Web Service

Create a new Web Service on Render and connect it to the GitHub repository.

#### Configure the Build Command

```bash
pip install -r requirements.txt
```

#### Configure the Start Command

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

#### Configure Environment Variables

Add the required environment variables through the Render dashboard.

#### Deploy

Deploy the service. Render will build and deploy the backend using the configured commands.

### Build Desktop Application

The desktop application can be packaged into a Windows executable using PyInstaller.

#### Install PyInstaller

```bash
pip install pyinstaller
```

#### Build the Executable

From the `desktop_app` directory:

```powershell
pyinstaller --name="ICTA-Access-Control" --windowed --onefile --add-data "assets;assets" --add-data "themes;themes" main.py
```

The generated executable will be placed in:

```text
dist/
```

> **Note:** The `--add-data` syntax shown above is intended for Windows. PyInstaller uses a different separator on Linux and macOS.

## API Documentation

Once the backend is running, interactive API documentation is available through FastAPI.

### Swagger UI

`http://localhost:8000/docs`

### ReDoc

`http://localhost:8000/redoc`

### Main API Endpoints

| Endpoint                | Method                 | Description                           |
| ----------------------- | ---------------------- | ------------------------------------- |
| `/auth/login`           | `POST`                 | User login with username and password |
| `/auth/forgot-password` | `POST`                 | Request password reset OTP            |
| `/auth/verify-otp`      | `POST`                 | Verify OTP and obtain reset token     |
| `/auth/reset-password`  | `POST`                 | Reset password using a reset token    |
| `/auth/refresh`         | `POST`                 | Refresh JWT token                     |
| `/users`                | `GET`                  | List users; admin access required     |
| `/users/{id}`           | `GET`, `PUT`, `DELETE` | Manage an individual user             |
| `/employees`            | `GET`, `POST`          | Employee management                   |
| `/visitors`             | `GET`, `POST`          | Visitor management                    |
| `/access-logs`          | `GET`                  | Access logs with filters              |
| `/sync`                 | `POST`                 | Synchronize offline data              |

## Contributing

Contributions should follow the project's existing development standards.

### Development Workflow

#### Fork the Repository

Create your own fork of the project.

#### Create a Feature Branch

```bash
git checkout -b feature/amazing-feature
```

#### Commit Your Changes

```bash
git commit -m "Add amazing feature"
```

#### Push the Feature Branch

```bash
git push origin feature/amazing-feature
```

#### Open a Pull Request

Create a Pull Request against the appropriate project branch.

### Coding Standards

* Follow PEP 8 guidelines.
* Use type hints.
* Write docstrings for functions.
* Keep UI components reusable.
* Maintain clear separation between UI, business logic, database, and API functionality.

## License

This project is proprietary software.

All rights reserved.

## Authors

**Hillary Oduor** - Initial Development

## Acknowledgments

This project uses and is supported by the following technologies and design systems:

* **PySide6** for Qt6 bindings for Python
* **FastAPI** for the web framework
* **MongoDB** for database storage
* **shadcn/ui** for design-system inspiration

## Support

For support, email:

`support@icta.go.ke`

You can also open an issue in the project's GitHub repository.


