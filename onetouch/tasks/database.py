"""
Helper funkcije za rad sa bazom podataka u Celery taskovima.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from contextlib import contextmanager


def create_task_session(database_uri):
    """
    Kreira SQLAlchemy sesiju za Celery task.

    Args:
        database_uri: Kompletan URI za konekciju na bazu (SQLALCHEMY_DATABASE_URI)

    Returns:
        Session: SQLAlchemy sesija

    Example:
        session = create_task_session(database_uri)
        try:
            record = session.query(TransactionRecord).get(record_id)
            session.commit()
        finally:
            session.close()
    """
    engine = create_engine(
        database_uri,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=5,
        max_overflow=10
    )
    Session = scoped_session(sessionmaker(bind=engine))
    return Session()


@contextmanager
def task_session_scope(database_uri):
    """
    Context manager za automatsko upravljanje sesijom u Celery taskovima.

    Args:
        database_uri: Kompletan URI za konekciju na bazu

    Yields:
        Session: SQLAlchemy sesija

    Example:
        with task_session_scope(database_uri) as session:
            record = session.query(TransactionRecord).get(record_id)
            session.commit()
    """
    session = create_task_session(database_uri)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_all_school_databases():
    """
    Vraća listu svih school database URI-ja.

    NAPOMENA: Ova funkcija pretpostavlja da možemo dobiti listu svih škola
    iz master baze ili environment varijabli.

    Za sada vraća hardcoded listu, ali može se proširiti da čita iz:
    - Environment varijable (SCHOOL_IDS=0001,0011,0022,...)
    - Master baze podataka
    - Config fajla

    Returns:
        list: Lista database URI stringova
    """
    import os

    # TODO: Implementirati dinamičko učitavanje iz env ili master baze
    # Za sada koristimo environment varijablu SCHOOL_IDS
    school_ids_str = os.getenv('SCHOOL_IDS', '')

    if not school_ids_str:
        # Fallback: vrati samo trenutni URI
        return [os.getenv('SQLALCHEMY_DATABASE_URI')]

    school_ids = school_ids_str.split(',')

    # Generiši URI za svaku školu
    base_uri = "mysql+pymysql://uplatnic_mihas:tamonekasifra@localhost:3307/uplatnic_uplatnice_app_{}"

    return [base_uri.format(school_id.strip()) for school_id in school_ids]
