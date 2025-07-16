# System Design Interview - Quick Reference Guide

## 📋 Interview Structure (Typical 45-60 mins)

### Phase 1: Requirements Clarification (5-10 mins)

**Questions to Ask:**

- What's the expected scale? (users, emails/day, nonprofits)
- What are the SLA requirements? (latency, availability)
- Do we need real-time email sending or can it be async?
- What about email delivery guarantees?
- Any compliance requirements? (GDPR, CAN-SPAM)

### Phase 2: High-Level Design (10-15 mins)

**Components to Include:**

```
Client → Load Balancer → API Gateway → Services → Database
                            ↓
                       Message Queue → Workers → Email Service
```

### Phase 3: Deep Dive (20-30 mins)

**Focus Areas:**

- Database schema design
- API design and scaling
- Email processing pipeline
- Error handling and retries
- Monitoring and alerting

### Phase 4: Scale & Optimize (10-15 mins)

**Scaling Strategies:**

- Horizontal scaling
- Caching strategies
- Database sharding
- CDN for static content

---

## 🎯 Key System Design Principles

### 1. **Scalability**

```
Vertical Scaling (Scale Up)     →    Horizontal Scaling (Scale Out)
- Bigger servers                →    - More servers
- Limited by hardware           →    - Distributed system
- Single point of failure       →    - Fault tolerant
```

### 2. **Reliability**

```
Failure Points              →    Solutions
- Server crashes           →    - Health checks + auto-restart
- Database failures        →    - Replication + failover
- Network partitions       →    - Circuit breakers
- Email service outages    →    - Multiple providers
```

### 3. **Consistency**

```
Strong Consistency         →    Eventual Consistency
- ACID transactions       →    - BASE properties
- Immediate updates       →    - Async replication
- Performance cost        →    - Better availability
```

---

## 📊 Capacity Planning

### Current vs Target Scale

| Metric              | Current       | Target (1 year) | Enterprise (3 years) |
| ------------------- | ------------- | --------------- | -------------------- |
| **Nonprofits**      | 5 (hardcoded) | 100K            | 1M                   |
| **Users**           | 1             | 1K              | 10K                  |
| **Emails/day**      | 100           | 1M              | 10M                  |
| **Peak emails/sec** | 1             | 100             | 1000                 |
| **Storage**         | 0 (in-memory) | 100GB           | 1TB                  |
| **Availability**    | 90%           | 99.9%           | 99.99%               |

### Scaling Milestones

**Phase 1: MVP → 1K users**

- Single server deployment
- PostgreSQL database
- Background job processing
- Basic monitoring

**Phase 2: 1K → 10K users**

- Load balancer + multiple servers
- Database read replicas
- Redis caching
- Email rate limiting

**Phase 3: 10K → 100K users**

- Microservices architecture
- Database sharding
- Multiple data centers
- Advanced monitoring

---

## 🏗️ Architecture Patterns

### 1. **Monolith → Microservices Evolution**

**Monolith (Current)**

```
┌─────────────────────────────┐
│     Single FastAPI App      │
│  ┌─────────────────────────┐ │
│  │ Nonprofits + Email +    │ │
│  │ Users + Auth + Admin    │ │
│  └─────────────────────────┘ │
└─────────────────────────────┘
```

**Microservices (Target)**

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│    User     │  │ Nonprofit   │  │   Email     │
│   Service   │  │  Service    │  │  Service    │
│             │  │             │  │             │
│ Port: 8001  │  │ Port: 8002  │  │ Port: 8003  │
└─────────────┘  └─────────────┘  └─────────────┘
        ↓                ↓                ↓
┌─────────────────────────────────────────────────┐
│              API Gateway (8000)                 │
└─────────────────────────────────────────────────┘
```

### 2. **Database Architecture Evolution**

**Single Database (Current)**

```
App → PostgreSQL (All tables)
```

**Read Replicas (Phase 1)**

```
App → Primary DB (writes)
  ↓
  └→ Read Replica 1 (reads)
  └→ Read Replica 2 (reads)
