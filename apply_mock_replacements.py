file_path = "tests/test_openrouter_compliance.py"

# Read the original content
with open(file_path) as f:
    content = f.read()

replacements = []

# test_correct_api_endpoint
replacements.append(
    (
        """                mock_response = Mock(); mock_response.headers = {}; mock_response.content = b"{}"; mock_response.text = "{}"; mock_response.history = []
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "choices": [{"message": {"content": "Test response"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                }""",
        """                mock_response = FakeResponse(
                    status_code=200,
                    json_data={
                        "choices": [{"message": {"content": "Test response"}}],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                    }
                )""",
    )
)

# test_authentication_header
replacements.append(
    (
        """                mock_response = Mock(); mock_response.headers = {}; mock_response.content = b"{}"; mock_response.text = "{}"; mock_response.history = []
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "choices": [{"message": {"content": "Test response"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                }""",
        """                mock_response = FakeResponse(
                    status_code=200,
                    json_data={
                        "choices": [{"message": {"content": "Test response"}}],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                    }
                )""",
    )
)

# test_request_structure
replacements.append(
    (
        """                mock_response = Mock(); mock_response.headers = {}; mock_response.content = b"{}"; mock_response.text = "{}"; mock_response.history = []
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "choices": [{"message": {"content": "Test response"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                }""",
        """                mock_response = FakeResponse(
                    status_code=200,
                    json_data={
                        "choices": [{"message": {"content": "Test response"}}],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                    }
                )""",
    )
)

# test_optional_parameters
replacements.append(
    (
        """                mock_response = Mock(); mock_response.headers = {}; mock_response.content = b"{}"; mock_response.text = "{}"; mock_response.history = []
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "choices": [{"message": {"content": "Test response"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                }""",
        """                mock_response = FakeResponse(
                    status_code=200,
                    json_data={
                        "choices": [{"message": {"content": "Test response"}}],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                    }
                )""",
    )
)

# test_http_headers
replacements.append(
    (
        """                mock_response = Mock(); mock_response.headers = {}; mock_response.content = b"{}"; mock_response.text = "{}"; mock_response.history = []
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "choices": [{"message": {"content": "Test response"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                }""",
        """                mock_response = FakeResponse(
                    status_code=200,
                    json_data={
                        "choices": [{"message": {"content": "Test response"}}],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                    }
                )""",
    )
)

# test_error_handling_400
replacements.append(
    (
        """                mock_response = Mock(); mock_response.headers = {}; mock_response.content = b"{}"; mock_response.text = "{}"; mock_response.history = []
                mock_response.status_code = 400
                mock_response.json.return_value = {
                    "error": {"message": "Invalid request parameters"}
                }""",
        """                mock_response = FakeResponse(
                    status_code=400,
                    json_data={
                        "error": {"message": "Invalid request parameters"}
                    }
                )""",
    )
)

# test_error_handling_401
replacements.append(
    (
        """                mock_response = Mock(); mock_response.headers = {}; mock_response.content = b"{}"; mock_response.text = "{}"; mock_response.history = []
                mock_response.status_code = 401
                mock_response.json.return_value = {"error": {"message": "Invalid API key"}}""",
        """                mock_response = FakeResponse(
                    status_code=401,
                    json_data={"error": {"message": "Invalid API key"}}
                )""",
    )
)

# test_error_handling_402
replacements.append(
    (
        """                mock_response = Mock(); mock_response.headers = {}; mock_response.content = b"{}"; mock_response.text = "{}"; mock_response.history = []
                mock_response.status_code = 402
                mock_response.json.return_value = {"error": {"message": "Insufficient credits"}}""",
        """                mock_response = FakeResponse(
                    status_code=402,
                    json_data={"error": {"message": "Insufficient credits"}}
                )""",
    )
)

# test_error_handling_404
replacements.append(
    (
        """                mock_response = Mock(); mock_response.headers = {}; mock_response.content = b"{}"; mock_response.text = "{}"; mock_response.history = []
                mock_response.status_code = 404
                mock_response.json.return_value = {"error": {"message": "Model not found"}}""",
        """                mock_response = FakeResponse(
                    status_code=404,
                    json_data={"error": {"message": "Model not found"}}
                )""",
    )
)

# test_error_handling_429_with_retry_after
replacements.append(
    (
        """                mock_response = Mock(); mock_response.headers = {}; mock_response.content = b"{}"; mock_response.text = "{}"; mock_response.history = []
                mock_response.status_code = 429
                mock_response.headers = {"retry-after": "5"}
                mock_response.json.return_value = {"error": {"message": "Rate limit exceeded"}}""",
        """                mock_response = FakeResponse(
                    status_code=429,
                    json_data={"error": {"message": "Rate limit exceeded"}},
                    headers={"retry-after": "5"}
                )""",
    )
)

# test_error_handling_500
replacements.append(
    (
        """                mock_response = Mock(); mock_response.headers = {}; mock_response.content = b"{}"; mock_response.text = "{}"; mock_response.history = []
                mock_response.status_code = 500
                mock_response.json.return_value = {"error": {"message": "Internal server error"}}""",
        """                mock_response = FakeResponse(
                    status_code=500,
                    json_data={"error": {"message": "Internal server error"}}
                )""",
    )
)

