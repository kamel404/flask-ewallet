from flask import Blueprint, request, jsonify, current_app
from .. import db
from ..models import User, CurrencyBalance, Transaction
from sqlalchemy.exc import IntegrityError

bp = Blueprint("auth", __name__)

def to_minor(amount_float):
    # convert decimal string/float to integer minor units (2 decimal places)
    return int(round(float(amount_float) * 100))

@bp.route("/signup", methods=["POST"])
def signup():
    data = request.get_json() or {}
    email = data.get("email")
    password = data.get("password")
    first_name = data.get("first_name")
    last_name = data.get("last_name")
    if not email or not password:
        return jsonify({"error": "email and password required"}), 400
    user = User(email=email, first_name=first_name, last_name=last_name)
    user.set_password(password)
    try:
        db.session.add(user)
        db.session.flush()
        # initialize USD and LBP balances
        for cur in ("USD", "LBP"):
            bal = CurrencyBalance(user_id=user.id, currency=cur, amount=0)
            db.session.add(bal)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "email already exists"}), 409

    return jsonify({"user_id": user.id, "email": user.email}), 201

@bp.route("/topup", methods=["POST"])
def topup():
    """
    Quick topup endpoint for testing.
    body: { "user_id": "<uuid>", "currency": "USD"|"LBP", "amount": 100.00 }
    """
    data = request.get_json() or {}
    user_id = data.get("user_id")
    currency = data.get("currency")
    amount = data.get("amount")
    if not user_id or not currency or amount is None:
        return jsonify({"error": "user_id, currency, amount required"}), 400
    try:
        minor = to_minor(amount)
    except Exception:
        return jsonify({"error": "invalid amount format"}), 400

    # lock the balance row
    from sqlalchemy import select, update, literal_column
    from sqlalchemy.orm import with_loader_criteria

    bal = db.session.execute(
        db.select(CurrencyBalance).where(CurrencyBalance.user_id == user_id, CurrencyBalance.currency == currency).with_for_update()
    ).scalar_one_or_none()
    if bal is None:
        return jsonify({"error": "balance not found for user/currency"}), 404

    bal.amount = bal.amount + minor
    tx = Transaction(from_user_id=None, to_user_id=user_id, currency=currency, amount=minor, type="topup", status="completed", metadata={})
    db.session.add(tx)
    db.session.commit()
    return jsonify({"balance_minor": bal.amount, "balance_decimal": "%.2f" % (bal.amount / 100.0)}), 200
