from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

def extract_to_draft(system: str, logical_date: str) -> None:
    logger.info('Extracting %s data for %s into %s_Draft', system, logical_date, system)

def build_tracking(source: str, logical_date: str) -> None:
    logger.info('Building %s_Data_Tracking for %s', source, logical_date)

def backup_tracking(logical_date: str) -> None:
    logger.info('Backing up tracking rows for %s', logical_date)

def upsert_sale_orders(logical_date: str) -> None:
    logger.info('Upserting PGI_SaleOrders for %s', logical_date)
