VISITOR_COLLECTION = "visitors"

def visitor_helper(visitor) -> dict:
    return {
        "id": str(visitor["_id"]),
        "visitor_name": visitor["visitor_name"],
        "check_in_time": visitor["check_in_time"],
        "check_out_time": visitor.get("check_out_time"),
        "host_id": visitor.get("host_id"),
        "host_name": visitor.get("host_name"),
        "status": visitor.get("status", "inside"),
        "dynamic_fields": visitor.get("dynamic_fields", {}),
        "consent_gained": visitor.get("consent_gained", False),
    }