from sqlalchemy.orm import Session

from models.audit_trail import AuditTrail


def create_audit_log(
    db: Session,
    user_type: str,
    user_id: int,
    action: str,
    entity_type: str,
    entity_id: int,
    description: str = None
):
    audit = AuditTrail(
        user_type=user_type,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        description=description
    )

    db.add(audit)