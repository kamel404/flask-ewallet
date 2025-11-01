"""
Seed script:
- Creates two users (kamel, ali)
- Initializes balances in USD/LBP
- Tops up Kamel with $200
- Creates a physical card for Kamel

Run:
    python seed.py
or:
    FLASK_APP=manage.py flask shell --command 'exec(open("seed.py").read())'
"""

import os
from app import create_app, db
from app.models import User, CurrencyBalance, Card

app = create_app(os.getenv("FLASK_ENV") or "development")

def run():
    with app.app_context():
        try:
            # Clean old data for a fresh demo
            db.session.query(Card).delete()
            db.session.query(CurrencyBalance).delete()
            db.session.query(User).delete()
            db.session.commit()

            # Create demo users
            kamel = User(email="kamel@example.com", first_name="Kamel")
            kamel.set_password("pass123")

            ali = User(email="ali@example.com", first_name="Ali")
            ali.set_password("pass123")

            db.session.add_all([kamel, ali])
            db.session.flush()

            # Initialize balances for each user
            for user in (kamel, ali):
                db.session.add(CurrencyBalance(user_id=user.id, currency="USD", amount=0))
                db.session.add(CurrencyBalance(user_id=user.id, currency="LBP", amount=0))
            db.session.flush()

            # Top up Kamel $200 (in minor units = 20000)
            usd_balance = CurrencyBalance.query.filter_by(user_id=kamel.id, currency="USD").one()
            usd_balance.amount = 20000

            # Create Kamel's card
            card = Card(
                user_id=kamel.id,
                pan_masked="545454******5454",
                card_type="physical",
                status="active",
                expiry="12/26"
            )
            db.session.add(card)
            db.session.commit()

            print("✅ Demo seed completed successfully.")
            print(f"Kamel ID: {kamel.id}, Ali ID: {ali.id}")
            print(f"Kamel USD balance (minor units): {usd_balance.amount}")
            print(f"Kamel Card: {card.pan_masked}, status: {card.status}")

        except Exception as e:
            db.session.rollback()
            print("❌ Seed failed:", e)

if __name__ == "__main__":
    run()
