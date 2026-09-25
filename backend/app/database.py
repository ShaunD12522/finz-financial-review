from sqlalchemy import create_engine, Column, Integer, String, Float, Date, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = "sqlite:///./finz.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True)

    transaction_id = Column(String, unique=True, nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    description = Column(String, nullable=False)
    counterparty = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    method = Column(String, nullable=False)

    category = Column(String, nullable=True)
    category_confidence = Column(Float, nullable=True)
    is_pnl = Column(Boolean, nullable=True)
    needs_review = Column(Boolean, default=False, nullable=False)
    review_reason = Column(String, nullable=True)  # human-readable explanation of why this needs review

    corrected_category = Column(String, nullable=True)
    reviewed = Column(Boolean, default=False, nullable=False)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
