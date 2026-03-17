# Content adapter package: URL processing pipeline from extraction through LLM summarization.
#
# Subdirectories: scraper/ (multi-provider chain), platform_extraction/ (YouTube, Twitter).
# Entry point: url_processor.py. To add a summarization feature, extend the relevant
# llm_summarizer_* module and wire it into LLMSummarizerService.
