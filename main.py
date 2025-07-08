from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import List, Dict
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from uuid import uuid4

app = FastAPI()

# Pydantic models
class NonprofitCreate(BaseModel):
    name: str
    address: str
    email: EmailStr

class SentEmail(BaseModel):
    to: EmailStr
    cc: List[EmailStr] = []
    body: str
    timestamp: datetime

# In-memory storage
nonprofits: Dict[str, NonprofitCreate] = {}
sent_emails: List[SentEmail] = []
email_drafts: Dict[str, dict] = {}

class EmailDraft(BaseModel):
    id: str
    template: str
    emails: List[EmailStr]
    cc: List[EmailStr] = []
    timestamp: datetime
    status: str = "draft"

@asynccontextmanager
async def lifespan(app: FastAPI):
    sample_nonprofits = [
        NonprofitCreate(name="Helping Hands", address="123 Charity Lane, Springfield, IL", email="contact@helpinghands.org"),
        NonprofitCreate(name="Green Earth", address="456 Forest Ave, Portland, OR", email="info@greenearth.org"),
        NonprofitCreate(name="Food For All", address="789 Market St, San Francisco, CA", email="hello@foodforall.org"),
        NonprofitCreate(name="Books & Beyond", address="321 Library Rd, Boston, MA", email="support@booksbeyond.org"),
        NonprofitCreate(name="Shelter Safe", address="654 Home St, Austin, TX", email="admin@sheltersafe.org"),
    ]
    for np in sample_nonprofits:
        nonprofits[np.email] = np
    yield

app = FastAPI(lifespan=lifespan)

# Create a nonprofit
@app.post("/nonprofits")
def create_nonprofit(nonprofit: NonprofitCreate):
    """Create a new nonprofit with name, address, and email."""
    if nonprofit.email in nonprofits:
        raise HTTPException(status_code=400, detail="Nonprofit already exists.")
    nonprofits[nonprofit.email] = nonprofit
    return {"message": "Nonprofit created successfully."}

# Send templated email
class EmailRequest(BaseModel):
    template: str
    emails: List[EmailStr]
    cc: List[EmailStr] = []

@app.post("/send-email")
def send_email(request: EmailRequest):
    """Send a templated email to a list of nonprofit emails. Template fields: {name}, {address}. Supports CC."""
    all_recipients = set(request.emails)
    cc_recipients = set(request.cc)
    for email in all_recipients.union(cc_recipients):
        if email not in nonprofits:
            raise HTTPException(status_code=404, detail=f"Nonprofit with email {email} not found.")
        np = nonprofits[email]
        body = request.template.format(name=np.name, address=np.address)
        # Determine if this is a cc recipient
        cc_list = list(cc_recipients) if email in cc_recipients else []
        email_record = SentEmail(to=email, cc=cc_list, body=body, timestamp=datetime.utcnow())
        sent_emails.append(email_record)
    return {"message": "Emails sent successfully."}

# Save a new draft
@app.post("/drafts", response_model=EmailDraft)
def save_draft(draft: EmailRequest):
    draft_id = str(uuid4())
    draft_obj = EmailDraft(
        id=draft_id,
        template=draft.template,
        emails=draft.emails,
        cc=draft.cc,
        timestamp=datetime.utcnow(),
        status="draft"
    )
    email_drafts[draft_id] = draft_obj.model_dump()
    return draft_obj

# Reload a draft
@app.get("/drafts/{draft_id}", response_model=EmailDraft)
def reload_draft(draft_id: str):
    if draft_id not in email_drafts:
        raise HTTPException(status_code=404, detail="Draft not found.")
    return email_drafts[draft_id]

# List all drafts
@app.get("/drafts", response_model=List[EmailDraft])
def list_drafts():
    return list(email_drafts.values())

# Send a draft
@app.post("/drafts/{draft_id}/send")
def send_draft(draft_id: str):
    if draft_id not in email_drafts:
        raise HTTPException(status_code=404, detail="Draft not found.")
    draft = email_drafts[draft_id]
    all_recipients = set(draft["emails"])
    cc_recipients = set(draft["cc"])
    for email in all_recipients.union(cc_recipients):
        if email not in nonprofits:
            raise HTTPException(status_code=404, detail=f"Nonprofit with email {email} not found.")
        np = nonprofits[email]
        body = draft["template"].format(name=np.name, address=np.address)
        cc_list = list(cc_recipients) if email in cc_recipients else []
        email_record = SentEmail(to=email, cc=cc_list, body=body, timestamp=datetime.utcnow())
        sent_emails.append(email_record)
    # Remove draft after sending
    del email_drafts[draft_id]
    return {"message": "Draft sent and deleted successfully."}

# Get all sent emails
@app.get("/sent-emails", response_model=List[SentEmail])
def get_sent_emails(to: str = Query(None, description="Filter by recipient email address"), cc: str = Query(None, description="Filter by cc email address")):
    """Retrieve all sent emails, optionally filtered by recipient or cc email address."""
    results = sent_emails
    if to:
        results = [email for email in results if email.to == to]
    if cc:
        results = [email for email in results if cc in email.cc]
    return results

# Get all nonprofits
@app.get("/nonprofits", response_model=List[NonprofitCreate])
def get_all_nonprofits(domain: str = Query(None, description="Filter nonprofits by email domain, e.g. greenearth.org")):
    """Retrieve all nonprofits, optionally filtered by email domain."""
    if domain:
        return [np for np in nonprofits.values() if np.email.endswith(f"@{domain}")]
    return list(nonprofits.values())

# Health check endpoint
@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "ok"}

# Serve the index.html file
@app.get("/")
def read_index():
    """Serve the index.html file."""
    return FileResponse("docs/index.html")
