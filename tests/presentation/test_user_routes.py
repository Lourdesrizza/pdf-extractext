from datetime import datetime

from app.domain.entities.user import User


def _user() -> User:
    return User(
        id="507f1f77bcf86cd799439011",
        email="usuario@example.com",
        full_name="Usuario Ejemplo",
        created_at=datetime(2026, 1, 1),
    )


def test_create_user_returns_created_user(client, mock_user_repo):
    user = _user()
    mock_user_repo.create.return_value = user

    response = client.post(
        "/api/v1/users/",
        json={"email": user.email, "full_name": user.full_name},
    )

    assert response.status_code == 201
    assert response.json()["email"] == user.email
    mock_user_repo.create.assert_awaited_once()


def test_create_user_rejects_duplicate_email(client, mock_user_repo):
    mock_user_repo.find_by_email.return_value = _user()

    response = client.post(
        "/api/v1/users/",
        json={"email": "usuario@example.com", "full_name": "Otro Usuario"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "El email ya está registrado"


def test_get_user_returns_not_found_problem(client):
    response = client.get("/api/v1/users/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Usuario con ID 'missing' no encontrado"


def test_get_all_users_returns_users(client, mock_user_repo):
    mock_user_repo.find_all.return_value = [_user()]

    response = client.get("/api/v1/users/")

    assert response.status_code == 200
    assert response.json()[0]["full_name"] == "Usuario Ejemplo"


def test_update_user_updates_profile(client, mock_user_repo):
    user = _user()
    mock_user_repo.find_by_id.return_value = user
    mock_user_repo.update.side_effect = lambda updated: updated

    response = client.put(
        f"/api/v1/users/{user.id}", json={"full_name": "Nuevo Nombre"}
    )

    assert response.status_code == 200
    assert response.json()["full_name"] == "Nuevo Nombre"


def test_deactivate_user_marks_user_inactive(client, mock_user_repo):
    user = _user()
    mock_user_repo.find_by_id.return_value = user
    mock_user_repo.update.side_effect = lambda updated: updated

    response = client.patch(f"/api/v1/users/{user.id}/deactivate")

    assert response.status_code == 200
    assert response.json()["is_active"] is False


def test_delete_user_delegates_to_repository(client, mock_user_repo):
    user = _user()
    mock_user_repo.find_by_id.return_value = user

    response = client.delete(f"/api/v1/users/{user.id}")

    assert response.status_code == 204
    mock_user_repo.delete.assert_awaited_once_with(user.id)
