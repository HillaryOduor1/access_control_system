# backend/app/seed.py
# run .\venv_backend\Scripts\activate then python -m app.seed to seed 
import asyncio
from app.config import db
from app.services.auth_service import hash_password
from datetime import datetime

async def seed_database():
    # Check if users already exist
    existing = await db.users.find_one({"username": "admin"})
    if existing:
        print("Database already seeded.")
        return

    # Create roles
    roles = [
        {"name": "admin", "permissions": ["view_dashboard", "manage_visitors", "manage_employees", "view_access_logs", "configure_fields", "view_reports", "manage_settings", "manage_users"]},
        {"name": "security", "permissions": ["view_dashboard", "manage_visitors", "view_access_logs"]},
        {"name": "regular", "permissions": ["view_dashboard", "view_visitors"]},
        {"name": "finance", "permissions": ["view_dashboard", "view_reports"]},
        {"name": "staff", "permissions": ["view_dashboard", "manage_visitors"]},
    ]
    for role in roles:
        await db.roles.update_one({"name": role["name"]}, {"$set": role}, upsert=True)
    print("Roles seeded.")

    # Create default users with new fields
    users = [
        {
            "username": "admin",
            "password": "Admin@123",
            "full_name": "System Administrator",
            "first_name": "System",
            "last_name": "Admin",
            "email": "admin@ict.go.ke",
            "employee_number": "ADM001",
            "phone": "+254700000001",
            "id_number": "12345678",
            "tenant_id": "ICT Authority",
            "roles": ["admin"]
        },
        {
            "username": "security",
            "password": "Security@123",
            "full_name": "Security Officer",
            "first_name": "Security",
            "last_name": "Officer",
            "email": "security@ict.go.ke",
            "employee_number": "SEC001",
            "phone": "+254700000002",
            "id_number": "87654321",
            "tenant_id": "ICT Authority",
            "roles": ["security"]
        },
        {
            "username": "finance",
            "password": "Finance@123",
            "full_name": "Finance Officer",
            "first_name": "Finance",
            "last_name": "Officer",
            "email": "finance@ict.go.ke",
            "employee_number": "FIN001",
            "phone": "+254700000003",
            "id_number": "11223344",
            "tenant_id": "ICT Authority",
            "roles": ["finance"]
        },
        {
            "username": "staff",
            "password": "Staff@123",
            "full_name": "Staff Member",
            "first_name": "Staff",
            "last_name": "Member",
            "email": "staff@ict.go.ke",
            "employee_number": "STA001",
            "phone": "+254700000004",
            "id_number": "44332211",
            "tenant_id": "ICT Authority",
            "roles": ["staff"]
        },
    ]
    for u in users:
        u["password_hash"] = hash_password(u.pop("password"))
        u["is_active"] = True
        u["created_at"] = datetime.utcnow()
        await db.users.insert_one(u)
    print("Users seeded.")
    print("Seeding complete.")

if __name__ == "__main__":
    asyncio.run(seed_database())

