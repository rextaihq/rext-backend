import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from src.api.database.async_database import SyncSessionLocal
from src.api.models.user_models.users import Users
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import UserSubscription, SubscriptionStatus, BillingPeriod
import uuid
from datetime import datetime, timezone, timedelta

def upgrade_user_to_agency(email: str):
    db: Session = SyncSessionLocal()
    try:
        user = db.query(Users).filter(Users.email == email).first()
        if not user:
            print(f"User {email} not found.")
            return

        agency_plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.name.ilike('%agency%')).first()
        if not agency_plan:
            print("Agency plan not found in database. Available plans:")
            for plan in db.query(SubscriptionPlan).all():
                print(f"- {plan.name}")
            return
            
        print(f"Found user: {user.id} ({user.email})")
        print(f"Found plan: {agency_plan.id} ({agency_plan.name})")

        # Check existing subscription
        sub = db.query(UserSubscription).filter(UserSubscription.user_id == user.id).first()
        
        now = datetime.now(timezone.utc)
        future = now + timedelta(days=365)
        
        if sub:
            print("Updating existing subscription...")
            sub.plan_id = agency_plan.id
            sub.status = SubscriptionStatus.ACTIVE
            sub.billing_period = BillingPeriod.YEARLY
            sub.current_period_end = future
            sub.current_credits = 5000
            sub.updated_at = now
        else:
            print("Creating new subscription...")
            sub = UserSubscription(
                user_id=user.id,
                plan_id=agency_plan.id,
                status=SubscriptionStatus.ACTIVE,
                billing_period=BillingPeriod.YEARLY,
                current_period_start=now,
                current_period_end=future,
                current_credits=5000
            )
            db.add(sub)
            
        db.commit()
        print(f"Successfully upgraded {email} to {agency_plan.name} plan.")

    except Exception as e:
        print(f"An error occurred: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    upgrade_user_to_agency("haroonahmed.revnix@gmail.com")
