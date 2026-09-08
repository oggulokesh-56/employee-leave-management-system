from sqlalchemy import Column, Integer, String, Date, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password = Column(String(100), nullable=False)
    job_title = Column(String(100), nullable=True)
    phone = Column(String(50), nullable=True)
    start_date = Column(Date, nullable=True)
    role = Column(String(20), default="Employee")
    status = Column(String(20), default="Active")

    leaves = relationship("Leave", back_populates="user", cascade="all, delete-orphan")


class Leave(Base):
    __tablename__ = "leaves"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    leave_type = Column(String(50), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    days_count = Column(Integer, nullable=False)
    reason = Column(String(1000), nullable=True)
    status = Column(String(20), default="Pending")

    user = relationship("User", back_populates="leaves")