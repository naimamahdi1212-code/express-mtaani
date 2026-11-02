from app.extensions import db
from app.models import LoginAttempt, User
from tests.conftest import login, make_user


def test_static_files_are_served(app):
    c = app.test_client()
    assert c.get("/static/css/style.css").status_code == 200
    assert c.get("/static/js/maps-common.js").status_code == 200
    assert c.get("/static/img/logo.png").status_code == 200


def test_health_check(app):
    r = app.test_client().get("/healthz")
    assert r.status_code == 200 and r.get_json() == {"status": "ok"}


def test_failed_logins_are_counted_in_the_database(app, data):
    c = app.test_client()
    for _ in range(5):
        c.post("/login", data={"email": "amina@example.com", "password": "nope-nope"})
    assert LoginAttempt.query.count() == 5
    assert b"Too many attempts" in c.post("/login", data={"email": "amina@example.com", "password": "password123"}).data


def test_success_clears_failures_and_records_last_login(app, data):
    c = app.test_client()
    c.post("/login", data={"email": "amina@example.com", "password": "nope-nope"})
    assert LoginAttempt.query.count() == 1
    login(app, "amina@example.com")
    assert LoginAttempt.query.count() == 0
    assert db.session.get(User, data["customer"].id).last_login_at is not None


def test_admin_users_page_and_deactivate(app, data):
    admin = login(app, "boss@example.com")
    page = admin.get("/admin/users").get_data(as_text=True)
    assert "amina@example.com" in page and "brian@example.com" in page
    assert "amina@example.com" in admin.get("/admin/users?q=amina").get_data(as_text=True)
    assert "brian@example.com" not in admin.get("/admin/users?q=amina").get_data(as_text=True)
    assert "brian@example.com" not in admin.get("/admin/users?role=customer").get_data(as_text=True)
    assert admin.get("/admin/users?q=%25").status_code == 200

    customer = login(app, "amina@example.com")
    assert customer.get("/account/orders").status_code == 200
    admin.post(f"/admin/users/{data['customer'].id}/deactivate")
    db.session.expire_all()
    assert db.session.get(User, data["customer"].id).active is False
    assert customer.get("/account/orders").status_code == 302          # signed out on the next request
    admin.post(f"/admin/users/{data['customer'].id}/activate")
    db.session.expire_all()
    assert db.session.get(User, data["customer"].id).active is True


def test_admins_cannot_be_deactivated_from_the_users_page(app, data):
    admin = login(app, "boss@example.com")
    admin.post(f"/admin/users/{data['admin'].id}/deactivate")
    other = make_user("second@example.com", "admin")
    admin.post(f"/admin/users/{other.id}/deactivate")
    db.session.expire_all()
    assert db.session.get(User, data["admin"].id).active is True
    assert db.session.get(User, other.id).active is True
    assert admin.post(f"/admin/users/{data['customer'].id}/explode").status_code == 404


def test_users_and_system_pages_are_admin_only(app, data):
    customer = login(app, "amina@example.com")
    assert customer.get("/admin/users").status_code == 403
    assert customer.get("/admin/system").status_code == 403
    assert customer.post(f"/admin/users/{data['rider1'].id}/deactivate").status_code == 403
    assert app.test_client().get("/admin/system").status_code == 302


def test_system_page_hides_secrets(app, data):
    app.config["GEOAPIFY_API_KEY"] = "abcd1234efgh567890XY"
    page = login(app, "boss@example.com").get("/admin/system").get_data(as_text=True)
    assert "sqlite" in page and "Connected" in page
    assert "90XY" in page                                 # only the last 4 characters are shown
    assert "abcd1234efgh567890XY" not in page


def test_health_check_reports_missing_tables(app):
    db.drop_all()
    r = app.test_client().get("/healthz")
    assert r.status_code == 503 and "init-db" in r.get_json()["status"]
    db.create_all()
