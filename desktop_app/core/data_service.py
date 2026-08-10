# core/data_service.py
from typing import List, Dict, Any, Optional
from datetime import datetime

class DataService:
    def __init__(self, api_client, db_manager, sync_manager):
        self.api = api_client
        self.db = db_manager
        self.sync = sync_manager

    # VISITORS
    def get_active_visitors(self) -> List[Dict]:
        if self.api.is_online():
            return self.api.request("GET", "/visitors/active")
        else:
            return self.db.get_active_visitors()

    def check_in_visitor(self, name: str, host_id: int, dynamic_data: Dict, consent: bool) -> int:
        visitor_dict = {
            "visitor_name": name,
            "host_id": str(host_id),
            "dynamic_fields": dynamic_data,
            "consent_gained": consent
        }
        if self.api.is_online():
            result = self.api.request("POST", "/visitors/checkin", json=visitor_dict)
            return result.get("id")
        else:
            visitor_id = self.db.check_in_visitor(name, host_id, dynamic_data, consent)
            self.db.add_sync_operation("CREATE", "visitors", str(visitor_id), visitor_dict)
            return visitor_id

    def checkout_visitor(self, visitor_id: int) -> bool:
        if self.api.is_online():
            self.api.request("POST", "/visitors/checkout", json={"visitor_id": str(visitor_id)})
            return True
        else:
            self.db.check_out_visitor(visitor_id)
            self.db.add_sync_operation("UPDATE", "visitors", str(visitor_id), {"status": "out"})
            return True

    def get_visitor_history(self, limit: int = 200) -> List[tuple]:
        if self.api.is_online():
            data = self.api.request("GET", "/visitors/history", params={"limit": limit})
            return [
                (v["id"], v["visitor_name"], v["check_in_time"], v.get("check_out_time", ""),
                 v.get("host_name", ""), v.get("status", ""))
                for v in data
            ]
        else:
            return self.db.get_visitor_history(limit)

    # EMPLOYEES
    def get_employees(self, active_only: bool = True) -> List[Dict]:
        if self.api.is_online():
            return self.api.request("GET", "/employees", params={"active_only": active_only})
        else:
            return self.db.get_employees(active_only)

    def add_employee(self, employee_id: str, full_name: str, role: str, badge_number: str,
                     dynamic_fields: Dict) -> int:
        emp_dict = {
            "employee_id": employee_id,
            "full_name": full_name,
            "role": role,
            "badge_number": badge_number,
            "dynamic_fields": dynamic_fields
        }
        if self.api.is_online():
            result = self.api.request("POST", "/employees", json=emp_dict)
            return result.get("id")
        else:
            emp_id = self.db.add_employee(employee_id, full_name, role, badge_number, dynamic_fields)
            self.db.add_sync_operation("CREATE", "employees", str(emp_id), emp_dict)
            return emp_id

    def update_employee(self, emp_id: int, full_name: str, role: str, badge_number: str,
                        dynamic_fields: Dict, is_active: bool):
        update_data = {
            "full_name": full_name,
            "role": role,
            "badge_number": badge_number,
            "dynamic_fields": dynamic_fields,
            "is_active": is_active
        }
        if self.api.is_online():
            self.api.request("PUT", f"/employees/{emp_id}", json=update_data)
        else:
            self.db.update_employee(emp_id, full_name, role, badge_number, dynamic_fields, is_active)
            self.db.add_sync_operation("UPDATE", "employees", str(emp_id), update_data)

    def deactivate_employee(self, emp_id: int):
        if self.api.is_online():
            self.api.request("DELETE", f"/employees/{emp_id}")
        else:
            self.db.deactivate_employee(emp_id)
            self.db.add_sync_operation("DELETE", "employees", str(emp_id), {})

    def get_employees_list_for_host(self) -> List[tuple]:
        if self.api.is_online():
            data = self.api.request("GET", "/employees", params={"active_only": True})
            return [(e["id"], e["full_name"]) for e in data]
        else:
            return self.db.get_employees_list_for_host()

    # ACCESS LOGS
    def get_access_logs(self, filters: Optional[Dict] = None) -> List[tuple]:
        if self.api.is_online():
            params = {}
            if filters:
                if filters.get('person_type'):
                    params['person_type'] = filters['person_type']
                if filters.get('direction'):
                    params['direction'] = filters['direction']
                if filters.get('date_from'):
                    params['from_date'] = filters['date_from']
                if filters.get('date_to'):
                    params['to_date'] = filters['date_to']
            data = self.api.request("GET", "/access-logs", params=params)
            return [
                (l["id"], l["person_type"], l["person_id"], l["direction"],
                 l["timestamp"], l["granted"], l.get("reason", ""), l.get("verified_by", ""))
                for l in data
            ]
        else:
            return self.db.get_access_logs(filters)

    # DASHBOARD STATS
    def get_dashboard_stats(self) -> Dict:
        if self.api.is_online():
            active_visitors = len(self.api.request("GET", "/visitors/active"))
            employees = self.api.request("GET", "/employees", params={"active_only": True})
            active_employees = len(employees)
            today = datetime.now().date().isoformat()
            logs = self.api.request("GET", "/access-logs", params={
                "from_date": f"{today} 00:00:00",
                "to_date": f"{today} 23:59:59"
            })
            today_entries = sum(1 for log in logs if log["direction"] == "in")
            today_checkouts = sum(1 for log in logs if log["direction"] == "out" and log["granted"])
            recent_logs = logs[:10]
            return {
                "active_visitors": active_visitors,
                "active_employees": active_employees,
                "today_entries": today_entries,
                "today_checkouts": today_checkouts,
                "recent_logs": recent_logs
            }
        else:
            active_visitors = len(self.db.get_active_visitors())
            employees = self.db.get_employees(active_only=True)
            active_employees = len(employees)
            today = datetime.now().date().isoformat()
            logs = self.db.get_access_logs()
            today_entries = sum(1 for log in logs if log[4].startswith(today) and log[3] == 'in')
            today_checkouts = sum(1 for log in logs if log[4].startswith(today) and log[3] == 'out' and log[5] == 1)
            recent_logs = logs[:10]
            return {
                "active_visitors": active_visitors,
                "active_employees": active_employees,
                "today_entries": today_entries,
                "today_checkouts": today_checkouts,
                "recent_logs": recent_logs
            }

    # REPORTS 
    def get_visitor_history_for_report(self, limit: int = 500) -> List[tuple]:
        return self.get_visitor_history(limit)

    # CUSTOM FIELDS
    def get_custom_fields(self, entity_type: str, active_only: bool = True) -> List[Dict]:
        return self.db.get_custom_fields(entity_type, active_only)

    def save_custom_field(self, entity_type: str, field_id: int, data: Dict):
        self.db.save_custom_field(entity_type, field_id, data)

    def delete_custom_field(self, entity_type: str, field_id: int):
        self.db.delete_custom_field(entity_type, field_id)

    # AUTH
    def change_password(self, user_id: int, current_password: str, new_password: str) -> tuple:
        if self.api.is_online():
            try:
                self.api.request("POST", "/auth/change-password", json={
                    "current_password": current_password,
                    "new_password": new_password
                })
                return True, "Password changed"
            except Exception as e:
                return False, str(e)
        else:
            return False, "Cannot change password offline"

    def update_profile(self, user_id: int, full_name: str, email: str) -> tuple:
        if self.api.is_online():
            try:
                self.api.request("PUT", "/users/me", json={"full_name": full_name, "email": email})
                return True, "Profile updated"
            except Exception as e:
                return False, str(e)
        else:
            return False, "Cannot update profile offline"

    # USER MANAGEMENT (Admin only)
    def get_users(self) -> List[Dict]:
        if self.api.is_online():
            return self.api.request("GET", "/users")
        else:
            # For offline, we could return cached list if needed, but we'll raise an error.
            raise ConnectionError("User management requires online access")

    def get_user(self, user_id: str) -> Optional[Dict]:
        if self.api.is_online():
            return self.api.request("GET", f"/users/{user_id}")
        else:
            raise ConnectionError("User management requires online access")

    def create_user(self, payload: Dict) -> Dict:
        if self.api.is_online():
            return self.api.request("POST", "/users", json=payload, need_auth=True)
        else:
            raise ConnectionError("User management requires online access")

    def update_user(self, user_id: str, payload: Dict) -> Dict:
        if self.api.is_online():
            return self.api.request("PUT", f"/users/{user_id}", json=payload, need_auth=True)
        else:
            raise ConnectionError("User management requires online access")

    def deactivate_user(self, user_id: str) -> Dict:
        if self.api.is_online():
            return self.api.request("DELETE", f"/users/{user_id}", need_auth=True)
        else:
            raise ConnectionError("User management requires online access")
 