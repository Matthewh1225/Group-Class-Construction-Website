from utils.database import database_cursor

# proDate is the last day of Pro access; NULL means none.
def has_active_pro(user_id):
    with database_cursor() as cursor:
        cursor.execute("SELECT 1 FROM Customer WHERE userId = %s AND proDate >= CURDATE()", (user_id,))
        return cursor.fetchone() is not None


# No expiry date means there is no subscription.
def get_user_subscription(user_id):
    with database_cursor() as cursor:
        cursor.execute("SELECT proDate, proDate >= CURDATE() AS active FROM Customer WHERE userId = %s", (user_id,))
        row = cursor.fetchone()
    if row is None or row["proDate"] is None:
        return None
    if row["active"]:
        status = "active"
    else:
        status = "expired"
    return {"plan_name": "Pro", "status": status, "current_period_end": row["proDate"]}
