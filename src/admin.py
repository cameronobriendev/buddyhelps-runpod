"""
Admin routes for managing phone numbers, system prompts, keyword corrections, and Twilio numbers.
Tabbed HTML UI + JSON API.
"""
import logging
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, Dict
from src import database as db
from src.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# ============ Phone Numbers API ============

class PhoneNumberCreate(BaseModel):
    phone_number: str
    business_name: str
    business_type: str = "plumber"
    greeting_name: str = "Benny"
    system_prompt_id: Optional[int] = None
    keyword_corrections_id: Optional[int] = None
    is_demo: bool = False
    is_active: bool = True

class PhoneNumberUpdate(BaseModel):
    business_name: Optional[str] = None
    business_type: Optional[str] = None
    greeting_name: Optional[str] = None
    system_prompt_id: Optional[int] = None
    keyword_corrections_id: Optional[int] = None
    is_demo: Optional[bool] = None
    is_active: Optional[bool] = None

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


# ============ System Prompts API ============

class PromptCreate(BaseModel):
    name: str
    content: str

class PromptUpdate(BaseModel):
    name: Optional[str] = None
    content: Optional[str] = None

@router.get("/api/prompts")
async def list_prompts():
    """List all system prompts."""
    return db.get_all_prompts()

@router.get("/api/prompts/{prompt_id}")
async def get_prompt(prompt_id: int):
    """Get a specific system prompt."""
    result = db.get_prompt(prompt_id)
    if not result:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return result

@router.post("/api/prompts")
async def create_prompt(data: PromptCreate):
    """Create a new system prompt."""
    try:
        return db.add_prompt(data.name, data.content)
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(status_code=400, detail="Prompt name already exists")
        raise

