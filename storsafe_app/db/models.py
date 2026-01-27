"""
SQLAlchemy Models for Storsafe Dashboard.

These models mirror the existing SQLite schema but work with both SQLite and PostgreSQL.
"""

from datetime import datetime
from typing import Optional, List

from . import db


class Property(db.Model):
    """Properties (e.g., Madison, Chicago)."""
    __tablename__ = "properties"
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    periods = db.relationship("ReconciliationPeriod", back_populates="property", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Property {self.name}>"
    
    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ReconciliationPeriod(db.Model):
    """Reconciliation periods (e.g., Madison - Dec 2025)."""
    __tablename__ = "reconciliation_periods"
    __table_args__ = (
        db.UniqueConstraint("property_id", "year", "month", name="uq_property_year_month"),
    )
    
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey("properties.id"), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(50), default="in_progress")  # in_progress, completed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    property = db.relationship("Property", back_populates="periods")
    bank_transactions = db.relationship("BankTransaction", back_populates="period", cascade="all, delete-orphan")
    yardi_transactions = db.relationship("YardiTransaction", back_populates="period", cascade="all, delete-orphan")
    matches = db.relationship("Match", back_populates="period", cascade="all, delete-orphan")
    adjustments = db.relationship("AdjustmentEntry", back_populates="period", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<ReconciliationPeriod {self.property.name if self.property else 'Unknown'} {self.year}-{self.month:02d}>"
    
    def to_dict(self):
        return {
            "id": self.id,
            "property_id": self.property_id,
            "property_name": self.property.name if self.property else None,
            "year": self.year,
            "month": self.month,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class BankTransaction(db.Model):
    """Bank transactions (from PDF bank statements)."""
    __tablename__ = "bank_transactions"
    
    id = db.Column(db.Integer, primary_key=True)
    period_id = db.Column(db.Integer, db.ForeignKey("reconciliation_periods.id", ondelete="CASCADE"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    transaction_id = db.Column(db.String(100), nullable=True)  # Check number, reference ID, etc.
    description = db.Column(db.Text, nullable=True)
    amount = db.Column(db.Float, nullable=False)  # Positive = deposit, Negative = withdrawal
    transaction_type = db.Column(db.String(50), nullable=True)  # CHECK, ACH, DEPOSIT, FEE, TRANSFER, OTHER
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    period = db.relationship("ReconciliationPeriod", back_populates="bank_transactions")
    match_links = db.relationship("MatchBankTransaction", back_populates="bank_transaction", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<BankTransaction {self.date} ${self.amount:.2f}>"
    
    def to_dict(self):
        return {
            "id": self.id,
            "period_id": self.period_id,
            "date": self.date.isoformat() if self.date else None,
            "transaction_id": self.transaction_id,
            "description": self.description,
            "amount": self.amount,
            "transaction_type": self.transaction_type,
        }


class YardiTransaction(db.Model):
    """Yardi transactions (from Excel bank rec reports)."""
    __tablename__ = "yardi_transactions"
    
    id = db.Column(db.Integer, primary_key=True)
    period_id = db.Column(db.Integer, db.ForeignKey("reconciliation_periods.id", ondelete="CASCADE"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    transaction_id = db.Column(db.String(100), nullable=True)  # Check number (blank for Other Items)
    description = db.Column(db.Text, nullable=True)
    amount = db.Column(db.Float, nullable=False)  # Negative for checks (outflow)
    source_type = db.Column(db.String(50), nullable=True)  # 'check' or 'other'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    period = db.relationship("ReconciliationPeriod", back_populates="yardi_transactions")
    match_links = db.relationship("MatchYardiTransaction", back_populates="yardi_transaction", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<YardiTransaction {self.date} ${self.amount:.2f}>"
    
    def to_dict(self):
        return {
            "id": self.id,
            "period_id": self.period_id,
            "date": self.date.isoformat() if self.date else None,
            "transaction_id": self.transaction_id,
            "description": self.description,
            "amount": self.amount,
            "source_type": self.source_type,
        }


class Match(db.Model):
    """Matches (auto-matched or manually matched transaction groups)."""
    __tablename__ = "matches"
    
    id = db.Column(db.Integer, primary_key=True)
    period_id = db.Column(db.Integer, db.ForeignKey("reconciliation_periods.id", ondelete="CASCADE"), nullable=False)
    match_pass = db.Column(db.String(50), nullable=True)  # 'PASS 1', 'PASS 2', ... 'PASS 7', 'MANUAL'
    match_type = db.Column(db.String(50), nullable=False)  # 'bank_yardi', 'bank_bank', 'yardi_yardi', 'suggestion'
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    period = db.relationship("ReconciliationPeriod", back_populates="matches")
    bank_links = db.relationship("MatchBankTransaction", back_populates="match", cascade="all, delete-orphan")
    yardi_links = db.relationship("MatchYardiTransaction", back_populates="match", cascade="all, delete-orphan")
    adjustment = db.relationship("AdjustmentEntry", back_populates="source_match", uselist=False)
    
    def __repr__(self):
        return f"<Match {self.id} {self.match_pass} {self.match_type}>"
    
    def to_dict(self):
        return {
            "id": self.id,
            "period_id": self.period_id,
            "match_pass": self.match_pass,
            "match_type": self.match_type,
            "notes": self.notes,
        }


class MatchBankTransaction(db.Model):
    """Many-to-many link: matches to bank transactions."""
    __tablename__ = "match_bank_transactions"
    
    match_id = db.Column(db.Integer, db.ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True)
    bank_transaction_id = db.Column(db.Integer, db.ForeignKey("bank_transactions.id", ondelete="CASCADE"), primary_key=True)
    
    # Relationships
    match = db.relationship("Match", back_populates="bank_links")
    bank_transaction = db.relationship("BankTransaction", back_populates="match_links")


class MatchYardiTransaction(db.Model):
    """Many-to-many link: matches to yardi transactions."""
    __tablename__ = "match_yardi_transactions"
    
    match_id = db.Column(db.Integer, db.ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True)
    yardi_transaction_id = db.Column(db.Integer, db.ForeignKey("yardi_transactions.id", ondelete="CASCADE"), primary_key=True)
    
    # Relationships
    match = db.relationship("Match", back_populates="yardi_links")
    yardi_transaction = db.relationship("YardiTransaction", back_populates="match_links")


class AdjustmentEntry(db.Model):
    """Adjustment entries (reconciling items to be recorded in Yardi)."""
    __tablename__ = "adjustment_entries"
    
    id = db.Column(db.Integer, primary_key=True)
    period_id = db.Column(db.Integer, db.ForeignKey("reconciliation_periods.id", ondelete="CASCADE"), nullable=False)
    source_type = db.Column(db.String(50), nullable=False)  # 'bank' or 'differential'
    source_bank_txn_id = db.Column(db.Integer, db.ForeignKey("bank_transactions.id", ondelete="SET NULL"), nullable=True)
    source_match_id = db.Column(db.Integer, db.ForeignKey("matches.id", ondelete="SET NULL"), nullable=True)
    date = db.Column(db.Date, nullable=False)
    description = db.Column(db.Text, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=True)  # 'nsf_fee', 'bank_charge', 'interest', 'other', etc.
    suggested = db.Column(db.Boolean, default=False)
    confirmed = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    period = db.relationship("ReconciliationPeriod", back_populates="adjustments")
    source_bank_txn = db.relationship("BankTransaction")
    source_match = db.relationship("Match", back_populates="adjustment")
    
    def __repr__(self):
        return f"<AdjustmentEntry {self.category} ${self.amount:.2f}>"
    
    def to_dict(self):
        return {
            "id": self.id,
            "period_id": self.period_id,
            "source_type": self.source_type,
            "date": self.date.isoformat() if self.date else None,
            "description": self.description,
            "amount": self.amount,
            "category": self.category,
            "suggested": self.suggested,
            "confirmed": self.confirmed,
            "notes": self.notes,
        }


class AdjustmentPattern(db.Model):
    """Adjustment patterns (learned from previous months for smart suggestions)."""
    __tablename__ = "adjustment_patterns"
    __table_args__ = (
        db.UniqueConstraint("property_id", "pattern_type", "pattern_value", name="uq_pattern"),
    )
    
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey("properties.id", ondelete="CASCADE"), nullable=True)
    pattern_type = db.Column(db.String(50), nullable=False)  # 'keyword', 'amount_range', 'transaction_type'
    pattern_value = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    confidence = db.Column(db.Float, default=1.0)  # 0.0 to 1.0
    times_used = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    property = db.relationship("Property")
    
    def __repr__(self):
        return f"<AdjustmentPattern {self.pattern_type}={self.pattern_value} -> {self.category}>"
