# AI Endpoint Rate Limiting

## Overview

AI endpoints are protected with tier-based rate limiting to prevent abuse and manage costs. Rate limits are applied per user per hour and vary based on subscription tier.

**Date Implemented:** October 15, 2025
**Phase:** Backend Phase 1, Week 2, Task 2.3

---

## Rate Limits by Tier

| Subscription Tier | Requests per Hour | Cost Protection |
|-------------------|-------------------|-----------------|
| **Free / Default** | 10 | Basic protection |
| **Pro** | 50 | Moderate usage |
| **Enterprise** | 200 | High volume |

---

## Protected Endpoints

### 1. Content Generation
**Endpoint:** `POST /api/v1/content/generate`

Generates AI-powered content using LangGraph workflows.

**Rate Limit Applied:** `ai_content_generation_rate_limit()`

**Example Usage:**
```python
from src.api.middleware.rate_limiter import ai_content_generation_rate_limit

@router.post("/generate")
async def generate_content(
    _rate_limit: None = Depends(ai_content_generation_rate_limit())
):
    # Endpoint logic...
```

### 2. Topic Generation
**Endpoint:** `POST /api/v1/topic/generate-topic`

Generates content topic ideas using AI models.

**Rate Limit Applied:** `ai_topic_generation_rate_limit()`

**Example Usage:**
```python
from src.api.middleware.rate_limiter import ai_topic_generation_rate_limit

@router.post("/generate-topic")
async def generate_topic(
    _rate_limit: None = Depends(ai_topic_generation_rate_limit())
):
    # Endpoint logic...
```

### 3. Knowledge Processing (Future)
**Endpoint:** `POST /api/v1/knowledge/process`

Processes knowledge base items with AI.

**Rate Limit Applied:** `ai_knowledge_processing_rate_limit()`

---

## How It Works

### 1. Tier Detection

When a request arrives, the rate limiter:
1. Identifies the authenticated user
2. Queries the database for active subscription
3. Determines subscription plan (Free, Pro, Enterprise)
4. Maps plan to tier limits

```python
def _get_user_tier(self, db: Session, user_id: str) -> str:
    """Get user's subscription tier."""
    subscription = db.query(UserSubscription).filter(
        UserSubscription.user_id == user_id,
        UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL])
    ).first()

    if not subscription:
        return "default"  # No subscription = free tier limits

    # Map plan name to tier limits
    # ...
```

### 2. Request Tracking

The limiter uses a **sliding window algorithm**:
- Stores timestamps of recent requests in memory
- Removes timestamps older than 1 hour
- Counts remaining requests in window
- Allows or blocks based on tier limit

```python
# Storage structure: {client_key: deque([timestamp1, timestamp2, ...])}
client_key = f"ai:{user_id}:{tier}"
timestamps = self.storage[client_key]

# Remove old timestamps (older than 1 hour)
cutoff = now - timedelta(seconds=3600)
while timestamps and timestamps[0] < cutoff:
    timestamps.popleft()

# Check limit
if len(timestamps) >= max_requests:
    raise HTTPException(status_code=429, detail="Rate limit exceeded")
```

### 3. Response Headers

When rate limit is exceeded, the response includes:

**429 Too Many Requests**
```http
Status: 429 Too Many Requests
Retry-After: 3456
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 3456
X-RateLimit-Tier: free
```

**Headers:**
- `Retry-After`: Seconds until oldest request expires
- `X-RateLimit-Limit`: Maximum requests allowed in window
- `X-RateLimit-Remaining`: Requests remaining in current window
- `X-RateLimit-Reset`: Seconds until limit resets
- `X-RateLimit-Tier`: User's subscription tier

**Error Message:**
```json
{
  "detail": "AI content generation rate limit exceeded (10/10 per hour for free tier). Try again in 3456 seconds. Upgrade your plan for higher limits."
}
```

---

## Implementation Details

### Class: `AIEndpointRateLimiter`

