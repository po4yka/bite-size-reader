# Phase 2: Schema Integrity Improvements

## Overview

Phase 2 adds critical data integrity constraints to prevent common data quality issues:

1. **NOT NULL constraint** on `LLMCall.request_id` - Prevents orphaned LLM calls
2. **CHECK constraints** via triggers - Validates request types have required fields
3. **CASCADE DELETE** - Automatically cleans up related records

## Changes Made

### 1. LLMCall.request NOT NULL

**Before:**
```python
class LLMCall(BaseModel):
    request = peewee.ForeignKeyField(
        Request, backref="llm_calls", null=True, on_delete="SET NULL"
    )
```

**After:**
```python
class LLMCall(BaseModel):
    request = peewee.ForeignKeyField(
        Request, backref="llm_calls", null=False, on_delete="CASCADE"
    )  # Phase 2: Made NOT NULL for data integrity
```

**Benefits:**
- ✅ Every LLM call is traceable to a request
- ✅ No orphaned LLM calls in the database
- ✅ Clearer debugging with complete request context
- ✅ CASCADE DELETE prevents orphans when requests are deleted

### 2. Request Type Validation

Added CHECK constraints via triggers to validate:

**URL Requests:**
- MUST have `normalized_url`
- Example: `type='url'` requires `normalized_url IS NOT NULL`

**Forward Requests:**
- MUST have `fwd_from_chat_id` AND `fwd_from_msg_id`
- Example: `type='forward'` requires both fields to be NOT NULL

**Implementation:**
```sql
CREATE TRIGGER validate_request_insert
BEFORE INSERT ON requests
WHEN (
    (NEW.type = 'url' AND NEW.normalized_url IS NULL)
    OR (NEW.type = 'forward' AND (NEW.fwd_from_chat_id IS NULL OR NEW.fwd_from_msg_id IS NULL))
)
BEGIN
    SELECT RAISE(ABORT, 'Request validation failed: ...');
END;
```

**Benefits:**
- ✅ Data quality enforced at database level
- ✅ Invalid requests rejected immediately
- ✅ Clear error messages for developers
- ✅ Works across all code paths (ORM, raw SQL, migrations)

## Migration Details

**Migration File:** `app/cli/migrations/002_add_schema_constraints.py`

### Steps Performed

1. **Cleanup Phase** - Remove any orphaned LLM calls
   - Count orphans: `SELECT COUNT(*) WHERE request_id IS NULL`
   - Delete orphans: `DELETE WHERE request_id IS NULL`

2. **Table Recreation** - Rebuild `llm_calls` with NOT NULL constraint
   - Create `llm_calls_new` with NOT NULL on `request_id`
   - Copy data: `INSERT INTO llm_calls_new SELECT * FROM llm_calls`
   - Drop old table: `DROP TABLE llm_calls`
   - Rename: `ALTER TABLE llm_calls_new RENAME TO llm_calls`
   - Recreate indexes (4 indexes)

3. **Trigger Creation** - Add validation triggers
   - `validate_request_insert` - Validate on INSERT
   - `validate_request_update` - Validate on UPDATE

### Rollback Support

The migration includes a `downgrade()` function that:
- Removes validation triggers
- Recreates `llm_calls` table with nullable `request_id`
- Restores original schema

**To rollback:**
```bash
python -m app.cli.migrations.migration_runner rollback 002_add_schema_constraints
```

## Testing

**Test File:** `test_phase2_simple.py`

### Test Coverage

1. ✅ NOT NULL constraint rejects NULL `request_id`
2. ✅ URL requests without `normalized_url` are rejected
3. ✅ Forward requests without `fwd_from_chat_id` are rejected
4. ✅ Forward requests without `fwd_from_msg_id` are rejected
5. ✅ Valid URL requests are accepted
6. ✅ Valid forward requests are accepted
7. ✅ CASCADE DELETE removes LLM calls when request is deleted

**Run tests:**
```bash
python test_phase2_simple.py
```

## Impact Assessment

### Before Phase 2

**Problems:**
- ❌ Orphaned LLM calls possible (no request reference)
- ❌ URL requests could exist without URLs
- ❌ Forward requests could exist without message references
- ❌ Difficult to debug missing request context
- ❌ Deleting requests left orphaned LLM calls

