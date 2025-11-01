# test_app.py
import os
import pytest
from app import create_app, db
from app.models import CurrencyBalance

@pytest.fixture
def client():
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    app = create_app("testing")
    app.config["TESTING"] = True
    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.session.remove()
        db.drop_all()

def test_signup_topup_transfer_and_webhooks(client):
    # --- SIGNUP TWO USERS ---
    r1 = client.post("/api/auth/signup", json={"email": "kamel@example.com", "password": "pw123"})
    r2 = client.post("/api/auth/signup", json={"email": "ali@example.com", "password": "pw123"})
    assert r1.status_code == 201
    assert r2.status_code == 201
    ua = r1.get_json()["user_id"]
    ub = r2.get_json()["user_id"]

    # --- CHECK BALANCES INITIALIZED ---
    with client.application.app_context():
        bal_usd = db.session.query(CurrencyBalance).filter_by(user_id=ua, currency="USD").one()
        bal_lbp = db.session.query(CurrencyBalance).filter_by(user_id=ua, currency="LBP").one()
        assert bal_usd.amount == 0
        assert bal_lbp.amount == 0

    # --- TOPUP USER A ---
    rtop = client.post("/api/auth/topup", json={"user_id": ua, "currency": "USD", "amount": 100.00})
    assert rtop.status_code == 200
    b0 = rtop.get_json()["balance_minor"]
    assert b0 == 10000  # minor units

    # --- P2P TRANSFER USD 25.50 A -> B ---
    rtx = client.post("/api/transfer/transfer", json={"from_user_id": ua, "to_user_id": ub, "currency": "USD", "amount": 25.50})
    assert rtx.status_code == 200
    with client.application.app_context():
        b_from = db.session.query(CurrencyBalance).filter_by(user_id=ua, currency="USD").one()
        b_to = db.session.query(CurrencyBalance).filter_by(user_id=ub, currency="USD").one()
        assert b_from.amount == 10000 - 2550
        assert b_to.amount == 2550

    # --- CREATE CARD FOR USER A ---
    card_payload = {
        "user_id": ua,
        "pan_masked": "545454******5454",
        "card_type": "physical",
        "status": "active",
        "expiry": "1226"
    }
    r_card = client.post("/api/payments/create-card", json=card_payload)
    assert r_card.status_code == 201
    card_data = r_card.get_json()
    pan = card_data["pan_masked"]

    # --- WEBHOOK: RETAIL (CARD-PRESENT) APPROVE ---
    retail_payload = {
        "messageType": "0100",
        "processingCode": "000000",
        "primaryAccountNumber": pan,
        "amountTransaction": "10.00",
        "amountCardholderBilling": "10.00",
        "dateAndTimeTransmission": "2025-10-26T13:04:15Z",
        "conversionRateCardholderBilling": "1.000000",
        "systemsTraceAuditNumber": "847392",
        "dateCapture": "2025-10-26",
        "merchantCategoryCode": "5411",
        "acquiringInstitutionIdentificationCode": "ACQ001",
        "retrievalReferenceNumber": "012345678901",
        "cardAcceptorTerminalIdentification": "T98765",
        "cardAcceptorIdentificationCode": "MRC123",
        "cardAcceptorName": "SuperMart Downtown",
        "cardAcceptorCity": "Beirut",
        "cardAcceptorCountryCode": "422",
        "entry_mode": "chip",
        "currencyCode": "840",
        "txn_ref": "BANK_TXN_001122",
        "idempotency_key": "idem-retail-1"
    }
    r_retail = client.post("/api/webhook/webhook/authorize", json=retail_payload)
    assert r_retail.status_code == 200
    jr_retail = r_retail.get_json()
    assert jr_retail["actionCode"] == "00"

    # --- WEBHOOK: E-COMMERCE (CARD-NOT-PRESENT) DECLINE ---
    ecommerce_payload = {
        "messageType": "0100",
        "processingCode": "000000",
        "primaryAccountNumber": pan,
        "amountTransaction": "15.00",
        "amountCardholderBilling": "15.00",
        "dateAndTimeTransmission": "2025-10-26T13:10:00Z",
        "conversionRateCardholderBilling": "1.000000",
        "systemsTraceAuditNumber": "847393",
        "merchantCategoryCode": "5732",
        "acquiringInstitutionIdentificationCode": "ACQ007",
        "retrievalReferenceNumber": "012345678902",
        "cardAcceptorIdentificationCode": "ECM456",
        "cardAcceptorName": "Acme Online",
        "cardAcceptorCity": "Beirut",
        "cardAcceptorCountryCode": "422",
        "currencyCode": "840",
        "ecom": {
            "avs_result": "N",        # should fail (Y required)
            "three_ds": "frictionless",
            "ip_address": "203.0.113.24",
            "channel": "web"
        },
        "txn_ref": "BANK_TXN_001123",
        "idempotency_key": "idem-ecom-1"
    }
    r_ecom = client.post("/api/webhook/webhook/authorize", json=ecommerce_payload)
    assert r_ecom.status_code == 200
    jr_ecom = r_ecom.get_json()
    assert jr_ecom["actionCode"] != "00"  # should decline

    # --- IDEMPOTENCY CHECK ---
    # repeat retail request -> same response
    r2 = client.post("/api/webhook/webhook/authorize", json=retail_payload)
    assert r2.status_code == 200
    assert r2.get_json() == jr_retail
