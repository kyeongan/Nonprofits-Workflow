# Scalable Implementation Examples

## Example 1: Database Layer with SQLAlchemy

### models/nonprofit.py

```python
from sqlalchemy import Column, String, Text, DateTime, UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
import uuid

Base = declarative_base()

class Nonprofit(Base):
    __tablename__ = "nonprofits"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    address = Column(Text, nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

class EmailCampaign(Base):
    __tablename__ = "email_campaigns"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    template = Column(Text, nullable=False)
    status = Column(String(50), default="draft")
    created_at = Column(DateTime, default=func.now())

class EmailSend(Base):
    __tablename__ = "email_sends"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    campaign_id = Column(UUID, nullable=False, index=True)
    nonprofit_id = Column(UUID, nullable=False)
    to_email = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    status = Column(String(50), default="pending", index=True)
    sent_at = Column(DateTime)
    created_at = Column(DateTime, default=func.now())
```

### repositories/nonprofit_repo.py

```python
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from models.nonprofit import Nonprofit

class NonprofitRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, nonprofit_data: dict) -> Nonprofit:
        nonprofit = Nonprofit(**nonprofit_data)
        self.db.add(nonprofit)
        await self.db.commit()
        await self.db.refresh(nonprofit)
        return nonprofit

    async def get_by_email(self, email: str) -> Optional[Nonprofit]:
        result = await self.db.execute(
            select(Nonprofit).where(Nonprofit.email == email)
        )
        return result.scalar_one_or_none()

    async def list_all(self, limit: int = 100, offset: int = 0) -> List[Nonprofit]:
        result = await self.db.execute(
            select(Nonprofit).limit(limit).offset(offset)
        )
        return result.scalars().all()

    async def search_by_domain(self, domain: str) -> List[Nonprofit]:
        result = await self.db.execute(
            select(Nonprofit).where(Nonprofit.email.like(f"%@{domain}"))
        )
        return result.scalars().all()
```

## Example 2: Async Email Service with Background Jobs

### services/email_service.py

```python
import asyncio
from typing import List
from datetime import datetime
from redis import Redis
from rq import Queue
from sqlalchemy.ext.asyncio import AsyncSession

from repositories.nonprofit_repo import NonprofitRepository
from repositories.email_repo import EmailRepository
from external.sendgrid_client import SendGridClient

class EmailService:
    def __init__(self, db: AsyncSession, redis_client: Redis):
        self.db = db
        self.nonprofit_repo = NonprofitRepository(db)
        self.email_repo = EmailRepository(db)
        self.queue = Queue(connection=redis_client)
        self.sendgrid = SendGridClient()

    async def create_campaign(self, template: str, email_addresses: List[str], cc_addresses: List[str] = None) -> str:
        """Create email campaign and queue for processing"""

        # Validate all nonprofits exist
        nonprofits = []
        for email in email_addresses + (cc_addresses or []):
            nonprofit = await self.nonprofit_repo.get_by_email(email)
            if not nonprofit:
                raise ValueError(f"Nonprofit with email {email} not found")
            nonprofits.append(nonprofit)

        # Create campaign
        campaign = await self.email_repo.create_campaign(template)

        # Queue individual email sends
        for nonprofit in nonprofits:
            is_cc = nonprofit.email in (cc_addresses or [])
            await self.email_repo.create_email_send(
                campaign_id=campaign.id,
                nonprofit_id=nonprofit.id,
                to_email=nonprofit.email,
                body=template.format(name=nonprofit.name, address=nonprofit.address),
                is_cc=is_cc
            )

        # Queue background job
        self.queue.enqueue(self.process_campaign, campaign.id)

        return str(campaign.id)

    def process_campaign(self, campaign_id: str):
        """Background job to process email campaign"""
        # This runs in a separate worker process
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._process_campaign_async(campaign_id))

    async def _process_campaign_async(self, campaign_id: str):
        """Async processing of email campaign"""
        pending_emails = await self.email_repo.get_pending_emails(campaign_id)

        # Process in batches to avoid overwhelming email service
        batch_size = 100
        for i in range(0, len(pending_emails), batch_size):
            batch = pending_emails[i:i + batch_size]
            await self._process_email_batch(batch)

            # Rate limiting - wait between batches
            await asyncio.sleep(1)

    async def _process_email_batch(self, emails: List):
        """Process a batch of emails"""
        tasks = []
        for email in emails:
            task = self._send_single_email(email)
            tasks.append(task)

        # Send all emails in batch concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Update status based on results
        for email, result in zip(emails, results):
            if isinstance(result, Exception):
                await self.email_repo.mark_failed(email.id, str(result))
            else:
                await self.email_repo.mark_sent(email.id)

    async def _send_single_email(self, email_record):
        """Send individual email with retry logic"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                await self.sendgrid.send_email(
                    to=email_record.to_email,
                    subject="Foundation Update",
                    body=email_record.body
                )
                return True
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
```

## Example 3: Refactored API Endpoints

### main_scalable.py

