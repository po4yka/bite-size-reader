---
id: <% tp.system.prompt("Paperclip ID (e.g. POY-285)") %>
title: <% tp.system.prompt("Task title (imperative)") %>
status: backlog
area: <% tp.system.suggester(["auth","api","kmp","sync","ci","frontend","observability","testing","content","scraper","llm","db","docs","ops"], ["auth","api","kmp","sync","ci","frontend","observability","testing","content","scraper","llm","db","docs","ops"]) %>
priority: <% tp.system.suggester(["critical","high","medium","low"], ["critical","high","medium","low"]) %>
owner: <% tp.system.prompt("Owner role") %>
paperclip: <% tp.frontmatter["id"] %>
blocks: []
blocked_by: []
created: <% tp.date.now("YYYY-MM-DD") %>
updated: <% tp.date.now("YYYY-MM-DD") %>
---

- [ ] #task <% tp.frontmatter["title"] %> #repo/ratatoskr #area/<% tp.frontmatter["area"] %> #status/backlog 🔼 [[<% tp.frontmatter["id"] %>]]

## Objective

## Context

## Acceptance criteria

- [ ] 

## Definition of done
