"""
Database Service for Storsafe Dashboard.

Provides high-level database operations and initialization.
"""

import logging
from typing import Optional, List
from flask import current_app

from . import db
from .models import (
    Property,
    ReconciliationPeriod,
    BankTransaction,
    YardiTransaction,
    Match,
    AdjustmentEntry,
    AdjustmentPattern,
)

logger = logging.getLogger(__name__)


class DatabaseService:
    """High-level database operations."""
    
    def __init__(self, app=None):
        self.app = app
        self._seeded = False
    
    def init_app(self, app):
        """Initialize with Flask app."""
        self.app = app
        
        # Seed patterns on first init within app context
        if not self._seeded:
            try:
                self._seed_adjustment_patterns()
                self._seeded = True
            except Exception:
                pass  # May fail if tables not created yet
    
    def init_db(self) -> dict:
        """Initialize database tables and seed data.
        
        Returns:
            dict with status and tables created
        """
        try:
            db.create_all()
            
            # Seed common adjustment patterns if they don't exist
            self._seed_adjustment_patterns()
            
            return {
                "status": "success",
                "message": "Database initialized successfully",
                "tables": [table.name for table in db.metadata.sorted_tables],
            }
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            return {
                "status": "error",
                "message": str(e),
            }
    
    def _seed_adjustment_patterns(self):
        """Seed common adjustment patterns."""
        patterns = [
            (None, "keyword", "nsf", "nsf_fee", 1.0),
            (None, "keyword", "nsf fee", "nsf_fee", 1.0),
            (None, "keyword", "returned item", "nsf_fee", 0.9),
            (None, "keyword", "overdraft", "overdraft_fee", 1.0),
            (None, "keyword", "od fee", "overdraft_fee", 0.9),
            (None, "keyword", "service charge", "bank_charge", 0.9),
            (None, "keyword", "monthly fee", "bank_charge", 0.9),
            (None, "keyword", "maintenance fee", "bank_charge", 0.9),
            (None, "keyword", "analysis charge", "bank_charge", 0.8),
            (None, "keyword", "wire fee", "bank_charge", 0.9),
            (None, "keyword", "interest", "interest_income", 0.8),
            (None, "keyword", "interest earned", "interest_income", 0.9),
            (None, "keyword", "interest paid", "interest_income", 0.9),
        ]
        
        for property_id, pattern_type, pattern_value, category, confidence in patterns:
            existing = AdjustmentPattern.query.filter_by(
                property_id=property_id,
                pattern_type=pattern_type,
                pattern_value=pattern_value,
            ).first()
            
            if not existing:
                pattern = AdjustmentPattern(
                    property_id=property_id,
                    pattern_type=pattern_type,
                    pattern_value=pattern_value,
                    category=category,
                    confidence=confidence,
                )
                db.session.add(pattern)
        
        db.session.commit()
        logger.info("Seeded adjustment patterns")
    
    def get_status(self) -> dict:
        """Get database status and record counts.
        
        Returns:
            dict with connection status and table counts
        """
        try:
            # Test connection
            db.session.execute(db.text("SELECT 1"))
            
            # Get counts
            counts = {
                "properties": Property.query.count(),
                "reconciliation_periods": ReconciliationPeriod.query.count(),
                "bank_transactions": BankTransaction.query.count(),
                "yardi_transactions": YardiTransaction.query.count(),
                "matches": Match.query.count(),
                "adjustment_entries": AdjustmentEntry.query.count(),
                "adjustment_patterns": AdjustmentPattern.query.count(),
            }
            
            return {
                "status": "connected",
                "database_url": self._masked_url(),
                "counts": counts,
            }
        except Exception as e:
            logger.error(f"Database status check failed: {e}")
            return {
                "status": "error",
                "message": str(e),
            }
    
    def _masked_url(self) -> str:
        """Get masked database URL for display."""
        url = current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
        if "://" in url:
            # Mask password if present
            parts = url.split("://")
            if "@" in parts[1]:
                creds, rest = parts[1].split("@", 1)
                if ":" in creds:
                    user, _ = creds.split(":", 1)
                    return f"{parts[0]}://{user}:****@{rest}"
        return url[:50] + "..." if len(url) > 50 else url
    
    # Property operations
    def get_or_create_property(self, name: str) -> Property:
        """Get or create a property by name."""
        prop = Property.query.filter_by(name=name).first()
        if not prop:
            prop = Property(name=name)
            db.session.add(prop)
            db.session.commit()
        return prop
    
    def get_all_properties(self) -> List[Property]:
        """Get all properties."""
        return Property.query.order_by(Property.name).all()
    
    # Period operations
    def get_or_create_period(self, property_name: str, year: int, month: int) -> ReconciliationPeriod:
        """Get or create a reconciliation period."""
        prop = self.get_or_create_property(property_name)
        
        period = ReconciliationPeriod.query.filter_by(
            property_id=prop.id,
            year=year,
            month=month,
        ).first()
        
        if not period:
            period = ReconciliationPeriod(
                property_id=prop.id,
                year=year,
                month=month,
            )
            db.session.add(period)
            db.session.commit()
        
        return period
    
    def get_all_periods(self) -> List[ReconciliationPeriod]:
        """Get all periods with stats."""
        return ReconciliationPeriod.query.join(Property).order_by(
            ReconciliationPeriod.year.desc(),
            ReconciliationPeriod.month.desc(),
            Property.name,
        ).all()
    
    def get_period_by_id(self, period_id: int) -> Optional[ReconciliationPeriod]:
        """Get a period by ID."""
        return ReconciliationPeriod.query.get(period_id)


# Singleton instance
_db_service: Optional[DatabaseService] = None


def get_db_service() -> DatabaseService:
    """Get the database service singleton."""
    global _db_service
    if _db_service is None:
        _db_service = DatabaseService()
    return _db_service