```

**Sharded (Phase 2)**

```
App → Shard 1 (nonprofits A-H)
  ├→ Shard 2 (nonprofits I-P)
  └→ Shard 3 (nonprofits Q-Z)
```

### 3. **Email Processing Pipeline**

**Synchronous (Current Problem)**

```
API Request → Process Emails → Return Response
     (blocks for minutes with large batches)
```

**Asynchronous (Solution)**

```
API Request → Queue Job → Return Immediately
                 ↓
            Background Worker → Email Service
                 ↓
            Update Status → Webhook/Polling
```

---

## 🔧 Technology Stack Recommendations

### **Database Layer**

```
Primary:     PostgreSQL (ACID, complex queries)
Cache:       Redis (sessions, frequently accessed data)
Search:      Elasticsearch (full-text search on nonprofits)
Analytics:   ClickHouse (email delivery metrics)
```

### **Application Layer**

```
API:         FastAPI (async, type hints, auto docs)
Workers:     Celery with Redis (background jobs)
Gateway:     Kong/Traefik (rate limiting, auth)
```

### **Infrastructure**

```
Containers:  Docker + Kubernetes
Load Balancer: NGINX/HAProxy
Monitoring:  Prometheus + Grafana
Logging:     ELK Stack (Elasticsearch, Logstash, Kibana)
```

### **External Services**

```
Email:       SendGrid (primary), AWS SES (backup)
Storage:     AWS S3 (file attachments)
Auth:        Auth0 (OAuth, SAML)
```

---

## 🚨 Common Failure Scenarios & Solutions

### 1. **Email Service Outage**

**Problem:** SendGrid is down, emails can't be sent

**Solution:**

```python
class EmailProvider:
    def __init__(self):
        self.providers = [SendGridProvider(), SESProvider(), MailgunProvider()]
        self.current_provider = 0

    async def send_email(self, email_data):
        for attempt in range(len(self.providers)):
            try:
                provider = self.providers[self.current_provider]
                return await provider.send(email_data)
            except Exception as e:
                self.current_provider = (self.current_provider + 1) % len(self.providers)
                if attempt == len(self.providers) - 1:
                    raise e
```

### 2. **Database Connection Pool Exhaustion**

**Problem:** Too many concurrent requests, database connections exhausted

**Solution:**

```python
# Connection pooling configuration
DATABASE_URL = "postgresql://user:pass@localhost/db"
engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,           # Base connections
    max_overflow=30,        # Additional connections
    pool_pre_ping=True,     # Validate connections
    pool_recycle=3600       # Recycle every hour
)
```

### 3. **Memory Leak from Large Email Lists**

**Problem:** Processing 100K emails loads all data into memory

**Solution:**

```python
async def process_large_email_list(campaign_id: str):
    # Stream processing instead of loading all at once
    async for batch in stream_emails_by_campaign(campaign_id, batch_size=1000):
        await process_email_batch(batch)
        # Batch processed, memory freed
```

---

## 📈 Performance Optimization Techniques

### 1. **Database Optimization**

```sql
-- Indexes for fast lookups
CREATE INDEX idx_nonprofits_email ON nonprofits(email);
CREATE INDEX idx_email_sends_status ON email_sends(status);
CREATE INDEX idx_email_sends_campaign_status ON email_sends(campaign_id, status);

