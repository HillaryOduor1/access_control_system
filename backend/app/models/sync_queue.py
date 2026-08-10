SYNC_META_COLLECTION = "sync_meta"

def sync_meta_helper(meta) -> dict:
    return {
        "client_id": meta["client_id"],
        "last_sync": meta.get("last_sync"),
        "device_info": meta.get("device_info", {}),
    }