# test_success_response_parsing
replacements.append(
    (
        """                mock_response = Mock(); mock_response.headers = {}; mock_response.content = b"{}"; mock_response.text = "{}"; mock_response.history = []
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "choices": [{"message": {"content": "Test response"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                    "model": "deepseek/deepseek-v3-0324",
                }""",
        """                mock_response = FakeResponse(
                    status_code=200,
                    json_data={
                        "choices": [{"message": {"content": "Test response"}}],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                        "model": "deepseek/deepseek-v3-0324",
                    }
                )""",
    )
)

# test_structured_output_content_with_json_part
replacements.append(
    (
        """                mock_response = Mock(); mock_response.headers = {}; mock_response.content = b"{}"; mock_response.text = "{}"; mock_response.history = []
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "id": "test-response",
                    "model": "qwen/qwen3-max",
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "total_tokens": 15,
                    },
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": [
                                    {"type": "reasoning", "text": "Planning structured output"},
                                    {"type": "output_json", "json": {"summary_250": "Short summary", "summary_1000": "Medium summary", "tldr": "Longer summary"}},
                                ],
                            },
                            "finish_reason": "stop",
                            "native_finish_reason": "completed",
                        }
                    ],
                }""",
        """                mock_response = FakeResponse(
                    status_code=200,
                    json_data={
                        "id": "test-response",
                        "model": "qwen/qwen3-max",
                        "usage": {
                            "prompt_tokens": 10,
                            "completion_tokens": 5,
                            "total_tokens": 15,
                        },
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": [
                                        {"type": "reasoning", "text": "Planning structured output"},
                                        {"type": "output_json", "json": {"summary_250": "Short summary", "summary_1000": "Medium summary", "tldr": "Longer summary"}},
                                    ],
                                },
                                "finish_reason": "stop",
                                "native_finish_reason": "completed",
                            }
                        ],
                    }
                )""",
    )
)

# test_models_endpoint
replacements.append(
    (
        """                mock_response = Mock(); mock_response.headers = {}; mock_response.content = b"{}"; mock_response.text = "{}"; mock_response.history = []
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "data": [
                        {"id": "deepseek/deepseek-v3-0324", "name": "DeepSeek V3"},
                        {"id": "google/gemini-2.5-pro", "name": "Gemini 2.5 Pro"},
                    ]
                }
                mock_response.raise_for_status = Mock()""",
        """                mock_response = FakeResponse(
                    status_code=200,
                    json_data={
                        "data": [
                            {"id": "deepseek/deepseek-v3-0324", "name": "DeepSeek V3"},
                            {"id": "google/gemini-2.5-pro", "name": "Gemini 2.5 Pro"},
                        ]
                    }
                )
                mock_response.raise_for_status = Mock()""",
    )
)

# test_fallback_models (This one is different, using side_effect with multiple Mocks.)
# It requires replacing Mock() instances within the list.
# This replacement will be more complex and might need separate handling or a more specific pattern.
replacements.append(
    (
        """                    Mock(status_code=500, json=Mock(return_value={"error": "Server error"})),
                    Mock(
                        status_code=200,
                        json=Mock(
                            return_value={
                                "choices": [{"message": {"content": "Fallback response"}}],
                                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                                "model": "google/gemini-2.5-pro",
                            }
                        ),
                    ),""",
        """                    FakeResponse(status_code=500, json_data={"error": "Server error"}),
                    FakeResponse(
                        status_code=200,
                        json_data={
                                "choices": [{"message": {"content": "Fallback response"}}],
                                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                                "model": "google/gemini-2.5-pro",
                            }
                    ),""",
    )
)

# Make sure to include the FakeResponse class definition itself in the content if it's not already there.
# This part is crucial and should be done only once.
# Check if the class is already there to prevent duplication.
if "class FakeResponse:" not in content:
    content = content.replace(
        "from app.adapters.openrouter.openrouter_client import OpenRouterClient",
        """from app.adapters.openrouter.openrouter_client import OpenRouterClient


class FakeResponse:
    def __init__(self, status_code, json_data, headers=None, content=None, text=None, history=None):
        self.status_code = status_code
        self._json_data = json_data
        self.headers = headers or {}
        self.content = content if content is not None else json.dumps(json_data).encode("utf-8")
        self.text = text if text is not None else json.dumps(json_data)
        self.elapsed = timedelta(seconds=0.001)
        self.request = MagicMock() # Mock the request object
        self.history = history if history is not None else [] # Ensure history is present

    def json(self):
        return self._json_data

    async def __aiter__(self):
        yield self.content

    async def aclose(self):
        pass

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP Error: {self.status_code}")""",
    )


for old_block, new_block in replacements:
    content = content.replace(old_block, new_block)

# Write the modified content back
with open(file_path, "w") as f:
    f.write(content)

print("Replacements complete in tests/test_openrouter_compliance.py")
