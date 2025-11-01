from flask import Blueprint, request, jsonify
from .. import db
from ..models import CurrencyBalance, Transaction
from sqlalchemy.exc import NoResultFound

bp = Blueprint("transfer", __name__)

def to_minor(amount_float):
    return int(round(float(amount_float) * 100))

@bp.route("/transfer", methods=["POST"])
def transfer():
    """
    Transfer between users in same currency.
    body: { "from_user_id": "...", "to_user_id": "...", "currency": "USD", "amount": 10.50 }
    """
    data = request.get_json() or {}
    from_user = data.get("from_user_id")
    to_user = data.get("to_user_id")
    currency = data.get("currency")
    amount = data.get("amount")
    if not from_user or not to_user or not currency or amount is None:
        return jsonify({"error": "from_user_id,to_user_id,currency,amount required"}), 400

    try:
        minor = to_minor(amount)
    except Exception:
        return jsonify({"error": "invalid amount"}), 400
    if minor <= 0:
        return jsonify({"error": "amount must be > 0"}), 400

    # to avoid deadlocks, lock balances in deterministic order by (user_id, currency)
    key1 = (from_user, currency)
    key2 = (to_user, currency)
    ordered = sorted([key1, key2], key=lambda k: (k[0], k[1]))
    # fetch and lock
    balances = {}
    for uid, cur in ordered:
        bal = db.session.execute(
            db.select(CurrencyBalance).where(CurrencyBalance.user_id == uid, CurrencyBalance.currency == cur).with_for_update()
        ).scalar_one_or_none()
        if bal is None:
            return jsonify({"error": f"balance not found for user {uid} currency {cur}"}), 404
        balances[(uid, cur)] = bal

    b_from = balances[(from_user, currency)]
    b_to = balances[(to_user, currency)]

    if b_from.amount < minor:
        return jsonify({"error": "insufficient_funds"}), 402

    b_from.amount = b_from.amount - minor
    b_to.amount = b_to.amount + minor

    tx = Transaction(from_user_id=from_user, to_user_id=to_user, currency=currency, amount=minor, type="p2p", status="completed", metadata={})
    db.session.add(tx)
    db.session.commit()
    return jsonify({"tx_id": tx.id, "from_new_balance": b_from.amount, "to_new_balance": b_to.amount}), 200
