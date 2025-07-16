# Nonprofits Workflow - System Design & Scalability Analysis

## Current System Limitations

### 1. **In-Memory Storage Bottlenecks**
```python
# Current problematic patterns:
nonprofits: Dict[str, NonprofitCreate] = {}     # ❌ Lost on restart
sent_emails: List[SentEmail] = []               # ❌ Memory grows infinitely
email_drafts: Dict[str, dict] = {}              # ❌ No persistence
```

**Problems:**
- **Data Loss**: All data lost on server restart
- **Memory Leak**: `sent_emails` list grows indefinitely
- **No Concurrency**: Race conditions with multiple workers
- **Limited Search**: O(n) operations for filtering

### 2. **Synchronous Email Processing**
```python
# Current blocking operation:
for email in all_recipients.union(cc_recipients):
    # This blocks the entire request thread
    body = request.template.format(name=np.name, address=np.address)
    email_record = SentEmail(to=email, cc=cc_list, body=body, timestamp=datetime.utcnow())
    sent_emails.append(email_record)
```

**Problems:**
- **Blocking I/O**: Sending 1000 emails blocks API for minutes
- **No Retry Logic**: Failed emails are lost
- **Resource Exhaustion**: Large email batches consume all server resources

### 3. **Missing Production Features**
- No authentication/authorization
- No rate limiting
- No logging/monitoring
- No error handling for edge cases
- No data validation beyond Pydantic

---

## Scalable Architecture Design

### Phase 1: Database Layer
```
Current: In-Memory Dicts/Lists
    ↓
Target: PostgreSQL + Redis Cache
```

**Database Schema:**
```sql
-- Nonprofits table
CREATE TABLE nonprofits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    address TEXT NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Email campaigns table
CREATE TABLE email_campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template TEXT NOT NULL,
    created_by UUID REFERENCES users(id),
    status VARCHAR(50) DEFAULT 'draft',
    created_at TIMESTAMP DEFAULT NOW()
);

-- Email sends table (for tracking individual emails)
CREATE TABLE email_sends (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id UUID REFERENCES email_campaigns(id),
    nonprofit_id UUID REFERENCES nonprofits(id),
    to_email VARCHAR(255) NOT NULL,
    cc_emails TEXT[], -- Array of emails
    body TEXT NOT NULL,
    status VARCHAR(50) DEFAULT 'pending', -- pending, sent, failed, bounced
    sent_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_nonprofits_email ON nonprofits(email);
CREATE INDEX idx_email_sends_campaign ON email_sends(campaign_id);
CREATE INDEX idx_email_sends_status ON email_sends(status);
CREATE INDEX idx_email_sends_sent_at ON email_sends(sent_at);
```

### Phase 2: Async Email Processing
```
Current: Synchronous Processing
    ↓
Target: Background Job Queue
```

**Architecture:**
```
API Request → Queue Job → Background Worker → Email Service
     ↓           ↓            ↓               ↓
  Return 202   Redis/RQ    Celery/RQ      SendGrid/SES
```

### Phase 3: Microservices Architecture
```
Monolith
    ↓
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│   User      │  │ Nonprofit   │  │   Email     │
│  Service    │  │  Service    │  │  Service    │
│             │  │             │  │             │
│ - Auth      │  │ - CRUD      │  │ - Templates │
│ - Users     │  │ - Search    │  │ - Sending   │
│ - Roles     │  │ - Import    │  │ - Tracking  │
└─────────────┘  └─────────────┘  └─────────────┘
```

---

## Implementation Roadmap

### Stage 1: Database Migration (Week 1)
**Goal:** Replace in-memory storage with PostgreSQL

**Key Changes:**
1. **Database Models** (SQLAlchemy/Tortoise ORM)
2. **Connection Pool** (asyncpg for FastAPI)
3. **Migration System** (Alembic)
4. **Data Access Layer** (Repository pattern)

**Code Structure:**
```
models/
├── __init__.py
├── nonprofit.py     # SQLAlchemy models
├── email.py
└── user.py

repositories/
├── __init__.py
├── nonprofit_repo.py
├── email_repo.py
└── base_repo.py

services/
├── __init__.py
├── nonprofit_service.py
├── email_service.py
└── template_service.py
```

### Stage 2: Async Email Processing (Week 2)
**Goal:** Implement background job processing

**Tech Stack:**
- **Job Queue:** Redis + RQ or Celery
- **Background Workers:** Separate processes
- **Email Service:** SendGrid/AWS SES integration

