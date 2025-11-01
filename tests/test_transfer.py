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


def signup(client, email):
    r = client.post("/api/auth/signup", json={"email": email, "password": "pw"})
    assert r.status_code == 201
    return r.get_json()["user_id"]


def topup(client, user_id, amount):
    r = client.post("/api/auth/topup", json={"user_id": user_id, "currency": "USD", "amount": amount})
    assert r.status_code == 200


def test_transfer_success_and_insufficient(client):
    ua = signup(client, "a@example.com")
    ub = signup(client, "b@example.com")

    topup(client, ua, 100.00)

    # successful transfer 25.50
    r = client.post(
        "/api/transfer/transfer",
        json={"from_user_id": ua, "to_user_id": ub, "currency": "USD", "amount": 25.50},
    )
    assert r.status_code == 200

    with client.application.app_context():
        b_from = db.session.query(CurrencyBalance).filter_by(user_id=ua, currency="USD").one()
        b_to = db.session.query(CurrencyBalance).filter_by(user_id=ub, currency="USD").one()
        assert b_from.amount == 10000 - 2550
        assert b_to.amount == 2550

    # insufficient funds
    r2 = client.post(
        "/api/transfer/transfer",
        json={"from_user_id": ua, "to_user_id": ub, "currency": "USD", "amount": 1000.00},
    )
    assert r2.status_code == 402
    assert r2.get_json().get("error") == "insufficient_funds"