```python
class AIEndpointRateLimiter:
    """
    Rate limiter for expensive AI operations with subscription tier awareness.

    Applies different rate limits based on user's subscription plan:
    - Free tier: 10 requests/hour
    - Pro tier: 50 requests/hour
    - Enterprise tier: 200 requests/hour
    """

    TIER_LIMITS = {
        "free": 10,
        "pro": 50,
        "enterprise": 200,
        "default": 10
    }

    def __init__(self, custom_limits: Optional[dict] = None, description: str = "AI operation"):
        self.limits = custom_limits or self.TIER_LIMITS
        self.description = description
        self.window_seconds = 3600  # 1 hour
        self.storage: Dict[str, deque] = defaultdict(deque)
```

### Factory Functions

```python
def ai_content_generation_rate_limit():
    """Rate limiter for AI content generation endpoint."""
    return AIEndpointRateLimiter(description="content generation")

def ai_topic_generation_rate_limit():
    """Rate limiter for AI topic generation endpoint."""
    return AIEndpointRateLimiter(description="topic generation")

def ai_knowledge_processing_rate_limit():
    """Rate limiter for AI knowledge base processing endpoint."""
    return AIEndpointRateLimiter(description="knowledge processing")
```

---

## Custom Limits

You can create custom rate limiters with different tier limits:

```python
custom_limiter = AIEndpointRateLimiter(
    custom_limits={
        "free": 5,
        "pro": 25,
        "enterprise": 100,
        "default": 5
    },
    description="expensive AI operation"
)
```

---

## Storage & Scalability

### Current Implementation (In-Memory)

**Pros:**
- Fast lookups
- No external dependencies
- Simple implementation

**Cons:**
- Not shared across server instances
- Lost on server restart
- Memory usage grows with active users

### Production Recommendation (Redis)

For distributed deployments, migrate to Redis-backed storage:

```python
# Future implementation with Redis
import redis

redis_client = redis.Redis(host='localhost', port=6379, db=0)

def check_rate_limit(user_id: str, tier: str, max_requests: int):
    key = f"ai:{user_id}:{tier}"

    # Increment counter
    count = redis_client.incr(key)

    # Set expiration on first request
    if count == 1:
        redis_client.expire(key, 3600)  # 1 hour

    # Check limit
    if count > max_requests:
        ttl = redis_client.ttl(key)
        raise HTTPException(status_code=429, detail=f"Retry after {ttl}s")
```

---

## Testing

### Unit Tests

Located at: `tests/middleware/test_ai_rate_limiter.py`

**Test Coverage:**
- ✅ Initialization with default limits
- ✅ Initialization with custom limits
- ✅ Free tier limit enforcement (10/hour)
- ✅ Pro tier limit enforcement (50/hour)
- ✅ Enterprise tier limit enforcement (200/hour)
- ✅ Retry-After header inclusion
- ✅ Rate limit headers (X-RateLimit-*)
- ✅ Time window reset after 1 hour
- ✅ Separate limits for different users
- ✅ Tier detection logic (free, pro, enterprise, default)
- ✅ Trial subscription tier handling

**Run Tests:**
```bash
pytest tests/middleware/test_ai_rate_limiter.py -v
```

### Manual Testing

**Test Free Tier Limit:**
```bash
# Make 11 requests as a free tier user
for i in {1..11}; do
  echo "Request $i"
  curl -X POST http://localhost:8000/api/v1/content/generate \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"content_id": "test-123"}'
done
```

Expected: First 10 succeed, 11th returns 429.

**Test Pro Tier Limit:**
```bash
# Make 51 requests as a pro tier user
for i in {1..51}; do
  echo "Request $i"
  curl -X POST http://localhost:8000/api/v1/content/generate \
    -H "Authorization: Bearer $PRO_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"content_id": "test-456"}'
done
```

Expected: First 50 succeed, 51st returns 429.

---

## Monitoring

### Recommended Metrics

1. **Rate Limit Violations per Tier**
   - Track how many users hit limits
   - Identify if limits are too restrictive

2. **AI Request Volume per Tier**
   - Monitor usage patterns
   - Inform pricing decisions

