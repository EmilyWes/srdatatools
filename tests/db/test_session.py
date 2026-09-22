import platformdirs

from app.db.session import default_db_path


def test_default_db_path__resolves_under_platform_user_data_dir() -> None:
    expected_dir = platformdirs.user_data_path("srdatatools", appauthor=False)

    db_path = default_db_path()

    assert db_path.parent == expected_dir
    assert db_path.name == "srdatatools.db"
    assert db_path.parent.is_dir()
