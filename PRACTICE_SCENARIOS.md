# 🎯 Practice Exercise: Live Coding Scenarios

## Scenario 1: Implement Background Email Processing

**Interviewer:** "Let's modify your current code to handle email sending asynchronously. Show me how you'd implement this."

### Your Current Code (Problematic):

```python
@app.post("/send-email")
def send_email(request: EmailRequest):
    # This blocks the request thread!
    for email in request.emails:
        if email not in nonprofits:
            raise HTTPException(status_code=404, detail=f"Nonprofit with email {email} not found.")
        np = nonprofits[email]
        body = request.template.format(name=np.name, address=np.address)
        email_record = SentEmail(to=email, cc=[], body=body, timestamp=datetime.utcnow())
        sent_emails.append(email_record)  # Synchronous
    return {"message": "Emails sent successfully."}
```

### Solution to Implement:

```python
from fastapi import BackgroundTasks
import asyncio
from typing import Dict
import uuid

# In-memory job tracking (in production, use Redis)
job_status: Dict[str, dict] = {}

@app.post("/send-email")
async def send_email(request: EmailRequest, background_tasks: BackgroundTasks):
    """Non-blocking email sending with job tracking"""

    # Validate recipients exist (fast validation)
    for email in request.emails:
        if email not in nonprofits:
            raise HTTPException(status_code=404, detail=f"Nonprofit with email {email} not found.")

    # Create job ID
    job_id = str(uuid.uuid4())

    # Initialize job status
    job_status[job_id] = {
        "status": "queued",
        "total_emails": len(request.emails),
        "sent": 0,
        "failed": 0,
        "created_at": datetime.utcnow()
    }

    # Queue background task
    background_tasks.add_task(process_email_job, job_id, request)

    return {
        "job_id": job_id,
        "status": "queued",
        "message": f"Email job queued. {len(request.emails)} emails will be processed."
    }

async def process_email_job(job_id: str, request: EmailRequest):
    """Background task to process emails"""
    try:
        job_status[job_id]["status"] = "processing"

        for email in request.emails:
            try:
                # Simulate email sending delay
                await asyncio.sleep(0.1)  # Real email service call here

                np = nonprofits[email]
                body = request.template.format(name=np.name, address=np.address)
                email_record = SentEmail(to=email, cc=request.cc, body=body, timestamp=datetime.utcnow())
                sent_emails.append(email_record)

                job_status[job_id]["sent"] += 1

            except Exception as e:
                job_status[job_id]["failed"] += 1
                print(f"Failed to send email to {email}: {e}")

        job_status[job_id]["status"] = "completed"
        job_status[job_id]["completed_at"] = datetime.utcnow()

    except Exception as e:
        job_status[job_id]["status"] = "failed"
        job_status[job_id]["error"] = str(e)

@app.get("/jobs/{job_id}/status")
def get_job_status(job_id: str):
    """Check email job progress"""
    if job_id not in job_status:
        raise HTTPException(status_code=404, detail="Job not found")

    return job_status[job_id]

@app.get("/jobs")
def list_jobs():
    """List all email jobs"""
    return {
        "jobs": [
            {"job_id": job_id, **status}
            for job_id, status in job_status.items()
        ]
    }
```

---

## Scenario 2: Add Database Persistence

**Interviewer:** "Your in-memory storage won't work in production. Show me how you'd add a database layer."

### Solution to Implement:

