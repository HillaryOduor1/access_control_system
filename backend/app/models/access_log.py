ACCESS_LOG_COLLECTION = "access_logs"

def access_log_helper(log) -> dict:
    return {
        "id": str(log["_id"]),
        "person_type": log["person_type"],
        "person_id": log["person_id"],
        "direction": log["direction"],
        "timestamp": log["timestamp"],
        "granted": log.get("granted", True),
        "reason": log.get("reason", ""),
        "verified_by": log.get("verified_by", "system"),
        "tenant_id": log.get("tenant_id", "default"),  # add
    }