@router.put("/api/prompts/{prompt_id}")
async def update_prompt(prompt_id: int, data: PromptUpdate):
    """Update a system prompt."""
    existing = db.get_prompt(prompt_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return db.update_prompt(prompt_id, data.name, data.content)

@router.delete("/api/prompts/{prompt_id}")
async def delete_prompt(prompt_id: int):
    """Delete a system prompt."""
    if db.delete_prompt(prompt_id):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Prompt not found")


# ============ Keywords API ============

class KeywordsCreate(BaseModel):
    name: str
    corrections: Dict[str, str]

class KeywordsUpdate(BaseModel):
    name: Optional[str] = None
    corrections: Optional[Dict[str, str]] = None

@router.get("/api/keywords")
async def list_keywords():
    """List all keyword correction sets."""
    return db.get_all_keywords()

@router.get("/api/keywords/{keyword_id}")
async def get_keywords(keyword_id: int):
    """Get a specific keyword correction set."""
    result = db.get_keywords(keyword_id)
    if not result:
        raise HTTPException(status_code=404, detail="Keyword set not found")
    return result

@router.post("/api/keywords")
async def create_keywords(data: KeywordsCreate):
    """Create a new keyword correction set."""
    try:
        return db.add_keywords(data.name, data.corrections)
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(status_code=400, detail="Keyword set name already exists")
        raise

@router.put("/api/keywords/{keyword_id}")
async def update_keywords(keyword_id: int, data: KeywordsUpdate):
    """Update a keyword correction set."""
    existing = db.get_keywords(keyword_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Keyword set not found")
    return db.update_keywords(keyword_id, data.name, data.corrections)

@router.delete("/api/keywords/{keyword_id}")
async def delete_keywords(keyword_id: int):
    """Delete a keyword correction set."""
    if db.delete_keywords(keyword_id):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Keyword set not found")


# ============ Twilio Numbers API ============

def get_twilio_client():
    """Get Twilio client, lazy import to avoid startup errors if not configured."""
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        raise HTTPException(status_code=500, detail="Twilio credentials not configured")
    from twilio.rest import Client
    return Client(settings.twilio_account_sid, settings.twilio_auth_token)


# Area code to region mapping (US/Canada)
AREA_CODE_REGIONS = {
    # Alberta
    "403": "Calgary, AB", "587": "Alberta", "780": "Edmonton, AB", "825": "Alberta",
    # British Columbia
    "604": "Vancouver, BC", "778": "BC", "236": "BC", "250": "BC",
    # Ontario
    "416": "Toronto, ON", "647": "Toronto, ON", "437": "Toronto, ON", "905": "GTA, ON",
    "289": "GTA, ON", "365": "GTA, ON", "519": "SW Ontario", "226": "SW Ontario",
    "613": "Ottawa, ON", "343": "Ottawa, ON", "705": "N Ontario", "249": "N Ontario",
    # Quebec
    "514": "Montreal, QC", "438": "Montreal, QC", "450": "QC", "579": "QC",
    # US - Common
    "775": "Nevada", "702": "Las Vegas, NV", "817": "Fort Worth, TX", "214": "Dallas, TX",
    "512": "Austin, TX", "415": "San Francisco, CA", "213": "Los Angeles, CA",
    "310": "Los Angeles, CA", "212": "New York, NY", "646": "New York, NY",
}

def get_region_from_phone(phone: str) -> str:
    """Extract area code and return region."""
    # Phone format: +1XXXYYYZZZZ
    if phone and len(phone) >= 5:
        area_code = phone[2:5] if phone.startswith("+1") else phone[1:4]
        return AREA_CODE_REGIONS.get(area_code, area_code)
    return ""


@router.get("/api/twilio/numbers")
async def list_twilio_numbers():
    """List all phone numbers owned by the Twilio account."""
    try:
        client = get_twilio_client()
        numbers = client.incoming_phone_numbers.list(limit=50)
        return [{
            "phone": n.phone_number,
            "sid": n.sid,
            "friendly_name": n.friendly_name,
            "voice_url": n.voice_url,
            "sms_url": n.sms_url,
            "region": get_region_from_phone(n.phone_number),
        } for n in numbers]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Twilio list error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/twilio/search")
async def search_available_numbers(country: str = "CA", area_code: str = "587"):
    """Search for available phone numbers to purchase."""
    try:
        client = get_twilio_client()
        available = client.available_phone_numbers(country).local.list(
            area_code=int(area_code) if area_code else None,
            limit=10
        )
        return [{
            "phone": n.phone_number,
            "locality": n.locality,
            "region": n.region,
            "postal_code": n.postal_code,
        } for n in available]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Twilio search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class TwilioBuyRequest(BaseModel):
    phone_number: str


@router.post("/api/twilio/buy")
async def buy_twilio_number(data: TwilioBuyRequest):
    """Purchase a phone number and configure webhook."""
    try:
        client = get_twilio_client()
        webhook_url = f"https://{settings.runpod_endpoint}/twilio/voice"

        incoming = client.incoming_phone_numbers.create(
            phone_number=data.phone_number,
            voice_url=webhook_url,
            voice_method="POST",
            friendly_name=f"BuddyHelps {data.phone_number[-4:]}"
        )
        return {
            "sid": incoming.sid,
            "phone": incoming.phone_number,
            "voice_url": incoming.voice_url,
            "friendly_name": incoming.friendly_name,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Twilio buy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/twilio/configure/{sid}")
async def configure_twilio_number(sid: str):
    """Configure webhook on an existing Twilio number."""
    try:
        client = get_twilio_client()
        webhook_url = f"https://{settings.runpod_endpoint}/twilio/voice"

        number = client.incoming_phone_numbers(sid).update(
            voice_url=webhook_url,
            voice_method="POST"
        )
        return {
            "phone": number.phone_number,
            "voice_url": number.voice_url,
            "friendly_name": number.friendly_name,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Twilio configure error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class TwilioUpdateRequest(BaseModel):
    friendly_name: str


@router.put("/api/twilio/numbers/{sid}")
async def update_twilio_number(sid: str, data: TwilioUpdateRequest):
    """Update a Twilio number's friendly name."""
    try:
        client = get_twilio_client()
        number = client.incoming_phone_numbers(sid).update(
            friendly_name=data.friendly_name
        )
        return {
            "phone": number.phone_number,
            "sid": number.sid,
            "friendly_name": number.friendly_name,
            "voice_url": number.voice_url,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Twilio update error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============ HTML Admin UI ============

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
        .container { max-width: 1100px; margin: 0 auto; }
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
        input, select, textarea { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 4px; margin-bottom: 10px; font-size: 14px; font-family: inherit; }
        label { display: block; margin-bottom: 4px; font-weight: 500; color: #555; }
        .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }
        .actions { display: flex; gap: 8px; }
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 100; overflow-y: auto; }
        .modal-content { background: white; max-width: 600px; margin: 50px auto; padding: 20px; border-radius: 8px; }
        .modal.active { display: block; }
        .close { float: right; font-size: 24px; cursor: pointer; }
        .empty { text-align: center; padding: 40px; color: #666; }

        /* Tabs */
        .tabs { display: flex; gap: 0; margin-bottom: 20px; }
        .tab { padding: 12px 24px; background: #e9ecef; border: none; cursor: pointer; font-size: 14px; font-weight: 500; }
        .tab:first-child { border-radius: 8px 0 0 8px; }
        .tab:last-child { border-radius: 0 8px 8px 0; }
        .tab.active { background: #007bff; color: white; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }

        /* Prompt preview */
        .prompt-preview { font-size: 13px; color: #666; max-width: 300px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        code { background: #f4f4f4; padding: 2px 6px; border-radius: 3px; font-size: 12px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>BuddyHelps Admin</h1>

        <div class="tabs">
            <button class="tab active" onclick="showTab('numbers')">Phone Numbers</button>
            <button class="tab" onclick="showTab('prompts')">System Prompts</button>
            <button class="tab" onclick="showTab('keywords')">Keywords</button>
            <button class="tab" onclick="showTab('twilio')">Twilio Numbers</button>
        </div>

        <!-- Phone Numbers Tab -->
        <div id="numbers-tab" class="tab-content active">
            <div class="card">
                <button class="btn-primary" onclick="showAddNumberModal()">+ Add Number</button>
            </div>

            <div class="card">
                <table>
                    <thead>
                        <tr>
                            <th>Phone Number</th>
                            <th>Business</th>
                            <th>Type</th>
                            <th>Greeting</th>
                            <th>Prompt</th>
                            <th>Keywords</th>
                            <th>Mode</th>
                            <th>Status</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody id="numbers-table">
                        <tr><td colspan="9" class="empty">Loading...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>

        <!-- System Prompts Tab -->
        <div id="prompts-tab" class="tab-content">
            <div class="card">
                <button class="btn-primary" onclick="showAddPromptModal()">+ Add Prompt</button>
            </div>

            <div class="card">
                <table>
                    <thead>
                        <tr>
                            <th>Name</th>
                            <th>Preview</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody id="prompts-table">
                        <tr><td colspan="3" class="empty">Loading...</td></tr>
                    </tbody>
                </table>
            </div>

            <div class="card">
                <h3>Available Variables</h3>
                <p>Use these in your prompts:</p>
                <ul>
                    <li><code>{business_name}</code> - The business name</li>
                    <li><code>{owner_name}</code> - The owner's name</li>
                    <li><code>{greeting_name}</code> - What the AI introduces itself as</li>
                </ul>
            </div>
        </div>

        <!-- Keywords Tab -->
        <div id="keywords-tab" class="tab-content">
            <div class="card">
                <button class="btn-primary" onclick="showAddKeywordsModal()">+ Add Keyword Set</button>
            </div>

            <div class="card">
                <table>
                    <thead>
                        <tr>
                            <th>Name</th>
                            <th>Corrections</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody id="keywords-table">
                        <tr><td colspan="3" class="empty">Loading...</td></tr>
                    </tbody>
                </table>
            </div>

            <div class="card">
                <h3>What Are Keywords?</h3>
                <p>Phone audio quality causes STT to mishear domain-specific words. Keywords correct these before sending to the LLM.</p>
                <p><strong>Example:</strong> "quogged" → "clogged", "fossit" → "faucet"</p>
            </div>
        </div>

        <!-- Twilio Numbers Tab -->
        <div id="twilio-tab" class="tab-content">
            <div class="card">
                <h3>Your Twilio Numbers</h3>
                <p>Numbers owned by your Twilio account. Import them to BuddyHelps or configure webhooks.</p>
                <button class="btn-primary" onclick="loadTwilioNumbers()" style="margin-top: 10px;">Refresh</button>
            </div>

            <div class="card">
                <table>
                    <thead>
                        <tr>
                            <th>Phone Number</th>
                            <th>Region</th>
                            <th>Friendly Name</th>
                            <th>Voice URL</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody id="twilio-numbers-table">
                        <tr><td colspan="5" class="empty">Loading...</td></tr>
                    </tbody>
                </table>
            </div>

            <div class="card">
                <h3>Buy New Number</h3>
                <div class="form-row">
                    <div>
                        <label>Country</label>
                        <select id="twilio-country">
                            <option value="CA">Canada</option>
                            <option value="US">United States</option>
                        </select>
                    </div>
                    <div>
                        <label>Area Code</label>
                        <input type="text" id="twilio-area-code" placeholder="587" maxlength="3">
                    </div>
                </div>
                <button class="btn-primary" onclick="searchTwilioNumbers()">Search Available Numbers</button>
            </div>

            <div class="card" id="twilio-search-results" style="display: none;">
                <h3>Available Numbers</h3>
                <table>
                    <thead>
                        <tr>
                            <th>Phone Number</th>
                            <th>Location</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody id="twilio-search-table">
                    </tbody>
                </table>
                <p style="font-size: 12px; color: #666; margin-top: 10px;">
                    Cost: ~$1.15 CAD/month + ~$0.0085 USD/min inbound
                </p>
            </div>
        </div>
    </div>

    <!-- Add/Edit Number Modal -->
    <div id="number-modal" class="modal">
        <div class="modal-content">
            <span class="close" onclick="closeModal('number-modal')">&times;</span>
            <h2 id="number-modal-title">Add Number</h2>
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

                <label>System Prompt</label>
                <select id="system_prompt_id">
                    <option value="">-- No prompt (use default) --</option>
                </select>

                <label>Keyword Corrections</label>
                <select id="keyword_corrections_id">
                    <option value="">-- No corrections --</option>
                </select>

                <div class="form-row">
                    <label>
                        <input type="checkbox" id="is_demo"> Demo Number (for testing)
                    </label>
                    <label>
                        <input type="checkbox" id="is_active" checked> Active
                    </label>
                </div>

                <br><br>
                <button type="submit" class="btn-success">Save</button>
            </form>
        </div>
    </div>

    <!-- Add/Edit Prompt Modal -->
    <div id="prompt-modal" class="modal">
        <div class="modal-content">
            <span class="close" onclick="closeModal('prompt-modal')">&times;</span>
            <h2 id="prompt-modal-title">Add Prompt</h2>
            <form id="prompt-form" onsubmit="savePrompt(event)">
                <input type="hidden" id="edit-prompt-id">

                <label>Prompt Name</label>
                <input type="text" id="prompt_name" placeholder="Default Plumber" required>

                <label>Prompt Content</label>
                <textarea id="prompt_content" rows="15" placeholder="You are {greeting_name}, answering phones for {business_name}...

WHO YOU ARE:
- Friendly, warm, genuinely helpful
- You work with {owner_name}

YOUR GOAL:
Have a real conversation. Listen. Make the caller feel heard.

HOW YOU TALK:
- Keep responses brief (1-3 sentences)
- Never give quotes or prices" required></textarea>

                <br>
                <button type="submit" class="btn-success">Save</button>
            </form>
        </div>
    </div>

    <!-- Add/Edit Keywords Modal -->
    <div id="keywords-modal" class="modal">
        <div class="modal-content">
            <span class="close" onclick="closeModal('keywords-modal')">&times;</span>
            <h2 id="keywords-modal-title">Add Keyword Set</h2>
            <form id="keywords-form" onsubmit="saveKeywords(event)">
                <input type="hidden" id="edit-keywords-id">

                <label>Set Name</label>
                <input type="text" id="keywords_name" placeholder="Plumbing" required>

                <label>Corrections (JSON format)</label>
                <textarea id="keywords_corrections" rows="12" placeholder='{
  "quogged": "clogged",
  "quarked": "clogged",
  "fossit": "faucet",
  "toylet": "toilet"
}' required></textarea>

                <p style="font-size: 12px; color: #666;">Format: {"misheard": "correct", ...}</p>

                <br>
                <button type="submit" class="btn-success">Save</button>
            </form>
        </div>
    </div>

    <script>
        const NUMBERS_API = '/api/numbers';
        const PROMPTS_API = '/api/prompts';
        const KEYWORDS_API = '/api/keywords';
        const TWILIO_API = '/api/twilio';
        let promptsCache = [];
        let keywordsCache = [];

        // ============ Tab Navigation ============
        function showTab(tab) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.querySelector(`.tab[onclick="showTab('${tab}')"]`).classList.add('active');
            document.getElementById(`${tab}-tab`).classList.add('active');
        }

        // ============ Numbers ============
        async function loadNumbers() {
            const [numbersResp, promptsResp, keywordsResp] = await Promise.all([
                fetch(NUMBERS_API),
                fetch(PROMPTS_API),
                fetch(KEYWORDS_API)
            ]);
            const numbers = await numbersResp.json();
            promptsCache = await promptsResp.json();
            keywordsCache = await keywordsResp.json();

            // Update prompt dropdown
            const promptSelect = document.getElementById('system_prompt_id');
            promptSelect.innerHTML = '<option value="">-- No prompt (use default) --</option>' +
                promptsCache.map(p => `<option value="${p.id}">${p.name}</option>`).join('');

            // Update keywords dropdown
            const keywordsSelect = document.getElementById('keyword_corrections_id');
            keywordsSelect.innerHTML = '<option value="">-- No corrections --</option>' +
                keywordsCache.map(k => `<option value="${k.id}">${k.name}</option>`).join('');

            const tbody = document.getElementById('numbers-table');
            if (numbers.length === 0) {
                tbody.innerHTML = '<tr><td colspan="9" class="empty">No phone numbers configured. Add one to get started.</td></tr>';
                return;
            }

            tbody.innerHTML = numbers.map(n => {
                const prompt = promptsCache.find(p => p.id === n.system_prompt_id);
                const keywords = keywordsCache.find(k => k.id === n.keyword_corrections_id);
                return `
                    <tr>
                        <td><strong>${n.phone_number}</strong></td>
                        <td>${n.business_name}</td>
                        <td><span class="badge badge-type">${n.business_type}</span></td>
                        <td>${n.greeting_name}</td>
                        <td>${prompt ? prompt.name : '<em style="color:#999">Default</em>'}</td>
                        <td>${keywords ? keywords.name : '<em style="color:#999">None</em>'}</td>
                        <td><span class="badge ${n.is_demo ? 'badge-inactive' : 'badge-type'}">${n.is_demo ? 'Demo' : 'Live'}</span></td>
                        <td><span class="badge ${n.is_active ? 'badge-active' : 'badge-inactive'}">${n.is_active ? 'Active' : 'Inactive'}</span></td>
                        <td class="actions">
                            <button onclick="editNumber('${n.phone_number}')" class="btn-primary">Edit</button>
                            <button onclick="deleteNumber('${n.phone_number}')" class="btn-danger">Delete</button>
                        </td>
                    </tr>
                `;
            }).join('');
        }

        function showAddNumberModal() {
            document.getElementById('number-modal-title').textContent = 'Add Number';
            document.getElementById('number-form').reset();
            document.getElementById('edit-phone').value = '';
            document.getElementById('phone_number').disabled = false;
            document.getElementById('is_demo').checked = false;
            document.getElementById('is_active').checked = true;
            document.getElementById('number-modal').classList.add('active');
        }

        async function editNumber(phone) {
            const resp = await fetch(`${NUMBERS_API}/${encodeURIComponent(phone)}`);
            const n = await resp.json();

            document.getElementById('number-modal-title').textContent = 'Edit Number';
            document.getElementById('edit-phone').value = phone;
            document.getElementById('phone_number').value = n.phone_number;
            document.getElementById('phone_number').disabled = true;
            document.getElementById('business_name').value = n.business_name;
            document.getElementById('business_type').value = n.business_type;
            document.getElementById('greeting_name').value = n.greeting_name;
            document.getElementById('system_prompt_id').value = n.system_prompt_id || '';
            document.getElementById('keyword_corrections_id').value = n.keyword_corrections_id || '';
            document.getElementById('is_demo').checked = n.is_demo;
            document.getElementById('is_active').checked = n.is_active;
            document.getElementById('number-modal').classList.add('active');
        }

        async function saveNumber(e) {
            e.preventDefault();
            const editPhone = document.getElementById('edit-phone').value;
            const isEdit = !!editPhone;

            const promptId = document.getElementById('system_prompt_id').value;
            const keywordsId = document.getElementById('keyword_corrections_id').value;
            const data = {
                phone_number: document.getElementById('phone_number').value,
                business_name: document.getElementById('business_name').value,
                business_type: document.getElementById('business_type').value,
                greeting_name: document.getElementById('greeting_name').value,
                system_prompt_id: promptId ? parseInt(promptId) : null,
                keyword_corrections_id: keywordsId ? parseInt(keywordsId) : null,
                is_demo: document.getElementById('is_demo').checked,
                is_active: document.getElementById('is_active').checked
            };

            const url = isEdit ? `${NUMBERS_API}/${encodeURIComponent(editPhone)}` : NUMBERS_API;
            const method = isEdit ? 'PUT' : 'POST';

            const resp = await fetch(url, {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });

            if (resp.ok) {
                closeModal('number-modal');
                loadNumbers();
            } else {
                const err = await resp.json();
                alert(err.detail || 'Error saving number');
            }
        }

        async function deleteNumber(phone) {
            if (!confirm(`Delete ${phone}?`)) return;
            const resp = await fetch(`${NUMBERS_API}/${encodeURIComponent(phone)}`, { method: 'DELETE' });
            if (resp.ok) {
                loadNumbers();
            } else {
                alert('Error deleting number');
            }
        }

        // ============ Prompts ============
        async function loadPrompts() {
            const resp = await fetch(PROMPTS_API);
            const prompts = await resp.json();
            promptsCache = prompts;

            const tbody = document.getElementById('prompts-table');
            if (prompts.length === 0) {
                tbody.innerHTML = '<tr><td colspan="3" class="empty">No prompts. Add one to get started.</td></tr>';
                return;
            }

            tbody.innerHTML = prompts.map(p => `
                <tr>
                    <td><strong>${p.name}</strong></td>
                    <td class="prompt-preview">${p.content.replace(/\\n/g, ' ').substring(0, 100)}...</td>
                    <td class="actions">
                        <button onclick="editPrompt(${p.id})" class="btn-primary">Edit</button>
                        <button onclick="deletePrompt(${p.id}, '${p.name}')" class="btn-danger">Delete</button>
                    </td>
                </tr>
            `).join('');
        }

        function showAddPromptModal() {
            document.getElementById('prompt-modal-title').textContent = 'Add Prompt';
            document.getElementById('prompt-form').reset();
            document.getElementById('edit-prompt-id').value = '';
            document.getElementById('prompt-modal').classList.add('active');
        }

        async function editPrompt(id) {
            const resp = await fetch(`${PROMPTS_API}/${id}`);
            const p = await resp.json();

            document.getElementById('prompt-modal-title').textContent = 'Edit Prompt';
            document.getElementById('edit-prompt-id').value = id;
            document.getElementById('prompt_name').value = p.name;
            document.getElementById('prompt_content').value = p.content;
            document.getElementById('prompt-modal').classList.add('active');
        }

        async function savePrompt(e) {
            e.preventDefault();
            const editId = document.getElementById('edit-prompt-id').value;
            const isEdit = !!editId;

            const data = {
                name: document.getElementById('prompt_name').value,
                content: document.getElementById('prompt_content').value
            };

            const url = isEdit ? `${PROMPTS_API}/${editId}` : PROMPTS_API;
            const method = isEdit ? 'PUT' : 'POST';

            const resp = await fetch(url, {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });

            if (resp.ok) {
                closeModal('prompt-modal');
                loadPrompts();
                loadNumbers(); // Refresh to update prompt names
            } else {
                const err = await resp.json();
                alert(err.detail || 'Error saving prompt');
            }
        }

        async function deletePrompt(id, name) {
            if (!confirm(`Delete prompt "${name}"? Numbers using it will revert to default.`)) return;
            const resp = await fetch(`${PROMPTS_API}/${id}`, { method: 'DELETE' });
            if (resp.ok) {
                loadPrompts();
                loadNumbers();
            } else {
                alert('Error deleting prompt');
            }
        }

        // ============ Keywords ============
        async function loadKeywords() {
            const resp = await fetch(KEYWORDS_API);
            const keywords = await resp.json();
            keywordsCache = keywords;

            const tbody = document.getElementById('keywords-table');
            if (keywords.length === 0) {
                tbody.innerHTML = '<tr><td colspan="3" class="empty">No keyword sets. Add one to get started.</td></tr>';
                return;
            }

            tbody.innerHTML = keywords.map(k => {
                const count = Object.keys(k.corrections).length;
                const preview = Object.entries(k.corrections).slice(0, 3)
                    .map(([wrong, right]) => `${wrong}→${right}`).join(', ');
                return `
                    <tr>
                        <td><strong>${k.name}</strong></td>
                        <td class="prompt-preview">${count} corrections: ${preview}${count > 3 ? '...' : ''}</td>
                        <td class="actions">
                            <button onclick="editKeywords(${k.id})" class="btn-primary">Edit</button>
                            <button onclick="deleteKeywords(${k.id}, '${k.name}')" class="btn-danger">Delete</button>
                        </td>
                    </tr>
                `;
            }).join('');
        }

        function showAddKeywordsModal() {
            document.getElementById('keywords-modal-title').textContent = 'Add Keyword Set';
            document.getElementById('keywords-form').reset();
            document.getElementById('edit-keywords-id').value = '';
            document.getElementById('keywords-modal').classList.add('active');
        }

        async function editKeywords(id) {
            const resp = await fetch(`${KEYWORDS_API}/${id}`);
            const k = await resp.json();

            document.getElementById('keywords-modal-title').textContent = 'Edit Keyword Set';
            document.getElementById('edit-keywords-id').value = id;
            document.getElementById('keywords_name').value = k.name;
            document.getElementById('keywords_corrections').value = JSON.stringify(k.corrections, null, 2);
            document.getElementById('keywords-modal').classList.add('active');
        }

        async function saveKeywords(e) {
            e.preventDefault();
            const editId = document.getElementById('edit-keywords-id').value;
            const isEdit = !!editId;

            let corrections;
            try {
                corrections = JSON.parse(document.getElementById('keywords_corrections').value);
            } catch (err) {
                alert('Invalid JSON format. Please check the corrections field.');
                return;
            }

            const data = {
                name: document.getElementById('keywords_name').value,
                corrections: corrections
            };

            const url = isEdit ? `${KEYWORDS_API}/${editId}` : KEYWORDS_API;
            const method = isEdit ? 'PUT' : 'POST';

            const resp = await fetch(url, {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });

            if (resp.ok) {
                closeModal('keywords-modal');
                loadKeywords();
                loadNumbers(); // Refresh to update keywords names
            } else {
                const err = await resp.json();
                alert(err.detail || 'Error saving keyword set');
            }
        }

        async function deleteKeywords(id, name) {
            if (!confirm(`Delete keyword set "${name}"? Numbers using it will have no corrections.`)) return;
            const resp = await fetch(`${KEYWORDS_API}/${id}`, { method: 'DELETE' });
            if (resp.ok) {
                loadKeywords();
                loadNumbers();
            } else {
                alert('Error deleting keyword set');
            }
        }

        // ============ Twilio Numbers ============
        async function loadTwilioNumbers() {
            const tbody = document.getElementById('twilio-numbers-table');
            tbody.innerHTML = '<tr><td colspan="4" class="empty">Loading...</td></tr>';

            try {
                const resp = await fetch(`${TWILIO_API}/numbers`);
                if (!resp.ok) {
                    const err = await resp.json();
                    tbody.innerHTML = `<tr><td colspan="4" class="empty">${err.detail || 'Error loading Twilio numbers'}</td></tr>`;
                    return;
                }

                const numbers = await resp.json();
                if (numbers.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="5" class="empty">No numbers in your Twilio account.</td></tr>';
                    return;
                }

                tbody.innerHTML = numbers.map(n => {
                    const voiceUrl = n.voice_url || '<em style="color:#999">Not configured</em>';
                    const isConfigured = n.voice_url && n.voice_url.includes('runpod');
                    const escapedName = (n.friendly_name || '').replace(/'/g, "\\'");
                    return `
                        <tr>
                            <td><strong>${n.phone}</strong></td>
                            <td>${n.region || '-'}</td>
                            <td>
                                <span id="name-${n.sid}">${n.friendly_name || '-'}</span>
                                <button onclick="editTwilioName('${n.sid}', '${escapedName}')" style="padding: 2px 6px; font-size: 11px; margin-left: 5px;">Edit</button>
                            </td>
                            <td style="max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${n.voice_url || ''}">${voiceUrl}</td>
                            <td class="actions">
                                <button onclick="importTwilioNumber('${n.phone}')" class="btn-primary">Import</button>
                                ${!isConfigured ? `<button onclick="configureTwilioNumber('${n.sid}')" class="btn-success">Set Webhook</button>` : ''}
                            </td>
                        </tr>
                    `;
                }).join('');
            } catch (err) {
                tbody.innerHTML = '<tr><td colspan="5" class="empty">Error connecting to Twilio API</td></tr>';
            }
        }

        async function searchTwilioNumbers() {
            const country = document.getElementById('twilio-country').value;
            const areaCode = document.getElementById('twilio-area-code').value;

            const resultsDiv = document.getElementById('twilio-search-results');
            const tbody = document.getElementById('twilio-search-table');

            resultsDiv.style.display = 'block';
            tbody.innerHTML = '<tr><td colspan="3" class="empty">Searching...</td></tr>';

            try {
                const resp = await fetch(`${TWILIO_API}/search?country=${country}&area_code=${areaCode}`);
                if (!resp.ok) {
                    const err = await resp.json();
                    tbody.innerHTML = `<tr><td colspan="3" class="empty">${err.detail || 'Error searching numbers'}</td></tr>`;
                    return;
                }

                const numbers = await resp.json();
                if (numbers.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="3" class="empty">No numbers available in that area code.</td></tr>';
                    return;
                }

                tbody.innerHTML = numbers.map(n => `
                    <tr>
                        <td><strong>${n.phone}</strong></td>
                        <td>${n.locality || ''}, ${n.region || ''}</td>
                        <td class="actions">
                            <button onclick="buyTwilioNumber('${n.phone}')" class="btn-success">Buy</button>
                        </td>
                    </tr>
                `).join('');
            } catch (err) {
                tbody.innerHTML = '<tr><td colspan="3" class="empty">Error connecting to Twilio API</td></tr>';
            }
        }

        async function buyTwilioNumber(phone) {
            if (!confirm(`Purchase ${phone} for ~$1.15 CAD/month?\\n\\nWebhook will be auto-configured to this server.`)) return;

            try {
                const resp = await fetch(`${TWILIO_API}/buy`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ phone_number: phone })
                });

                if (resp.ok) {
                    const result = await resp.json();
                    alert(`Purchased ${result.phone}!\\n\\nWebhook set to: ${result.voice_url}`);
                    loadTwilioNumbers();
                    document.getElementById('twilio-search-results').style.display = 'none';
                } else {
                    const err = await resp.json();
                    alert(err.detail || 'Error purchasing number');
                }
            } catch (err) {
                alert('Error connecting to Twilio API');
            }
        }

        async function configureTwilioNumber(sid) {
            if (!confirm('Configure this number to receive calls on this BuddyHelps server?')) return;

            try {
                const resp = await fetch(`${TWILIO_API}/configure/${sid}`, { method: 'POST' });

                if (resp.ok) {
                    const result = await resp.json();
                    alert(`Configured ${result.phone}!\\n\\nWebhook set to: ${result.voice_url}`);
                    loadTwilioNumbers();
                } else {
                    const err = await resp.json();
                    alert(err.detail || 'Error configuring number');
                }
            } catch (err) {
                alert('Error connecting to Twilio API');
            }
        }

        function importTwilioNumber(phone) {
            // Pre-fill the add number modal with this phone
            showAddNumberModal();
            document.getElementById('phone_number').value = phone;
        }

        async function editTwilioName(sid, currentName) {
            const newName = prompt('Enter new friendly name:', currentName);
            if (newName === null || newName === currentName) return;

            try {
                const resp = await fetch(`${TWILIO_API}/numbers/${sid}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ friendly_name: newName })
                });

                if (resp.ok) {
                    const result = await resp.json();
                    document.getElementById(`name-${sid}`).textContent = result.friendly_name;
                } else {
                    const err = await resp.json();
                    alert(err.detail || 'Error updating name');
                }
            } catch (err) {
                alert('Error connecting to Twilio API');
            }
        }

        // ============ Utils ============
        function closeModal(modalId) {
            document.getElementById(modalId).classList.remove('active');
        }

        // Load on page load
        loadNumbers();
        loadPrompts();
        loadKeywords();
        loadTwilioNumbers();
    </script>
</body>
</html>
"""

@router.get("/admin", response_class=HTMLResponse)
async def admin_ui():
    """Serve the admin UI."""
    return ADMIN_HTML
