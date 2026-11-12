import re
from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models.admin import Admin
from models.ots_note import OtsNote, OtsMenu
from schemas.ots_note import (
    OtsNoteCreate,
    OtsNoteBulkCreate,
    OtsNoteUpdate,
    OtsNoteResponse,
    OtsMenuCreate,
    OtsMenuUpdate,
    OtsMenuResponse,
)
from auth.dependencies import require_admin
from utils.audit import create_audit_log

router = APIRouter(
    prefix="/api/ots-notes",
    tags=["OTS Notes"]
)

INDONESIAN_DAYS = {
    0: "Senin",
    1: "Selasa",
    2: "Rabu",
    3: "Kamis",
    4: "Jumat",
    5: "Sabtu",
    6: "Minggu",
}

PRICE_LINE_REGEX = re.compile(
    r"(?:-|–|—)\s*(?:rp\.?\s*)?(\d+(?:[.,]\d{3})*)(?:\s*(rb|ribu|k))?\s*$",
    re.IGNORECASE,
)


def _default_day_label(note_date: date) -> str:
    return INDONESIAN_DAYS.get(note_date.weekday(), "")


def _parse_items_total(items_text: str) -> Optional[int]:
    total = 0
    found = False
    for raw_line in items_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        m = PRICE_LINE_REGEX.search(line)
        if m:
            num_str = m.group(1).replace(".", "").replace(",", "")
            try:
                val = int(num_str)
            except ValueError:
                continue
            unit = (m.group(2) or "").lower()
            if unit in ("rb", "ribu", "k"):
                val *= 1000
            total += val
            found = True
    return total if found and total > 0 else None


@router.get("", response_model=List[OtsNoteResponse])
def list_ots_notes(
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(require_admin),
):
    query = db.query(OtsNote)
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            (OtsNote.customer_name.ilike(term))
            | (OtsNote.items_text.ilike(term))
            | (OtsNote.day_label.ilike(term))
        )

    return (
        query.order_by(OtsNote.note_date.desc(), OtsNote.id.asc()).all()
    )


@router.post("", response_model=OtsNoteResponse)
def create_ots_note(
    data: OtsNoteCreate,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(require_admin),
):
    day_label = (data.day_label or "").strip() or _default_day_label(data.note_date)
    cleaned_items = data.items_text.strip()
    computed_amount = data.amount if data.amount is not None else _parse_items_total(cleaned_items)

    note = OtsNote(
        note_date=data.note_date,
        day_label=day_label,
        customer_name=data.customer_name.strip(),
        items_text=cleaned_items,
        amount=computed_amount,
        is_paid=data.is_paid,
        is_done=data.is_done,
        created_by=current_admin.name or current_admin.username,
    )
    db.add(note)
    db.flush()

    create_audit_log(
        db=db,
        user_type="admin",
        user_id=current_admin.id,
        action="OTS_NOTE_CREATED",
        entity_type="OtsNote",
        entity_id=note.id,
        description=f"Catatan OTS '{note.customer_name}: {note.items_text}' ({note.note_date}) ditambahkan oleh {current_admin.name}",
    )

    db.commit()
    db.refresh(note)
    return note


