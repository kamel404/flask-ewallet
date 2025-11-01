import os
import pytest
from app import create_app, db


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


def setup_user_card_and_topup(client):
    # signup
    r = client.post("/api/auth/signup", json={"email": "shopper@example.com", "password": "pw"})
    assert r.status_code == 201
    user_id = r.get_json()["user_id"]

    # top up USD
    r2 = client.post("/api/auth/topup", json={"user_id": user_id, "currency": "USD", "amount": 100.00})
    assert r2.status_code == 200

    # create card
    card_payload = {
        "user_id": user_id,
        "pan_masked": "545454******5454",
        "card_type": "physical",
        "status": "active",
        "expiry": "1226",
    }
    r3 = client.post("/api/payments/create-card", json=card_payload)
    assert r3.status_code == 201
    pan = r3.get_json()["pan_masked"]
    return user_id, pan


def test_webhook_authorize_and_idempotency(client):
    uid, pan = setup_user_card_and_topup(client)

    # Retail approve
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
        "idempotency_key": "idem-retail-1",
    }
    r_retail = client.post("/api/webhook/webhook/authorize", json=retail_payload)
    assert r_retail.status_code == 200
    jr = r_retail.get_json()
    assert jr["actionCode"] == "00"

    # Ecom decline due to AVS N
    ecom_payload = {
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
        "ecom": {"avs_result": "N", "three_ds": "frictionless", "ip_address": "203.0.113.24", "channel": "web"},
        "txn_ref": "BANK_TXN_001123",
        "idempotency_key": "idem-ecom-1",
    }
    r_ecom = client.post("/api/webhook/webhook/authorize", json=ecom_payload)
    assert r_ecom.status_code == 200
    assert r_ecom.get_json()["actionCode"] != "00"

    # idempotency: repeat retail
    r_repeat = client.post("/api/webhook/webhook/authorize", json=retail_payload)
    assert r_repeat.status_code == 200
    assert r_repeat.get_json() == jr
