from flask import Blueprint, request, jsonify
from .. import db
from ..models import Card, CardAuthRequest, CurrencyBalance, Transaction
from datetime import datetime

bp = Blueprint("webhook", __name__)

CURRENCY_MAP = {"840": "USD", "422": "LBP"}  # 840 USD, 422 LB
MINOR_UNITS = {"USD": 2, "LBP": 2}  # using 2 decimals for simplicity

def parse_minor(amount_str, currency="USD"):
    # amount_str like "27.50" -> minor units int
    return int(round(float(amount_str) * (10 ** MINOR_UNITS.get(currency, 2))))

def build_response_template(req, action_code, approval_code, new_balance_minor):
    # required fields per spec
    tpl = {
        "messageType": "2110",
        "primaryAccountNumber": req.get("primaryAccountNumber"),
        "processingCode": req.get("processingCode"),
        "amountTransaction": req.get("amountTransaction"),
        "amountCardholderBilling": req.get("amountCardholderBilling"),
        "dateAndTimeTransmission": req.get("dateAndTimeTransmission"),
        "conversionRateCardholderBilling": req.get("conversionRateCardholderBilling"),
        "systemsTraceAuditNumber": req.get("systemsTraceAuditNumber"),
        "dateCapture": req.get("dateCapture"),
        "merchantCategoryCode": req.get("merchantCategoryCode"),
        "acquiringInstitutionIdentificationCode": req.get("acquiringInstitutionIdentificationCode"),
        "retrievalReferenceNumber": req.get("retrievalReferenceNumber"),
        "cardAcceptorTerminalIdentification": req.get("cardAcceptorTerminalIdentification"),
        "cardAcceptorIdentificationCode": req.get("cardAcceptorIdentificationCode"),
        "cardAcceptorName": req.get("cardAcceptorName"),
        "cardAcceptorCity": req.get("cardAcceptorCity"),
        "cardAcceptorCountryCode": req.get("cardAcceptorCountryCode"),
        "posDataCode": req.get("posDataCode"),
        "cardExpiry": req.get("cardExpiry"),
        "actionCode": action_code,
        "approvalCode": approval_code,
        "additionalAmounts": [
            {
                "accountType": "00",
                "amountType": "02",
                "currencyCode": req.get("currencyCode", "840"),
                "currencyMinorUnit": str(MINOR_UNITS.get(CURRENCY_MAP.get(req.get("currencyCode","840"), "USD"), 2)),
                "amountSign": "C",
                "value": str(new_balance_minor).rjust(12, "0")
            }
        ]
    }
    return tpl

@bp.route("/webhook/authorize", methods=["POST"])
def authorize():
    req = request.get_json() or {}
    idem = req.get("idempotency_key")
    if not idem:
        return jsonify({"error": "idempotency_key required"}), 400

    # return existing if processed
    existing = db.session.query(CardAuthRequest).filter_by(idempotency_key=idem).first()
    if existing:
        return jsonify(existing.response_payload), 200

    # parse basic fields
    pan = req.get("primaryAccountNumber")
    amount_str = req.get("amountTransaction")
    currency_code = req.get("currencyCode", "840")
    currency = CURRENCY_MAP.get(currency_code, "USD")
    txn_ref = req.get("txn_ref")

    # find card by masked PAN
    card = db.session.query(Card).filter_by(pan_masked=pan).first()
    if not card:
        resp = build_response_template(req, action_code="05", approval_code="000000", new_balance_minor=0)
        # store record
        record = CardAuthRequest(idempotency_key=idem, request_payload=req, response_payload=resp)
        db.session.add(record)
        db.session.commit()
        return jsonify(resp), 200

    if card.status != "active":
        resp = build_response_template(req, action_code="57", approval_code="000000", new_balance_minor=0)
        record = CardAuthRequest(idempotency_key=idem, request_payload=req, response_payload=resp)
        db.session.add(record); db.session.commit()
        return jsonify(resp), 200

    # E-commerce checks
    ecom = req.get("ecom")
    if ecom:
        # sample policy: require 3DS frictionless and AVS Y to approve
        if ecom.get("three_ds") != "frictionless" or ecom.get("avs_result") != "Y":
            resp = build_response_template(req, action_code="05", approval_code="000000", new_balance_minor=0)
            record = CardAuthRequest(idempotency_key=idem, request_payload=req, response_payload=resp)
            db.session.add(record); db.session.commit()
            return jsonify(resp), 200

    # parse amount
    try:
        amount_minor = parse_minor(amount_str, currency)
    except Exception:
        resp = build_response_template(req, action_code="05", approval_code="000000", new_balance_minor=0)
        record = CardAuthRequest(idempotency_key=idem, request_payload=req, response_payload=resp)
        db.session.add(record); db.session.commit()
        return jsonify(resp), 200

    if amount_minor <= 0:
        resp = build_response_template(req, action_code="05", approval_code="000000", new_balance_minor=0)
        record = CardAuthRequest(idempotency_key=idem, request_payload=req, response_payload=resp)
        db.session.add(record); db.session.commit()
        return jsonify(resp), 200

    # attempt to debit under transaction and lock balance
    bal = db.session.execute(
        db.select(CurrencyBalance).where(CurrencyBalance.user_id == card.user_id, CurrencyBalance.currency == currency).with_for_update()
    ).scalar_one_or_none()
    if bal is None:
        resp = build_response_template(req, action_code="05", approval_code="000000", new_balance_minor=0)
        record = CardAuthRequest(idempotency_key=idem, request_payload=req, response_payload=resp)
        db.session.add(record); db.session.commit()
        return jsonify(resp), 200

    if bal.amount < amount_minor:
        resp = build_response_template(req, action_code="51", approval_code="000000", new_balance_minor=bal.amount)
        record = CardAuthRequest(idempotency_key=idem, request_payload=req, response_payload=resp)
        db.session.add(record); db.session.commit()
        return jsonify(resp), 200

    # debit and create transaction
    bal.amount = bal.amount - amount_minor
    tx = Transaction(from_user_id=card.user_id, to_user_id=None, currency=currency, amount=amount_minor, type="card_payment", status="completed", metadata={"txn_ref": txn_ref})
    db.session.add(tx)
    db.session.flush()  # get tx.id

    approval_code = tx.id[:6] if isinstance(tx.id, str) else "000000"
    resp = build_response_template(req, action_code="00", approval_code=approval_code, new_balance_minor=bal.amount)
    record = CardAuthRequest(idempotency_key=idem, request_payload=req, response_payload=resp)
    db.session.add(record)
    db.session.commit()
    return jsonify(resp), 200
