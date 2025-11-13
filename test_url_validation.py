#!/usr/bin/env python3
import re

# Test the URL pattern
url_pattern = r'^https?://[^\s<>"{}|\\^`]*$'

test_urls = [
    "https://habr.com/ru/articles/947772/",
    "https://habr.com/ru/companies/yandex_praktikum/articles/947066/",
    "https://apptractor.ru/develop/retrofit-korutiny-kotlin-polnoe-rukovodstvo-dlya-android-razrabotchikov.html",
    "https://www.zacsweers.dev/android-proguard-rules/",
    "https://www.wired.com/story/ai-agents-are-getting-better-at-writing-code-and-hacking-it-as-well/",
]

for url in test_urls:
    match = re.match(url_pattern, url)
