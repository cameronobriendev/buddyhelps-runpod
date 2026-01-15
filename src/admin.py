"""
Admin routes for managing phone numbers.
Simple HTML UI + JSON API.
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional
from src import database as db

router = APIRouter()

class PhoneNumberCreate(BaseModel):
    phone_number: str
    business_name: str
    business_type: str = "plumber"
    greeting_name: str = "Benny"
    system_prompt: Optional[str] = None
    is_active: bool = True

class PhoneNumberUpdate(BaseModel):
    business_name: Optional[str] = None
    business_type: Optional[str] = None
    greeting_name: Optional[str] = None
    system_prompt: Optional[str] = None
    is_active: Optional[bool] = None

# API Routes
@router.get("/api/numbers")
async def list_numbers():
    """List all phone numbers."""
    return db.get_all_numbers()

@router.get("/api/numbers/{phone}")
async def get_number(phone: str):
    """Get a specific phone number."""
    result = db.get_number(phone)
    if not result:
        raise HTTPException(status_code=404, detail="Number not found")
    return result

@router.post("/api/numbers")
async def create_number(data: PhoneNumberCreate):
    """Create a new phone number."""
    existing = db.get_number(data.phone_number)
    if existing:
        raise HTTPException(status_code=400, detail="Number already exists")
    return db.add_number(**data.dict())

@router.put("/api/numbers/{phone}")
async def update_number(phone: str, data: PhoneNumberUpdate):
    """Update a phone number."""
    existing = db.get_number(phone)
    if not existing:
        raise HTTPException(status_code=404, detail="Number not found")
    updates = {k: v for k, v in data.dict().items() if v is not None}
    return db.update_number(phone, **updates)

@router.delete("/api/numbers/{phone}")
async def delete_number(phone: str):
    """Delete a phone number."""
    if db.delete_number(phone):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Number not found")

# HTML Admin UI
ADMIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>BuddyHelps Admin</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
        h1 { color: #333; margin-bottom: 20px; }
        .container { max-width: 1000px; margin: 0 auto; }
        .card { background: white; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        table { width: 100%; border-collapse: collapse; }
        th, td { text-align: left; padding: 12px; border-bottom: 1px solid #eee; }
        th { background: #f8f8f8; font-weight: 600; }
        tr:hover { background: #f8f8f8; }
        .badge { display: inline-block; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: 500; }
        .badge-active { background: #d4edda; color: #155724; }
        .badge-inactive { background: #f8d7da; color: #721c24; }
        .badge-type { background: #e2e3e5; color: #383d41; }
        button { padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; }
        .btn-primary { background: #007bff; color: white; }
        .btn-danger { background: #dc3545; color: white; }
        .btn-success { background: #28a745; color: white; }
        button:hover { opacity: 0.9; }
        input, select, textarea { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 4px; margin-bottom: 10px; font-size: 14px; }
        label { display: block; margin-bottom: 4px; font-weight: 500; color: #555; }
        .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }
        .actions { display: flex; gap: 8px; }
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 100; }
        .modal-content { background: white; max-width: 500px; margin: 50px auto; padding: 20px; border-radius: 8px; }
        .modal.active { display: block; }
        .close { float: right; font-size: 24px; cursor: pointer; }
        .empty { text-align: center; padding: 40px; color: #666; }
    </style>
</head>
<body>
    <div class="container">
        <h1>BuddyHelps Phone Numbers</h1>

        <div class="card">
            <button class="btn-primary" onclick="showAddModal()">+ Add Number</button>
        </div>

        <div class="card">
            <table>
                <thead>
                    <tr>
                        <th>Phone Number</th>
                        <th>Business</th>
                        <th>Type</th>
                        <th>Greeting</th>
                        <th>Status</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody id="numbers-table">
                    <tr><td colspan="6" class="empty">Loading...</td></tr>
                </tbody>
            </table>
        </div>
    </div>

    <!-- Add/Edit Modal -->
    <div id="modal" class="modal">
        <div class="modal-content">
            <span class="close" onclick="closeModal()">&times;</span>
            <h2 id="modal-title">Add Number</h2>
            <form id="number-form" onsubmit="saveNumber(event)">
                <input type="hidden" id="edit-phone">

                <label>Phone Number</label>
                <input type="text" id="phone_number" placeholder="+15874059371" required>

                <div class="form-row">
                    <div>
                        <label>Business Name</label>
                        <input type="text" id="business_name" placeholder="ABC Plumbing" required>
                    </div>
                    <div>
                        <label>Business Type</label>
                        <select id="business_type">
                            <option value="plumber">Plumber</option>
                            <option value="hvac">HVAC</option>
                            <option value="electrician">Electrician</option>
                            <option value="demo">Demo</option>
                            <option value="other">Other</option>
                        </select>
                    </div>
                </div>

                <label>Greeting Name (AI introduces as)</label>
                <input type="text" id="greeting_name" placeholder="Benny" value="Benny">

                <label>Custom System Prompt (optional)</label>
                <textarea id="system_prompt" rows="3" placeholder="Override default prompt..."></textarea>

                <label>
                    <input type="checkbox" id="is_active" checked> Active
                </label>

                <br><br>
                <button type="submit" class="btn-success">Save</button>
            </form>
        </div>
    </div>

    <script>
        const API = '/api/numbers';

        async function loadNumbers() {
            const resp = await fetch(API);
            const numbers = await resp.json();
            const tbody = document.getElementById('numbers-table');

            if (numbers.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" class="empty">No phone numbers configured. Add one to get started.</td></tr>';
                return;
            }

            tbody.innerHTML = numbers.map(n => `
                <tr>
                    <td><strong>${n.phone_number}</strong></td>
                    <td>${n.business_name}</td>
                    <td><span class="badge badge-type">${n.business_type}</span></td>
                    <td>${n.greeting_name}</td>
                    <td><span class="badge ${n.is_active ? 'badge-active' : 'badge-inactive'}">${n.is_active ? 'Active' : 'Inactive'}</span></td>
                    <td class="actions">
                        <button onclick="editNumber('${n.phone_number}')" class="btn-primary">Edit</button>
                        <button onclick="deleteNumber('${n.phone_number}')" class="btn-danger">Delete</button>
                    </td>
                </tr>
            `).join('');
        }

        function showAddModal() {
            document.getElementById('modal-title').textContent = 'Add Number';
            document.getElementById('number-form').reset();
            document.getElementById('edit-phone').value = '';
            document.getElementById('phone_number').disabled = false;
            document.getElementById('is_active').checked = true;
            document.getElementById('modal').classList.add('active');
        }

        async function editNumber(phone) {
            const resp = await fetch(`${API}/${encodeURIComponent(phone)}`);
            const n = await resp.json();

            document.getElementById('modal-title').textContent = 'Edit Number';
            document.getElementById('edit-phone').value = phone;
            document.getElementById('phone_number').value = n.phone_number;
            document.getElementById('phone_number').disabled = true;
            document.getElementById('business_name').value = n.business_name;
            document.getElementById('business_type').value = n.business_type;
            document.getElementById('greeting_name').value = n.greeting_name;
            document.getElementById('system_prompt').value = n.system_prompt || '';
            document.getElementById('is_active').checked = n.is_active;
            document.getElementById('modal').classList.add('active');
        }

        function closeModal() {
            document.getElementById('modal').classList.remove('active');
        }

        async function saveNumber(e) {
            e.preventDefault();
            const editPhone = document.getElementById('edit-phone').value;
            const isEdit = !!editPhone;

            const data = {
                phone_number: document.getElementById('phone_number').value,
                business_name: document.getElementById('business_name').value,
                business_type: document.getElementById('business_type').value,
                greeting_name: document.getElementById('greeting_name').value,
                system_prompt: document.getElementById('system_prompt').value || null,
                is_active: document.getElementById('is_active').checked
            };

            const url = isEdit ? `${API}/${encodeURIComponent(editPhone)}` : API;
            const method = isEdit ? 'PUT' : 'POST';

            const resp = await fetch(url, {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });

            if (resp.ok) {
                closeModal();
                loadNumbers();
            } else {
                const err = await resp.json();
                alert(err.detail || 'Error saving number');
            }
        }

        async function deleteNumber(phone) {
            if (!confirm(`Delete ${phone}?`)) return;

            const resp = await fetch(`${API}/${encodeURIComponent(phone)}`, { method: 'DELETE' });
            if (resp.ok) {
                loadNumbers();
            } else {
                alert('Error deleting number');
            }
        }

        // Load on page load
        loadNumbers();
    </script>
</body>
</html>
"""

@router.get("/admin", response_class=HTMLResponse)
async def admin_ui():
    """Serve the admin UI."""
    return ADMIN_HTML