@router.post("/bulk", response_model=List[OtsNoteResponse])
def create_ots_notes_bulk(
    data: OtsNoteBulkCreate,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(require_admin),
):
    lines = [ln.strip() for ln in data.raw_text.splitlines() if ln.strip()]
    day_names_lower = {d.lower() for d in INDONESIAN_DAYS.values()}
    day_label = (data.day_label or "").strip() or _default_day_label(data.note_date)

    parsed_entries = []
    current_customer = None
    current_items: List[str] = []

    def _flush_current():
        nonlocal current_customer, current_items
        if current_customer and current_items:
            parsed_entries.append((current_customer, "\n".join(current_items)))
        current_customer = None
        current_items = []

    for line in lines:
        # Skip single day-name header lines like "Senin" or "Selasa" if pasted
        if line.lower().rstrip(":") in day_names_lower:
            _flush_current()
            continue

        if ":" in line:
            _flush_current()
            name_part, items_part = line.split(":", 1)
            cleaned_name = name_part.strip(" -•*")
            if cleaned_name:
                current_customer = cleaned_name
                if items_part.strip():
                    current_items.append(items_part.strip())
        elif current_customer is not None:
            current_items.append(line)
        elif " - " in line:
            name_part, items_part = line.split(" - ", 1)
            cleaned_name = name_part.strip(" -•*")
            if cleaned_name and items_part.strip():
                parsed_entries.append((cleaned_name, items_part.strip()))
        else:
            parsed_entries.append(("Pelanggan OTS", line))

    _flush_current()

    created_notes: List[OtsNote] = []
    for customer_name, items_text in parsed_entries:
        if not customer_name or not items_text:
            continue

        note = OtsNote(
            note_date=data.note_date,
            day_label=day_label,
            customer_name=customer_name[:150],
            items_text=items_text,
            amount=_parse_items_total(items_text),
            is_paid=False,
            is_done=False,
            created_by=current_admin.name or current_admin.username,
        )
        db.add(note)
        created_notes.append(note)

    if not created_notes:
        raise HTTPException(
            status_code=400,
            detail="Format catatan kosong atau tidak valid. Gunakan format 'Nama : Pesanan' per baris.",
        )

    db.flush()

    create_audit_log(
        db=db,
        user_type="admin",
        user_id=current_admin.id,
        action="OTS_NOTE_BULK_CREATED",
        entity_type="OtsNote",
        entity_id=created_notes[0].id,
        description=f"{len(created_notes)} catatan OTS untuk tanggal {data.note_date} ditambahkan secara massal oleh {current_admin.name}",
    )

    db.commit()
    for note in created_notes:
        db.refresh(note)

    return created_notes


# ── Master Menu OTS (Preset Menu Khusus OTS) ─────────────────────────────────
@router.get("/menus", response_model=List[OtsMenuResponse])
def list_ots_menus(
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(require_admin),
):
    return db.query(OtsMenu).order_by(OtsMenu.name.asc(), OtsMenu.id.asc()).all()


@router.post("/menus", response_model=OtsMenuResponse)
def create_ots_menu(
    data: OtsMenuCreate,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(require_admin),
):
    cleaned_name = data.name.strip()
    if not cleaned_name:
        raise HTTPException(status_code=400, detail="Nama menu OTS wajib diisi")

    existing = (
        db.query(OtsMenu)
        .filter(OtsMenu.name.ilike(cleaned_name))
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail=f"Menu OTS '{cleaned_name}' sudah ada")

    menu = OtsMenu(
        name=cleaned_name,
        price=max(0, int(data.price or 0)),
        is_active=data.is_active,
        created_by=current_admin.name or current_admin.username,
    )
    db.add(menu)
    db.flush()

    create_audit_log(
        db=db,
        user_type="admin",
        user_id=current_admin.id,
        action="OTS_MENU_CREATED",
        entity_type="OtsMenu",
        entity_id=menu.id,
        description=f"Menu OTS '{menu.name}' (Rp {menu.price}) ditambahkan oleh {current_admin.name}",
    )

    db.commit()
    db.refresh(menu)
    return menu


@router.put("/menus/{menu_id}", response_model=OtsMenuResponse)
def update_ots_menu(
    menu_id: int,
    data: OtsMenuUpdate,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(require_admin),
):
    menu = db.query(OtsMenu).filter(OtsMenu.id == menu_id).first()
    if not menu:
        raise HTTPException(status_code=404, detail="Menu OTS tidak ditemukan")

    update_data = data.model_dump(exclude_unset=True)
    if "name" in update_data and update_data["name"] is not None:
        cleaned_name = update_data["name"].strip()
        if not cleaned_name:
            raise HTTPException(status_code=400, detail="Nama menu OTS tidak boleh kosong")
        duplicate = (
            db.query(OtsMenu)
            .filter(OtsMenu.name.ilike(cleaned_name), OtsMenu.id != menu_id)
            .first()
        )
        if duplicate:
            raise HTTPException(status_code=400, detail=f"Menu OTS '{cleaned_name}' sudah ada")
        menu.name = cleaned_name

    if "price" in update_data and update_data["price"] is not None:
        menu.price = max(0, int(update_data["price"]))

    if "is_active" in update_data and update_data["is_active"] is not None:
        menu.is_active = update_data["is_active"]

    create_audit_log(
        db=db,
        user_type="admin",
        user_id=current_admin.id,
        action="OTS_MENU_UPDATED",
        entity_type="OtsMenu",
        entity_id=menu.id,
        description=f"Menu OTS '{menu.name}' (Rp {menu.price}) diperbarui oleh {current_admin.name}",
    )

    db.commit()
    db.refresh(menu)
    return menu


