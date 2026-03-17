# Content adapter package.
#
# Module ownership for app/adapters/content/:
#
#   url_processor.py          -- top-level orchestrator: routes URLs through
#                                extraction → summarization → storage pipeline
#   url_flow_*.py             -- data models and context helpers for URL flow
#   content_extractor*.py     -- content extraction layer (scraper chain,
#                                HTTP fallback, crawl-based extraction)
#   scraper/                  -- multi-provider scraper chain (protocol, chain,
#                                factory, and per-provider implementations)
#   platform_extraction/      -- platform-specific extractors (YouTube, Twitter)
#   llm_summarizer_articles.py -- article-specific summarization + translation
#   llm_summarizer_cache.py   -- deduplication cache for LLM summarization calls
#   llm_summarizer_insights.py -- second-pass additional insights generation
#   llm_summarizer_metadata.py -- metadata enrichment (entities, tags, stats)
#   llm_summarizer_semantic.py -- semantic chunk generation and embedding helpers
#   llm_summarizer_text.py    -- text normalization and prompt-prep utilities
#   llm_response_workflow*.py -- LLM call execution, retry, repair, and storage
#   summarization_runtime.py  -- runtime configuration for summarization
#   summarization_models.py   -- shared Pydantic models for summarization
#   summary_request_factory.py -- factory for constructing summary request DTOs
#   pure_summary_service.py   -- stateless summarization (no DB, no Telegram)
#   search_context_*.py       -- web search context enrichment for summaries
#
# To add a new summarization feature: extend the relevant llm_summarizer_*
# module, or create a new one following the same naming convention. Wire it
# into LLMSummarizerService in llm_summarizer_articles.py.