```python
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from redis import Redis
import structlog

from database import get_db_session, get_redis_client
from services.email_service import EmailService
from services.nonprofit_service import NonprofitService
from middleware.auth import verify_jwt_token
from middleware.rate_limit import rate_limit

logger = structlog.get_logger()

app = FastAPI(title="Scalable Nonprofits API", version="2.0.0")

# Dependency injection
async def get_email_service(
    db: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis_client)
) -> EmailService:
    return EmailService(db, redis)

async def get_nonprofit_service(
    db: AsyncSession = Depends(get_db_session)
) -> NonprofitService:
    return NonprofitService(db)

# Scalable endpoints
@app.post("/nonprofits")
async def create_nonprofit(
    nonprofit_data: NonprofitCreate,
    service: NonprofitService = Depends(get_nonprofit_service),
    user_id: str = Depends(verify_jwt_token)
):
    """Create a new nonprofit - now with auth and database persistence"""
    try:
        nonprofit = await service.create_nonprofit(nonprofit_data.dict())
        logger.info("nonprofit_created", nonprofit_id=nonprofit.id, user_id=user_id)
        return {"id": str(nonprofit.id), "message": "Nonprofit created successfully"}
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.post("/send-email")
@rate_limit(requests_per_minute=10)  # Rate limiting
async def send_email(
    request: EmailRequest,
    service: EmailService = Depends(get_email_service),
    user_id: str = Depends(verify_jwt_token)
):
    """Send templated email - now async with background processing"""
    try:
        campaign_id = await service.create_campaign(
            template=request.template,
            email_addresses=request.emails,
            cc_addresses=request.cc
        )

        logger.info("email_campaign_queued", campaign_id=campaign_id, user_id=user_id)

        return {
            "campaign_id": campaign_id,
            "status": "queued",
            "message": "Email campaign queued for processing"
        }
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.get("/campaigns/{campaign_id}/status")
async def get_campaign_status(
    campaign_id: str,
    service: EmailService = Depends(get_email_service),
    user_id: str = Depends(verify_jwt_token)
):
    """Monitor email campaign progress"""
    status = await service.get_campaign_status(campaign_id)
    return {
        "campaign_id": campaign_id,
        "status": status["status"],
        "total_emails": status["total"],
        "sent": status["sent"],
        "failed": status["failed"],
        "pending": status["pending"]
    }

@app.get("/nonprofits")
async def list_nonprofits(
    domain: str = None,
    limit: int = 100,
    offset: int = 0,
    service: NonprofitService = Depends(get_nonprofit_service),
    user_id: str = Depends(verify_jwt_token)
):
    """List nonprofits with pagination and filtering"""
    if domain:
        nonprofits = await service.search_by_domain(domain)
    else:
        nonprofits = await service.list_nonprofits(limit=limit, offset=offset)

    return {
        "nonprofits": [
            {
                "id": str(np.id),
                "name": np.name,
                "address": np.address,
                "email": np.email
            }
            for np in nonprofits
        ],
        "limit": limit,
        "offset": offset
    }

# Health check with detailed system status
@app.get("/health")
async def health_check(
    db: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis_client)
):
    """Comprehensive health check"""
    health_status = {"status": "healthy", "checks": {}}

    # Database check
    try:
        await db.execute("SELECT 1")
        health_status["checks"]["database"] = "healthy"
    except Exception as e:
        health_status["checks"]["database"] = f"unhealthy: {str(e)}"
        health_status["status"] = "unhealthy"

    # Redis check
    try:
        redis.ping()
        health_status["checks"]["redis"] = "healthy"
    except Exception as e:
        health_status["checks"]["redis"] = f"unhealthy: {str(e)}"
        health_status["status"] = "unhealthy"

    return health_status
```

## Example 4: Docker Configuration for Scalability

### docker-compose.yml

```yaml
version: "3.8"

services:
  # Main application
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/nonprofits
      - REDIS_URL=redis://redis:6379/0
      - SENDGRID_API_KEY=${SENDGRID_API_KEY}
    depends_on:
      - postgres
      - redis
    deploy:
      replicas: 3 # Horizontal scaling

  # Background workers
  worker:
    build: .
    command: python worker.py
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/nonprofits
      - REDIS_URL=redis://redis:6379/0
      - SENDGRID_API_KEY=${SENDGRID_API_KEY}
    depends_on:
      - postgres
      - redis
    deploy:
      replicas: 2 # Multiple workers

  # Database
  postgres:
    image: postgres:15
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
      - POSTGRES_DB=nonprofits
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  # Cache and job queue
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  # Load balancer
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    depends_on:
      - api

volumes:
  postgres_data:
```

## Example 5: Monitoring and Observability

### monitoring.py

```python
import structlog
import prometheus_client
from prometheus_client import Counter, Histogram, Gauge
import time

# Metrics
REQUEST_COUNT = Counter('api_requests_total', 'Total API requests', ['method', 'endpoint', 'status'])
REQUEST_DURATION = Histogram('api_request_duration_seconds', 'Request duration')
EMAIL_QUEUE_SIZE = Gauge('email_queue_size', 'Number of emails in queue')
ACTIVE_CAMPAIGNS = Gauge('active_campaigns_total', 'Number of active email campaigns')

class MonitoringMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            start_time = time.time()

            # Process request
            await self.app(scope, receive, send)

            # Record metrics
            duration = time.time() - start_time
            REQUEST_DURATION.observe(duration)

            method = scope["method"]
            path = scope["path"]
            # You'd extract status from response in real implementation
            REQUEST_COUNT.labels(method=method, endpoint=path, status="200").inc()

# Structured logging setup
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)
```

This demonstrates the key patterns you should know for your scalability interview! 🚀