### After Phase 2

**Solutions:**
- ✅ All LLM calls must have a request
- ✅ All URL requests must have a normalized_url
- ✅ All forward requests must have complete metadata
- ✅ Clear validation errors guide developers
- ✅ CASCADE DELETE automatically cleans up related records

### Performance Impact

**Minimal:**
- Triggers add microseconds to INSERT/UPDATE operations
- CHECK constraints evaluated before write (fast)
- Indexes recreated during migration (one-time cost)
- No impact on SELECT queries

## Usage Examples

### Creating Valid Records

```python
from app.db.models import User, Request, LLMCall

# Create user
user = User.create(
    telegram_user_id=123456789,
    username='testuser',
    is_owner=True
)

# Valid URL request
url_request = Request.create(
    type='url',
    status='ok',
    correlation_id='unique-id',
    user_id=user.telegram_user_id,
    normalized_url='https://example.com'  # Required!
)

# Valid LLM call
llm_call = LLMCall.create(
    request=url_request,  # Required! Cannot be None
    provider='openrouter',
    model='qwen/qwen3-max',
    status='ok'
)

# Valid forward request
fwd_request = Request.create(
    type='forward',
    status='ok',
    correlation_id='unique-id-2',
    user_id=user.telegram_user_id,
    fwd_from_chat_id=-100123456789,  # Required!
    fwd_from_msg_id=999               # Required!
)
```

### What No Longer Works

```python
# ❌ This will fail: URL request without normalized_url
Request.create(
    type='url',
    status='ok',
    correlation_id='bad',
    user_id=123456789
    # Missing normalized_url!
)
# Error: Request validation failed: URL requests must have normalized_url

# ❌ This will fail: LLM call without request
LLMCall.create(
    request=None,  # Not allowed!
    provider='openrouter',
    model='qwen/qwen3-max'
)
# Error: NOT NULL constraint failed: llm_calls.request_id

# ❌ This will fail: Forward request without fwd_from_chat_id
Request.create(
    type='forward',
    status='ok',
    correlation_id='bad-forward',
    user_id=123456789,
    fwd_from_msg_id=999
    # Missing fwd_from_chat_id!
)
# Error: Request validation failed: forward requests must have fwd_from_chat_id and fwd_from_msg_id
```

## Migration Status

Check migration status:
```bash
python -m app.cli.migrations.migration_runner status
```

Expected output:
```
Migration Status:
  Total: 2
  Applied: 2
  Pending: 0

Migrations:
  ✓ 001_add_performance_indexes (applied 2025-11-15 08:32:49)
  ✓ 002_add_schema_constraints (applied 2025-11-15 08:45:12)
```

## Troubleshooting

### Migration Fails: "Orphaned LLM calls found"

**Problem:** Existing orphaned LLM calls in database

**Solution:** The migration automatically cleans them up. Check logs for count.

### INSERT fails: "NOT NULL constraint failed"

**Problem:** Trying to insert LLM call without request

**Solution:** Always provide a valid request reference:
```python
llm_call = LLMCall.create(request=my_request, ...)
```

### INSERT fails: "Request validation failed"

**Problem:** Request missing required fields for its type

**Solutions:**
- For URL requests: Add `normalized_url`
- For forward requests: Add both `fwd_from_chat_id` and `fwd_from_msg_id`

### CASCADE DELETE unexpected

**Problem:** LLM calls deleted when request is deleted

**Solution:** This is by design! To keep LLM calls, don't delete the request.

## Next Steps

### Phase 3: Performance (Optional)
- Add query result caching
- Implement batch operations
- Add database health checks

### Phase 4: Lifecycle Management (Future)
- Implement data archival
- Add automated VACUUM tasks
- Create monitoring dashboard

## References

- Main improvements doc: `docs/database_improvements.md`
- Migration file: `app/cli/migrations/002_add_schema_constraints.py`
- Test file: `test_phase2_simple.py`
- Model definitions: `app/db/models.py`

---

**Document Version:** 1.0
**Last Updated:** 2025-11-15
**Migration:** 002_add_schema_constraints
**Status:** ✅ Completed and Tested
