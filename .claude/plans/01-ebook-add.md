# Plan: EBook Add (01-ebook-add)

## Context

The ISKCON Book Store currently sells only physical books. This feature adds an optional
digital edition (PDF/EPUB) to any book. Admins upload the file when adding/editing a book.
After a customer places a UPI or Razorpay (paid) order, the payment success page shows a
"Download eBook" button for any ebook items. COD orders do not get download access.

Spec: `.claude/specs/01-ebook-add.md`
Branch: `feature/ebook-add`

---

## Files to Modify

| File | What changes |
|------|-------------|
| `app.py` | Config, Book model, new helper, new route, extend add/edit book routes, add import |
| `templates/admin/book_form.html` | Add Digital Edition upload section (right column) |
| `templates/payment_success.html` | Add download button per ebook item in order loop |
| `templates/admin/order_detail.html` | Add download link column in order items table |

---

## Step-by-Step Implementation

### Step 1 — Config (`app.py` lines 33–49)

Add two new config entries inside the `Config` class after `ALLOWED_EXTENSIONS`:

```python
EBOOK_FOLDER = os.path.join(BASE_DIR, "ebooks")          # outside static/ for security
ALLOWED_EBOOK_EXTENSIONS = {"pdf", "epub"}
```

Also add `os.makedirs(app.config["EBOOK_FOLDER"], exist_ok=True)` after line 61
(where `UPLOAD_FOLDER` is already created).

---

### Step 2 — Flask import (`app.py` line 15)

Add `send_from_directory` to the existing Flask import:

```python
from flask import (
    Flask, render_template, request, session, redirect,
    url_for, flash, jsonify, abort, send_from_directory
)
```

---

### Step 3 — Book model (`app.py` after line 99)

Add two columns to the `Book` model after `active`:

```python
is_ebook   = db.Column(db.Boolean, default=False)
ebook_file = db.Column(db.String(200), nullable=True)
```

The DB auto-migrates on startup via `db.create_all()` — new nullable columns are added
without data loss on SQLite. PostgreSQL will also handle nullable columns cleanly.

---

### Step 4 — New helper (`app.py` after `save_image` at line 209)

Add a parallel helper for ebook files:

```python
def allowed_ebook_file(filename):
    return "." in filename and \
           filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_EBOOK_EXTENSIONS"]

def save_ebook(file):
    """Save uploaded ebook file and return filename."""
    if file and allowed_ebook_file(file.filename):
        ext = file.filename.rsplit(".", 1)[1].lower()
        filename = f"{uuid.uuid4().hex}.{ext}"
        file.save(os.path.join(app.config["EBOOK_FOLDER"], filename))
        return filename
    return None
```

---

### Step 5 — Download route (`app.py` — add after `order_success` route ~line 601)

```python
@app.route("/ebook/download/<order_number>/<int:book_id>")
def ebook_download(order_number, book_id):
    order = Order.query.filter_by(order_number=order_number).first_or_404()

    # Access control: UPI orders allowed (trust-based), Razorpay must be paid, COD denied
    if order.payment_method == "cod":
        abort(403)
    if order.payment_method == "razorpay" and order.payment_status != "paid":
        abort(403)

    # Verify this book_id is actually in the order
    item = next((i for i in order.items if i.book_id == book_id), None)
    if not item:
        abort(404)

    book = Book.query.get_or_404(book_id)
    if not book.is_ebook or not book.ebook_file:
        abort(404)

    ebook_path = os.path.join(app.config["EBOOK_FOLDER"], book.ebook_file)
    if not os.path.exists(ebook_path):
        flash("eBook file not found. Please contact support.", "warning")
        return redirect(url_for("order_success", order_number=order_number))

    return send_from_directory(
        app.config["EBOOK_FOLDER"],
        book.ebook_file,
        as_attachment=True,
        download_name=f"{book.title}.{book.ebook_file.rsplit('.', 1)[1]}"
    )
```

---

### Step 6 — `admin_add_book` (`app.py` lines 685–715)

After `image_name = save_image(image_file) or "default_book.jpg"`, add:

```python
ebook_file_obj = request.files.get("ebook_file")
ebook_filename = save_ebook(ebook_file_obj)
is_ebook = bool(request.form.get("is_ebook"))
```

Add to `Book(...)` constructor:

```python
is_ebook   = is_ebook,
ebook_file = ebook_filename,
```

---

### Step 7 — `admin_edit_book` (`app.py` lines 718–752)

After the existing image update block, add:

```python
is_ebook = bool(request.form.get("is_ebook"))
book.is_ebook = is_ebook

ebook_file_obj = request.files.get("ebook_file")
if ebook_file_obj and ebook_file_obj.filename:
    # Delete old ebook file if exists
    if book.ebook_file:
        old_path = os.path.join(app.config["EBOOK_FOLDER"], book.ebook_file)
        if os.path.exists(old_path):
            os.remove(old_path)
    book.ebook_file = save_ebook(ebook_file_obj)

# If is_ebook unchecked and no file, clear ebook_file
if not is_ebook:
    book.ebook_file = None
```

---

### Step 8 — `templates/admin/book_form.html`

Insert new "Digital Edition" section in the right column, **after the active checkbox block
(after line 120, before `</div>` at line 121)**:

```html
<div class="mb-3">
    <div class="card border-primary">
        <div class="card-header bg-primary text-white py-2">
            <small class="fw-bold">📥 Digital Edition (eBook)</small>
        </div>
        <div class="card-body p-3">
            <div class="form-check mb-2">
                <input type="checkbox" name="is_ebook" class="form-check-input"
                       id="isEbookCheck" value="1"
                       {% if book and book.is_ebook %}checked{% endif %}
                       onchange="document.getElementById('ebookUploadSection').style.display=this.checked?'block':'none'">
                <label class="form-check-label" for="isEbookCheck">
                    Has downloadable eBook
                </label>
            </div>
            <div id="ebookUploadSection"
                 style="display:{% if book and book.is_ebook %}block{% else %}none{% endif %}">
                {% if book and book.ebook_file %}
                <p class="text-success small mb-1">
                    ✅ File uploaded: <code>{{ book.ebook_file[-12:] }}</code>
                </p>
                {% endif %}
                <input type="file" name="ebook_file" class="form-control form-control-sm"
                       accept=".pdf,.epub">
                <small class="text-muted">PDF or EPUB (max 16MB)</small>
            </div>
        </div>
    </div>
</div>
```

---

### Step 9 — `templates/payment_success.html`

In the items loop (lines 44–51), modify each row to show a download button for ebook items:

```html
{% for item in order.items %}
<div class="d-flex justify-content-between py-1 align-items-center">
  <span style="font-size:0.87rem;">{{ item.book_title }} × {{ item.quantity }}</span>
  <div class="d-flex align-items-center gap-2">
    <span style="font-size:0.87rem; font-weight:700; color:var(--saffron);">
      ₹{{ (item.price * item.quantity)|int }}
    </span>
    {% if item.book and item.book.is_ebook and item.book.ebook_file
          and order.payment_method != 'cod' %}
    <a href="{{ url_for('ebook_download', order_number=order.order_number, book_id=item.book_id) }}"
       class="btn btn-sm btn-outline-success py-0 px-2" style="font-size:0.75rem;">
      📥 Download
    </a>
    {% endif %}
  </div>
</div>
{% endfor %}
```

---

### Step 10 — `templates/admin/order_detail.html`

In the order items table (lines 141–148), add a 5th column header and cell:

**Table header** (after `<th>Subtotal</th>` at line 137):
```html
<th>eBook</th>
```

**Table row** (after subtotal `<td>` at line 146):
```html
<td>
  {% if item.book and item.book.is_ebook and item.book.ebook_file %}
  <a href="{{ url_for('ebook_download', order_number=order.order_number, book_id=item.book_id) }}"
     class="btn btn-sm btn-outline-primary" target="_blank">📥</a>
  {% else %}—{% endif %}
</td>
```

---

## Verification Checklist

1. **Server starts without error** — `python app.py` → no model/import errors
2. **Admin: Add book with eBook** — `/admin/books/add` → check "Has downloadable eBook" → upload PDF → submit → verify file exists in `ebooks/` folder
3. **Admin: Edit book** — replace ebook file → old file deleted, new file saved
4. **Admin: Uncheck is_ebook** → `ebook_file` cleared in DB
5. **Customer: Place UPI order with ebook book** → success page shows 📥 Download button → clicking it downloads the PDF
6. **Customer: Place COD order** → no Download button shown → `/ebook/download/...` returns 403
7. **Edge case: book.is_ebook=True but ebook_file=None** → no Download button shown (template guard)
8. **Edge case: file deleted from disk** → flash warning shown, redirect back to success page
9. **Non-ebook books** → unaffected; `—` shown in admin order detail table

---

## Notes

- `ebooks/` folder is at project root (not inside `static/`), so files are NOT directly
  accessible via browser URL — only served through the authenticated download route.
- Add `ebooks/` to `.gitignore` after implementation.
- After plan mode exits, this file will also be copied to `.claude/plans/01-ebook-add.md`
  in the project folder as requested.