3. **Average Requests per User**
   - Detect outliers
   - Identify potential abuse

### Logging

Rate limit events are logged:

**Allowed Request:**
```
INFO: AI rate limit check passed for user user-123 (tier: free): 5/10 used
```

**Blocked Request:**
```
WARNING: AI rate limit exceeded for user user-456 (tier: free): 10/10 in 3600s
```

---

## Upgrade Messaging

When users hit rate limits, they receive upgrade prompts:

```
AI content generation rate limit exceeded (10/10 per hour for free tier).
Try again in 3456 seconds. Upgrade your plan for higher limits.
```

**Frontend Integration:**
- Detect 429 status code
- Display user-friendly error message
- Show "Upgrade Plan" call-to-action
- Display retry timer

---

## Configuration

### Environment Variables

No environment variables needed. Rate limits are hardcoded in:

```python
TIER_LIMITS = {
    "free": 10,
    "pro": 50,
    "enterprise": 200,
    "default": 10
}
```

### Changing Limits

To adjust limits, edit `src/api/middleware/rate_limiter.py`:

```python
class AIEndpointRateLimiter:
    TIER_LIMITS = {
        "free": 15,        # Increased from 10
        "pro": 75,         # Increased from 50
        "enterprise": 300, # Increased from 200
        "default": 15
    }
```

---

## Security Considerations

1. **User ID-Based Tracking**
   - Rate limits tied to authenticated user ID
   - Prevents IP-based circumvention
   - Requires authentication

2. **Tier Detection**
   - Queries database for current subscription
   - Uses active or trial subscriptions
   - Falls back to "default" for unauthenticated

3. **Time Window**
   - Sliding 1-hour window
   - Old requests automatically expire
   - No manual reset needed

4. **DoS Protection**
   - Limits expensive AI operations
   - Reduces cost exposure
   - Protects infrastructure

---

## Future Enhancements

### Phase 2 Improvements

1. **Redis Storage**
   - Shared across server instances
   - Persistent across restarts
   - Better scalability

2. **Dynamic Limits**
   - Load from database
   - Configure per-customer limits
   - Admin UI for adjustments

3. **Grace Period**
   - Allow burst above limit
   - Smooth user experience
   - Prevent harsh blocks

4. **Cost Tracking**
   - Log API costs per request
   - Track spending per user
   - Generate cost reports

5. **Smart Throttling**
   - Gradually slow responses near limit
   - Prevent hard 429 errors
   - Better UX

---

## Troubleshooting

### Issue: User complains about rate limit but should have higher tier

**Diagnosis:**
1. Check user's subscription status in database:
   ```sql
   SELECT * FROM user_subscriptions WHERE user_id = 'user-123';
   ```
2. Check subscription plan:
   ```sql
   SELECT * FROM subscription_plans WHERE id = 'plan-id';
   ```
3. Verify plan name matches tier mapping in code

**Solution:**
- Ensure subscription status is ACTIVE or TRIAL
- Verify plan name contains "free", "pro", or "enterprise"
- Check plan_id is correctly linked

### Issue: Rate limit not resetting after 1 hour

**Diagnosis:**
1. Check server time: `date -u`
2. Verify timezone is UTC
3. Check storage timestamps

**Solution:**
- Restart application (clears in-memory storage)
- Implement Redis for persistent storage
- Verify server system time is correct

### Issue: Rate limits too restrictive for production

**Diagnosis:**
- Monitor rate limit violations
- Analyze usage patterns
- Check customer feedback

**Solution:**
- Increase tier limits in code
- Deploy updated limits
- Communicate changes to users

---

## Related Documentation

- [Usage Limiter](../usage-limiter.md) - Subscription-based resource limits
- [General Rate Limiter](../rate-limiter.md) - IP-based API rate limiting
- [Subscription Plans](../subscriptions/plans.md) - Subscription tier details

---

**Last Updated:** October 15, 2025
**Owner:** Backend Team
**Status:** ✅ Implemented and Tested