-- Partial indexes for specific queries
CREATE INDEX idx_pending_emails ON email_sends(created_at) WHERE status = 'pending';
```

### 2. **Caching Strategy**

```python
# Multi-level caching
class NonprofitService:
    def __init__(self, db, redis):
        self.db = db
        self.redis = redis
        self.local_cache = {}  # In-memory cache

    async def get_nonprofit(self, email: str):
        # L1: Local cache (fastest)
        if email in self.local_cache:
            return self.local_cache[email]

        # L2: Redis cache (fast)
        cached = await self.redis.get(f"nonprofit:{email}")
        if cached:
            nonprofit = json.loads(cached)
            self.local_cache[email] = nonprofit
            return nonprofit

        # L3: Database (slowest)
        nonprofit = await self.db.query(Nonprofit).filter_by(email=email).first()
        if nonprofit:
            await self.redis.setex(f"nonprofit:{email}", 3600, json.dumps(nonprofit))
            self.local_cache[email] = nonprofit

        return nonprofit
```

### 3. **Rate Limiting Implementation**

```python
class RateLimiter:
    def __init__(self, redis):
        self.redis = redis

    async def is_allowed(self, key: str, limit: int, window: int) -> bool:
        """Sliding window rate limiter"""
        now = time.time()
        pipe = self.redis.pipeline()

        # Remove old entries
        pipe.zremrangebyscore(key, 0, now - window)

        # Count current entries
        pipe.zcard(key)

        # Add current request
        pipe.zadd(key, {str(uuid.uuid4()): now})

        # Set expiry
        pipe.expire(key, window)

        results = await pipe.execute()
        request_count = results[1]

        return request_count < limit
```

---

## 🎤 Mock Interview Questions & Answers

### Q: "Design a system to send 1 million emails per day"

**Answer Framework:**

1. **Clarify Requirements**

   - Peak load: ~12 emails/second average, 100+ emails/second peak
   - Delivery time: Can be async (minutes acceptable)
   - Reliability: Must track success/failure

2. **High-Level Design**

   ```
   API → Queue → Workers → Email Service
     ↓      ↓       ↓         ↓
   Return  Redis  Celery  SendGrid/SES
   202     Queue  Workers  (rate limited)
   ```

3. **Deep Dive**

   - **Queuing:** Redis with job priorities
   - **Workers:** Multiple Celery workers with retry logic
   - **Rate Limiting:** Respect email provider limits (SendGrid: 600 emails/second)
   - **Monitoring:** Track queue depth, processing rate, failure rate

4. **Scaling**
   - **Horizontal:** Add more worker processes
   - **Vertical:** Upgrade worker server specs
   - **Provider:** Multiple email service providers

### Q: "How do you handle email failures and retries?"

**Answer:**

```python
@celery.task(bind=True, max_retries=3)
def send_email_task(self, email_data):
    try:
        send_email_via_provider(email_data)
        mark_email_sent(email_data['id'])
    except TemporaryFailure as e:
        # Retry with exponential backoff
        raise self.retry(countdown=2 ** self.request.retries, exc=e)
    except PermanentFailure as e:
        # Don't retry, mark as failed
        mark_email_failed(email_data['id'], str(e))
    except Exception as e:
        # Unknown error, retry once then fail
        if self.request.retries >= 1:
            mark_email_failed(email_data['id'], str(e))
        else:
            raise self.retry(countdown=60, exc=e)
```

### Q: "How do you ensure no duplicate emails are sent?"

**Answer:**

1. **Idempotency Keys:** Client provides unique key per request
2. **Database Constraints:** Unique index on (campaign_id, nonprofit_id)
3. **Redis Deduplication:** Check recent sends before queuing
4. **Request Validation:** Prevent duplicate campaigns

```python
async def create_email_campaign(self, template: str, emails: List[str], idempotency_key: str):
    # Check if already processed
    existing = await self.redis.get(f"campaign:{idempotency_key}")
    if existing:
        return json.loads(existing)

    # Create campaign
    campaign = await self.db.create_campaign(template, emails)

    # Cache result
    await self.redis.setex(f"campaign:{idempotency_key}", 3600, json.dumps(campaign))

    return campaign
```

---

This should give you a comprehensive foundation for your system design interview! Focus on understanding the trade-offs and being able to explain your decisions. Good luck! 🚀