@router.delete("/menus/{menu_id}")
def delete_ots_menu(
    menu_id: int,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(require_admin),
):
    menu = db.query(OtsMenu).filter(OtsMenu.id == menu_id).first()
    if not menu:
        raise HTTPException(status_code=404, detail="Menu OTS tidak ditemukan")

    menu_name = menu.name
    db.delete(menu)

    create_audit_log(
        db=db,
        user_type="admin",
        user_id=current_admin.id,
        action="OTS_MENU_DELETED",
        entity_type="OtsMenu",
        entity_id=menu_id,
        description=f"Menu OTS '{menu_name}' dihapus oleh {current_admin.name}",
    )

    db.commit()
    return {"message": "Menu OTS berhasil dihapus"}


@router.put("/{note_id}", response_model=OtsNoteResponse)
def update_ots_note(
    note_id: int,
    data: OtsNoteUpdate,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(require_admin),
):
    note = db.query(OtsNote).filter(OtsNote.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Catatan OTS tidak ditemukan")

    update_data = data.model_dump(exclude_unset=True)

    if "note_date" in update_data and update_data["note_date"] is not None:
        note.note_date = update_data["note_date"]
        # Update default day label unless custom day_label was explicitly sent
        if "day_label" not in update_data or not (update_data.get("day_label") or "").strip():
            note.day_label = _default_day_label(note.note_date)

    if "day_label" in update_data:
        cleaned_label = (update_data["day_label"] or "").strip()
        note.day_label = cleaned_label or _default_day_label(note.note_date)

    if "customer_name" in update_data and update_data["customer_name"] is not None:
        note.customer_name = update_data["customer_name"].strip()

    if "items_text" in update_data and update_data["items_text"] is not None:
        note.items_text = update_data["items_text"].strip()

    if "amount" in update_data:
        note.amount = (
            update_data["amount"]
            if update_data["amount"] is not None
            else _parse_items_total(note.items_text)
        )
    elif "items_text" in update_data:
        note.amount = _parse_items_total(note.items_text)

    if "is_paid" in update_data and update_data["is_paid"] is not None:
        note.is_paid = update_data["is_paid"]

    if "is_done" in update_data and update_data["is_done"] is not None:
        note.is_done = update_data["is_done"]

    create_audit_log(
        db=db,
        user_type="admin",
        user_id=current_admin.id,
        action="OTS_NOTE_UPDATED",
        entity_type="OtsNote",
        entity_id=note.id,
        description=f"Catatan OTS '{note.customer_name}' diperbarui oleh {current_admin.name}",
    )

    db.commit()
    db.refresh(note)
    return note


@router.delete("/{note_id}")
def delete_ots_note(
    note_id: int,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(require_admin),
):
    note = db.query(OtsNote).filter(OtsNote.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Catatan OTS tidak ditemukan")

    label = f"{note.customer_name}: {note.items_text}"
    db.delete(note)

    create_audit_log(
        db=db,
        user_type="admin",
        user_id=current_admin.id,
        action="OTS_NOTE_DELETED",
        entity_type="OtsNote",
        entity_id=note_id,
        description=f"Catatan OTS '{label}' dihapus oleh {current_admin.name}",
    )

    db.commit()
    return {"message": "Catatan OTS berhasil dihapus"}
