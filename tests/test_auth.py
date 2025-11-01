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


def test_signup_initial_balances(client):
    r = client.post("/api/auth/signup", json={"email": "user@example.com", "password": "pw"})
    assert r.status_code == 201
    uid = r.get_json()["user_id"]

    with client.application.app_context():
        usd = db.session.query(CurrencyBalance).filter_by(user_id=uid, currency="USD").one()
        lbp = db.session.query(CurrencyBalance).filter_by(user_id=uid, currency="LBP").one()
        assert usd.amount == 0
        assert lbp.amount == 0


def test_topup_and_validation(client):
    # need a user first
    r = client.post("/api/auth/signup", json={"email": "a@b.com", "password": "pw"})
    uid = r.get_json()["user_id"]

    # missing fields
    r_bad = client.post("/api/auth/topup", json={})
    assert r_bad.status_code == 400

    # invalid amount format
    r_bad2 = client.post("/api/auth/topup", json={"user_id": uid, "currency": "USD", "amount": "abc"})
    assert r_bad2.status_code == 400

    # success
    r_ok = client.post("/api/auth/topup", json={"user_id": uid, "currency": "USD", "amount": 50.25})
    assert r_ok.status_code == 200
    body = r_ok.get_json()
    assert body["balance_minor"] == 5025
    assert body["balance_decimal"] == "50.25"
