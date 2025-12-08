# gRPC Processing Service Documentation

## Overview
The `ProcessingService` provides a real-time, streaming interface for submitting and tracking article processing requests. It allows clients to submit a URL and receive a stream of status updates as the backend processes the content (extraction, summarization, etc.).

**Package:** `processing.v1`

---

## Service: `ProcessingService`

### RPC: `SubmitUrl`
Submits a URL for processing and returns a server-side stream of `ProcessingUpdate` messages.

**Signature:**
```protobuf
rpc SubmitUrl (SubmitUrlRequest) returns (stream ProcessingUpdate);
```

#### Request: `SubmitUrlRequest`
| Field | Type | Description |
|---|---|---|
| `url` | `string` | The URL of the article to process. Required. |
| `language` | `string` | Target language code (e.g., "en", "ru", "auto"). Optional. |
| `force_refresh` | `bool` | If `true`, forces re-processing even if the URL has been processed before. |

#### Response Stream: `ProcessingUpdate`
The server streams these messages to report progress.

| Field | Type | Description |
|---|---|---|
| `request_id` | `int64` | unique ID of the request. |
| `status` | `ProcessingStatus` | Current overall status (see Enum). |
| `stage` | `ProcessingStage` | Current processing stage (see Enum). |
| `message` | `string` | Human-readable log message or error description. |
| `progress` | `float` | Estimated progress from 0.0 to 1.0. |
| `summary_id` | `int64` | ID of the generated summary (populated when `status` is `COMPLETED`). |
| `error` | `string` | Detailed error message if `status` is `FAILED`. |

---

## Enums

### `ProcessingStatus`
Represents the overall state of the request.

| Name | Value | Description |
|---|---|---|
| `ProcessingStatus_UNSPECIFIED` | 0 | Default/Unknown state. |
| `ProcessingStatus_PENDING` | 1 | Request accepted, waiting to start. |
| `ProcessingStatus_PROCESSING` | 2 | Currently running. |
| `ProcessingStatus_COMPLETED` | 3 | Successfully finished. |
| `ProcessingStatus_FAILED` | 4 | Failed to complete. |

### `ProcessingStage`
Represents the specific step currently being executed.

| Name | Value | Description |
|---|---|---|
| `ProcessingStage_UNSPECIFIED` | 0 | Default/Unknown stage. |
| `ProcessingStage_QUEUED` | 1 | Waiting in queue. |
| `ProcessingStage_EXTRACTION` | 2 | Extracting content from the URL (Firecrawl). |
| `ProcessingStage_SUMMARIZATION` | 3 | Generating summary (LLM). |
| `ProcessingStage_SAVING` | 4 | Saving results to database. |
| `ProcessingStage_DONE` | 5 | All steps finished. |

---

## Usage Example (Python)

```python
import grpc
from app.protos import processing_pb2, processing_pb2_grpc

async with grpc.aio.insecure_channel('localhost:50051') as channel:
    stub = processing_pb2_grpc.ProcessingServiceStub(channel)
    request = processing_pb2.SubmitUrlRequest(url="https://example.com")

    async for update in stub.SubmitUrl(request):
        print(f"Status: {update.status}, Progress: {update.progress}")
```
