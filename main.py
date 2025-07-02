from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import List, Dict
from fastapi.responses import FileResponse

app = FastAPI()

# Pydantic models
class NonprofitCreate(BaseModel):
    name: str
    address: str
    email: EmailStr

class EmailRequest(BaseModel):
    template: str
    emails: List[EmailStr]

class SentEmail(BaseModel):
    to: EmailStr
    body: str
    timestamp: datetime

# In-memory storage
nonprofits: Dict[str, NonprofitCreate] = {}
sent_emails: List[SentEmail] = []

# Pre-populate nonprofits for testing
@app.on_event("startup")
def startup_populate():
    sample_nonprofits = [
        NonprofitCreate(name="Helping Hands", address="123 Charity Lane, Springfield, IL", email="contact@helpinghands.org"),
        NonprofitCreate(name="Green Earth", address="456 Forest Ave, Portland, OR", email="info@greenearth.org"),
        NonprofitCreate(name="Food For All", address="789 Market St, San Francisco, CA", email="hello@foodforall.org"),
        NonprofitCreate(name="Books & Beyond", address="321 Library Rd, Boston, MA", email="support@booksbeyond.org"),
        NonprofitCreate(name="Shelter Safe", address="654 Home St, Austin, TX", email="admin@sheltersafe.org"),
    ]
    for np in sample_nonprofits:
        nonprofits[np.email] = np

# Create a nonprofit
@app.post("/nonprofits")
def create_nonprofit(nonprofit: NonprofitCreate):
    """Create a new nonprofit with name, address, and email."""
    if nonprofit.email in nonprofits:
        raise HTTPException(status_code=400, detail="Nonprofit already exists.")
    nonprofits[nonprofit.email] = nonprofit
    return {"message": "Nonprofit created successfully."}

# Send templated email
@app.post("/send-email")
def send_email(request: EmailRequest):
    """Send a templated email to a list of nonprofit emails. Template fields: {name}, {address}."""
    for email in request.emails:
        if email not in nonprofits:
            raise HTTPException(status_code=404, detail=f"Nonprofit with email {email} not found.")
        np = nonprofits[email]
        body = request.template.format(name=np.name, address=np.address)
        email_record = SentEmail(to=email, body=body, timestamp=datetime.utcnow())
        sent_emails.append(email_record)
    return {"message": "Emails sent successfully."}

# Get all sent emails
@app.get("/sent-emails", response_model=List[SentEmail])
def get_sent_emails():
    """Retrieve all sent emails."""
    return sent_emails

# Get all nonprofits
@app.get("/nonprofits", response_model=List[NonprofitCreate])
def get_all_nonprofits():
    """Retrieve all nonprofits."""
    return list(nonprofits.values())

# Health check endpoint
@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "ok"}

# Serve the index.html file
@app.get("/")
def read_index():
    return FileResponse("docs/index.html")
