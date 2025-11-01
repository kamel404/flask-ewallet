from flask import Blueprint, request, jsonify
from .. import db
from ..models import CurrencyBalance, Transaction, User, Card
from sqlalchemy.exc import IntegrityError

bp = Blueprint("payments", __name__)

def to_minor(amount_float):
    return int(round(float(amount_float) * 100))

@bp.route("/payments", methods=["POST"])
def create_payment():
    """
    Simulate a payment from a user to a merchant (or another user).
    body: { "from_user_id": "<uuid>", "to_user_id": "<uuid or null>", "currency": "USD", "amount": 25.00, "description": "Store purchase" }
    """
    data = request.get_json() or {}
    from_user = data.get("from_user_id")
    to_user = data.get("to_user_id")
    currency = data.get("currency")
    amount = data.get("amount")
    description = data.get("description", "")

    if not from_user or not currency or amount is None:
        return jsonify({"error": "from_user_id, currency, amount required"}), 400

    try:
        minor = to_minor(amount)
    except Exception:
        return jsonify({"error": "invalid amount format"}), 400

    # lock sender balance
    bal_from = db.session.execute(
        db.select(CurrencyBalance).where(CurrencyBalance.user_id == from_user, CurrencyBalance.currency == currency).with_for_update()
    ).scalar_one_or_none()
    if bal_from is None:
        return jsonify({"error": f"balance not found for user {from_user} currency {currency}"}), 404

    if bal_from.amount < minor:
        return jsonify({"error": "insufficient_funds"}), 402

    # if to_user provided, credit receiver
    bal_to = None
    if to_user:
        bal_to = db.session.execute(
            db.select(CurrencyBalance).where(CurrencyBalance.user_id == to_user, CurrencyBalance.currency == currency).with_for_update()
        ).scalar_one_or_none()
        if bal_to is None:
            return jsonify({"error": f"receiver balance not found for {currency}"}), 404

    # perform debit / credit
    bal_from.amount -= minor
    if bal_to:
        bal_to.amount += minor

    # create transaction record
    tx = Transaction(
        from_user_id=from_user,
        to_user_id=to_user,
        currency=currency,
        amount=minor,
        type="payment",
        status="completed",
        details={"description": description},
    )
    db.session.add(tx)
    db.session.commit()

    return jsonify({
        "transaction_id": tx.id,
        "status": tx.status,
        "new_balance_minor": bal_from.amount,
        "new_balance_decimal": "%.2f" % (bal_from.amount / 100.0),
    }), 201


@bp.route("/payments/history/<user_id>", methods=["GET"])
def payment_history(user_id):
    """
    Get user's transaction history.
    """
    transactions = Transaction.query.filter(
        (Transaction.from_user_id == user_id) | (Transaction.to_user_id == user_id)
    ).order_by(Transaction.created_at.desc()).all()

    data = []
    for tx in transactions:
        data.append({
            "id": tx.id,
            "from_user_id": tx.from_user_id,
            "to_user_id": tx.to_user_id,
            "currency": tx.currency,
            "amount": "%.2f" % (tx.amount / 100.0),
            "type": tx.type,
            "status": tx.status,
            "details": tx.details,
            "created_at": tx.created_at.isoformat(),
        })
    return jsonify(data), 200


@bp.route("/wallets/<user_id>", methods=["GET"])
def get_wallets(user_id):
    """
    Get all wallet balances for a user.
    """
    balances = CurrencyBalance.query.filter_by(user_id=user_id).all()
    result = []
    for b in balances:
        result.append({
            "currency": b.currency,
            "balance_minor": b.amount,
            "balance_decimal": "%.2f" % (b.amount / 100.0),
        })
    return jsonify(result), 200

from flask import request, jsonify

@bp.route("/create-card", methods=["POST"])
def create_card():
    data = request.get_json()

    user_id = data.get("user_id")
    pan_masked = data.get("pan_masked")
    card_type = data.get("card_type", "physical")
    status = data.get("status", "active")
    expiry = data.get("expiry", "1226")

    if not user_id or not pan_masked:
        return jsonify({"error": "user_id and pan_masked are required"}), 400

    card = Card(
        user_id=user_id,
        pan_masked=pan_masked,
        card_type=card_type,
        status=status,
        expiry=expiry
    )
    db.session.add(card)
    db.session.commit()

    return jsonify({
        "id": card.id,
        "user_id": card.user_id,
        "pan_masked": card.pan_masked,
        "card_type": card.card_type,
        "status": card.status,
        "expiry": card.expiry
    }), 201

