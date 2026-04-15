# Spec: EBook Add

## Overview

Allow physical books in the store to optionally have a digital (eBook) version.
Admins can upload a PDF/ebook file when adding or editing a book. After a customer
completes payment (UPI or Razorpay), they receive a secure, time-limited download
link for any eBook items in their order. COD orders do not get download access
(payment must be confirmed first).

This enables ISKCON to distribute digital copies alongside physical books, increasing
reach while protecting content from unauthorized sharing.

## Depends on

- Base book catalog (already implemented)
- Order + payment flow (already implemented)
- Admin authentication (`@admin_required` decorator, already implemented)

## Routes / APIs

| Method | Path | Description | Access |
|--------|------|-------------|--------|
| GET | `/ebook/download/<order_number>/<int:book_id>` | Serve the eBook file for a paid order item | Public (validated by order ownership token) |
| POST | `/admin/books/add` | Extended — now accepts optional eBook file upload | Admin |
| POST | `/admin/books/edit/<book_id>` | Extended — now accepts optional eBook file upload | Admin |

## Database changes

**`books` table — new columns:**

| Column | Type | Default | Notes |
|--------|------|---------|-------|
| `is_ebook` | `Boolean` | `False` | Flag: book has a downloadable digital edition |
| `ebook_file` | `String(200)` | `None` | Filename of the stored PDF/ebook file |

No new tables required.

## UI / Templates / Frontend

**Modify: `templates/admin/book_form.html`**
- Add "Digital Edition" section with:
  - Checkbox: "This book has a downloadable eBook"
  - File upload input (PDF, epub) — shown only when checkbox is checked
  - Display current ebook filename if already uploaded (edit mode)

**Modify: `templates/payment_success.html`**
- After successful payment (UPI / Razorpay — `payment_status == 'paid'` or UPI pending):
  - For each order item where `book.is_ebook == True`, show a **Download eBook** button
  - Link to `/ebook/download/<order_number>/<book_id>`
  - Show note: "Your download link is valid for this order page"

**Modify: `templates/admin/order_detail.html`**
- Show eBook download link next to any ebook order items (admin convenience)

## Files to change

| File | Change |
|------|--------|
| `app.py` | Add `is_ebook` + `ebook_file` columns to `Book` model; add `/ebook/download/` route; extend `admin_add_book` and `admin_edit_book` to handle ebook file upload |
| `templates/admin/book_form.html` | Add eBook file upload section |
| `templates/payment_success.html` | Show download button for ebook items |
| `templates/admin/order_detail.html` | Show ebook download link per item |

## Files to create

| File | Purpose |
|------|---------|
| `static/ebooks/` | Directory to store uploaded ebook files (gitignored) |

## New dependencies

No new Python packages required.
- File serving via Flask's `send_from_directory` (already in stdlib/Flask)

## Rules for implementation

- **eBook files stored outside `static/images/`** — use a dedicated `static/ebooks/` folder (or better, outside `static/` entirely using `send_file` to prevent direct URL access)
- **Access control on download route** — verify the order exists, belongs to the session or matches order number, and `payment_status` is `paid` (for Razorpay) or order exists (for UPI — manual payment, trust-based)
- **Allowed file types** — PDF and EPUB only (`pdf`, `epub`); validate server-side with `ALLOWED_EBOOK_EXTENSIONS`
- **Filename sanitization** — use `werkzeug.utils.secure_filename` + UUID prefix (same pattern as cover images)
- **Max file size** — respect existing `MAX_CONTENT_LENGTH = 16MB`; increase to 50MB in config if needed
- **No hardcoded paths** — use `app.config["EBOOK_FOLDER"]` set from env or Base dir
- **Graceful fallback** — if `ebook_file` is missing/deleted, return 404 with user-friendly message, not a 500
- **Admin-only upload** — only admins can upload/replace ebook files; customers only download
- Follow existing single-file architecture — all routes in `app.py`

## Definition of done

- [ ] `Book` model has `is_ebook` and `ebook_file` columns; DB migrates cleanly on startup
- [ ] Admin can upload a PDF when adding a new book
- [ ] Admin can upload/replace a PDF when editing an existing book
- [ ] eBook file is saved to `static/ebooks/` with UUID filename
- [ ] `payment_success.html` shows "Download eBook" button for ebook items in the order
- [ ] Download route serves the correct file; rejects requests for orders that don't exist
- [ ] Non-ebook books are unaffected — no UI changes on their pages
- [ ] No errors in server logs during upload or download
- [ ] Large PDF (up to 16 MB) uploads successfully
- [ ] Edge case: book marked `is_ebook` but file not yet uploaded — no broken link shown