**Implementation:**
```python
# Background task
@app.post("/send-email")
async def send_email(request: EmailRequest, background_tasks: BackgroundTasks):
    # Validate recipients exist
    campaign = await create_email_campaign(request)
    
    # Queue background job
    background_tasks.add_task(process_email_campaign, campaign.id)
    
    return {"campaign_id": campaign.id, "status": "queued"}

# Monitor endpoint
@app.get("/campaigns/{campaign_id}/status")
async def get_campaign_status(campaign_id: str):
    return await get_campaign_progress(campaign_id)
```

### Stage 3: Production Features (Week 3)
**Goal:** Add authentication, rate limiting, monitoring

**Features:**
1. **JWT Authentication**
2. **Rate Limiting** (per user/IP)
3. **Structured Logging**
4. **Health Checks**
5. **Metrics/Monitoring**

### Stage 4: Performance Optimization (Week 4)
**Goal:** Handle high-scale scenarios

**Optimizations:**
1. **Database Indexing**
2. **Query Optimization**
3. **Caching Strategy** (Redis)
4. **Connection Pooling**
5. **Horizontal Scaling**

---

## Scalability Targets

### Current Capacity
- **Nonprofits:** ~1,000 (memory limit)
- **Concurrent Users:** 1 (single-threaded)
- **Email Throughput:** ~10/second (blocking)
- **Data Persistence:** None

### Target Capacity (Phase 1)
- **Nonprofits:** 100,000+
- **Concurrent Users:** 100+
- **Email Throughput:** 1,000/second
- **Data Persistence:** 99.9% reliability

### Enterprise Scale (Phase 2)
- **Nonprofits:** 1,000,000+
- **Concurrent Users:** 1,000+
- **Email Throughput:** 10,000/second
- **Multi-tenancy:** Support multiple foundations

---

## Common Interview Questions & Answers

### Q1: "How would you handle sending 100,000 emails?"
**Answer:**
1. **Queue the job** immediately, return 202 Accepted
2. **Batch processing** (1000 emails per batch)
3. **Rate limiting** to respect email service limits
4. **Progress tracking** with status updates
5. **Retry logic** for failed emails
6. **Dead letter queue** for permanently failed emails

### Q2: "What happens if your database goes down?"
**Answer:**
1. **Circuit breaker** pattern to detect failures
2. **Graceful degradation** (read-only mode)
3. **Database replication** (primary/replica setup)
4. **Connection pooling** with retry logic
5. **Health checks** to monitor database status

### Q3: "How do you prevent duplicate emails?"
**Answer:**
1. **Idempotency keys** in API requests
2. **Database constraints** (unique indexes)
3. **Deduplication** at campaign level
4. **Redis cache** for recent email tracking
5. **Request validation** before processing

### Q4: "How would you implement email templates?"
**Answer:**
1. **Template engine** (Jinja2)
2. **Template versioning** for A/B testing
3. **Variable validation** before sending
4. **Preview functionality** 
5. **Template library** with categories

### Q5: "How do you ensure email delivery?"
**Answer:**
1. **Webhook handling** for delivery status
2. **Bounce management** 
3. **Retry strategies** (exponential backoff)
4. **Email verification** before sending
5. **Delivery analytics** and reporting

---

## Performance Metrics to Track

### API Performance
- **Response times:** P50, P95, P99
- **Throughput:** Requests per second
- **Error rates:** 4xx, 5xx responses
- **Database query times**

### Email Performance
- **Queue depth:** Pending jobs
- **Processing rate:** Emails per second
- **Delivery rate:** Success percentage
- **Bounce rate:** Failed deliveries

### System Health
- **Memory usage:** Application memory
- **CPU utilization:** Server load
- **Database connections:** Pool usage
- **Disk space:** Storage usage

---

## Security Considerations

### Authentication & Authorization
```python
# JWT-based auth
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        token = request.headers.get("Authorization")
        if not verify_jwt_token(token):
            raise HTTPException(401, "Unauthorized")
    response = await call_next(request)
    return response
```

### Rate Limiting
```python
# Redis-based rate limiting
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host
    if await is_rate_limited(client_ip):
        raise HTTPException(429, "Too Many Requests")
    response = await call_next(request)
    return response
```

### Data Protection
- **Input validation** (Pydantic + custom validators)
- **SQL injection protection** (ORM parameterized queries)
- **Email address validation** (DNS verification)
- **Content sanitization** (XSS prevention)

This analysis should prepare you well for system design discussions in your interview! 🚀