```python
from sqlalchemy import create_engine, Column, String, DateTime, Text, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.sql import func
import os

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./nonprofits.db")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Database models
class NonprofitDB(Base):
    __tablename__ = "nonprofits"

    email = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    address = Column(Text, nullable=False)
    created_at = Column(DateTime, default=func.now())

class SentEmailDB(Base):
    __tablename__ = "sent_emails"

    id = Column(String, primary_key=True)
    to_email = Column(String, nullable=False, index=True)
    cc_emails = Column(Text)  # JSON string
    body = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=func.now())
    job_id = Column(String, index=True)

# Create tables
Base.metadata.create_all(bind=engine)

# Dependency to get database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Updated endpoints with database
@app.post("/nonprofits")
def create_nonprofit(nonprofit: NonprofitCreate, db: Session = Depends(get_db)):
    """Create nonprofit with database persistence"""

    # Check if exists
    existing = db.query(NonprofitDB).filter(NonprofitDB.email == nonprofit.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Nonprofit already exists.")

    # Create new nonprofit
    db_nonprofit = NonprofitDB(
        email=nonprofit.email,
        name=nonprofit.name,
        address=nonprofit.address
    )
    db.add(db_nonprofit)
    db.commit()

    return {"message": "Nonprofit created successfully."}

@app.get("/nonprofits")
def get_nonprofits(
    domain: str = Query(None),
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get nonprofits with pagination and filtering"""

    query = db.query(NonprofitDB)

    if domain:
        query = query.filter(NonprofitDB.email.like(f"%@{domain}"))

    nonprofits = query.offset(skip).limit(limit).all()

    return {
        "nonprofits": [
            {
                "name": np.name,
                "address": np.address,
                "email": np.email,
                "created_at": np.created_at
            }
            for np in nonprofits
        ],
        "total": query.count(),
        "skip": skip,
        "limit": limit
    }

# Updated email processing with database
async def process_email_job_db(job_id: str, request: EmailRequest, db: Session):
    """Process emails with database persistence"""
    import json

    try:
        job_status[job_id]["status"] = "processing"

        for email in request.emails:
            try:
                # Get nonprofit from database
                nonprofit = db.query(NonprofitDB).filter(NonprofitDB.email == email).first()
                if not nonprofit:
                    raise Exception(f"Nonprofit {email} not found in database")

                # Simulate email sending
                await asyncio.sleep(0.1)

                body = request.template.format(name=nonprofit.name, address=nonprofit.address)

                # Save to database
                email_record = SentEmailDB(
                    id=str(uuid.uuid4()),
                    to_email=email,
                    cc_emails=json.dumps(request.cc),
                    body=body,
                    job_id=job_id
                )
                db.add(email_record)
                db.commit()

                job_status[job_id]["sent"] += 1

            except Exception as e:
                job_status[job_id]["failed"] += 1
                print(f"Failed to send email to {email}: {e}")

        job_status[job_id]["status"] = "completed"

    except Exception as e:
        job_status[job_id]["status"] = "failed"
        job_status[job_id]["error"] = str(e)
```

---

## Scenario 3: Implement Rate Limiting

**Interviewer:** "How would you prevent abuse of your email API? Show me rate limiting implementation."

### Solution to Implement:

```python
from collections import defaultdict
from datetime import datetime, timedelta
import time

# In-memory rate limiting (use Redis in production)
rate_limit_storage = defaultdict(list)

class RateLimiter:
    def __init__(self, requests_per_minute: int = 10):
        self.requests_per_minute = requests_per_minute
        self.window_size = 60  # 1 minute in seconds

    def is_allowed(self, client_id: str) -> bool:
        """Check if request is allowed under rate limit"""
        now = time.time()

        # Clean old requests
        rate_limit_storage[client_id] = [
            req_time for req_time in rate_limit_storage[client_id]
            if now - req_time < self.window_size
        ]

        # Check if under limit
        if len(rate_limit_storage[client_id]) < self.requests_per_minute:
            rate_limit_storage[client_id].append(now)
            return True

        return False

    def time_until_reset(self, client_id: str) -> int:
        """Time in seconds until rate limit resets"""
        if not rate_limit_storage[client_id]:
            return 0

        oldest_request = min(rate_limit_storage[client_id])
        return max(0, int(self.window_size - (time.time() - oldest_request)))

# Rate limiting middleware
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # Only apply to API endpoints
    if not request.url.path.startswith("/send-email"):
        return await call_next(request)

    # Get client identifier (IP address)
    client_ip = request.client.host

    # Check rate limit
    rate_limiter = RateLimiter(requests_per_minute=5)  # 5 emails per minute

    if not rate_limiter.is_allowed(client_ip):
        time_until_reset = rate_limiter.time_until_reset(client_ip)
        return JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit exceeded",
                "retry_after": time_until_reset
            },
            headers={"Retry-After": str(time_until_reset)}
        )

    return await call_next(request)

# Alternative: Decorator-based rate limiting
def rate_limit(requests_per_minute: int = 10):
    def decorator(func):
        rate_limiter = RateLimiter(requests_per_minute)

        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get request object from FastAPI
            request = kwargs.get('request') or args[0]
            client_ip = request.client.host

            if not rate_limiter.is_allowed(client_ip):
                time_until_reset = rate_limiter.time_until_reset(client_ip)
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded. Try again in {time_until_reset} seconds.",
                    headers={"Retry-After": str(time_until_reset)}
                )

            return await func(*args, **kwargs)
        return wrapper
    return decorator

# Usage
@app.post("/send-email")
@rate_limit(requests_per_minute=3)
async def send_email_with_rate_limit(request: EmailRequest, background_tasks: BackgroundTasks):
    # Your existing email logic here
    pass
```

---

## Scenario 4: Add Monitoring and Health Checks

