from sqlalchemy.orm import Session

from app.db.models import AppSetting


def get_setting(session: Session, key: str) -> str | None:
    setting = session.get(AppSetting, key)
    return setting.value if setting is not None else None


def set_setting(session: Session, key: str, value: str) -> None:
    session.merge(AppSetting(key=key, value=value))


def delete_setting(session: Session, key: str) -> None:
    setting = session.get(AppSetting, key)
    if setting is not None:
        session.delete(setting)