**Interviewer:** "How would you monitor this system in production? Show me health checks and metrics."

### Solution to Implement:

```python
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from datetime import datetime
import psutil
import sys

# Metrics
api_requests_total = Counter('api_requests_total', 'Total API requests', ['method', 'endpoint', 'status'])
email_jobs_total = Counter('email_jobs_total', 'Total email jobs', ['status'])
email_processing_duration = Histogram('email_processing_seconds', 'Email processing duration')
active_background_tasks = Gauge('active_background_tasks', 'Number of active background tasks')

# Health check dependencies
class HealthChecker:
    @staticmethod
    async def check_database(db: Session) -> dict:
        """Check database connectivity"""
        try:
            db.execute("SELECT 1")
            return {"status": "healthy", "latency_ms": 0}  # You'd measure actual latency
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    @staticmethod
    def check_memory() -> dict:
        """Check memory usage"""
        memory = psutil.virtual_memory()
        return {
            "status": "healthy" if memory.percent < 80 else "unhealthy",
            "usage_percent": memory.percent,
            "available_gb": round(memory.available / 1024**3, 2)
        }

    @staticmethod
    def check_disk() -> dict:
        """Check disk space"""
        disk = psutil.disk_usage('/')
        usage_percent = (disk.used / disk.total) * 100
        return {
            "status": "healthy" if usage_percent < 80 else "unhealthy",
            "usage_percent": round(usage_percent, 2),
            "free_gb": round(disk.free / 1024**3, 2)
        }

@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Comprehensive health check"""
    health_checker = HealthChecker()

    checks = {
        "database": await health_checker.check_database(db),
        "memory": health_checker.check_memory(),
        "disk": health_checker.check_disk(),
        "background_jobs": {
            "status": "healthy",
            "active_jobs": len([j for j in job_status.values() if j["status"] == "processing"]),
            "total_jobs": len(job_status)
        }
    }

    # Overall status
    overall_status = "healthy"
    if any(check["status"] == "unhealthy" for check in checks.values()):
        overall_status = "unhealthy"

    return {
        "status": overall_status,
        "timestamp": datetime.utcnow().isoformat(),
        "checks": checks,
        "version": "1.0.0"
    }

@app.get("/metrics")
def get_metrics():
    """Prometheus metrics endpoint"""
    return Response(generate_latest(), media_type="text/plain")

# Middleware to collect metrics
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start_time = time.time()

    # Process request
    response = await call_next(request)

    # Record metrics
    duration = time.time() - start_time

    # Record request
    api_requests_total.labels(
        method=request.method,
        endpoint=request.url.path,
        status=str(response.status_code)
    ).inc()

    return response

# Enhanced job tracking with metrics
async def process_email_job_with_metrics(job_id: str, request: EmailRequest):
    """Email processing with metrics collection"""
    start_time = time.time()
    active_background_tasks.inc()

    try:
        # Your existing email processing logic
        await process_email_job(job_id, request)

        # Record success
        email_jobs_total.labels(status="completed").inc()

    except Exception as e:
        # Record failure
        email_jobs_total.labels(status="failed").inc()
        raise

    finally:
        # Record duration and cleanup
        duration = time.time() - start_time
        email_processing_duration.observe(duration)
        active_background_tasks.dec()
```

---

## 🎯 Interview Tips

### 1. **Start Simple, Then Scale**

```
Interviewer: "Design email system for 1M emails/day"

Your Approach:
1. "Let me start with a basic design for 1K emails/day"
2. "Now let me identify bottlenecks for 100K emails/day"
3. "Finally, here's how I'd scale to 1M emails/day"
```

### 2. **Ask Clarifying Questions**

- "What's the acceptable latency for email sending?"
- "Do we need real-time status updates?"
- "What's the expected failure rate tolerance?"
- "Are there any compliance requirements?"

### 3. **Think Out Loud**

```
"I'm thinking about two approaches here:
1. Synchronous: Simple but doesn't scale
2. Asynchronous: More complex but scales better

Given the scale requirements, I'd go with asynchronous because..."
```

### 4. **Consider Trade-offs**

- **Consistency vs Availability**: "I'd choose eventual consistency here because..."
- **Latency vs Throughput**: "For bulk emails, throughput is more important than latency"
- **Cost vs Performance**: "We could use faster storage but it would increase costs"

### 5. **Have Numbers Ready**

- Database: ~1000 queries/second per core
- Redis: ~100K ops/second
- Network: ~1Gbps = 125MB/s
- SSD: ~500MB/s sequential, ~100MB/s random

Good luck with your interview! These scenarios should give you plenty of hands-on practice. 🚀
