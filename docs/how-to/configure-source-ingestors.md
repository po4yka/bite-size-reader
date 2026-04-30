# Configure Optional Source Ingestors

Phase 5 adds optional proactive ingestors that emit generic `Source` and
`FeedItem` rows for signal scoring. Generic RSS remains the default path.
Hacker News and Reddit are zero-cost optional sources. Substack is an RSS
specialization. X/Twitter is disabled unless explicitly cost-acknowledged.

## Enable Hacker News

```yaml
signal_ingestion:
  enabled: true
  hn_enabled: true
  hn_feeds:
    - top
    - best
  max_items_per_source: 30
```

Supported HN feeds are `top`, `best`, `new`, and `newest`. The adapter uses
`https://hacker-news.firebaseio.com/v0/*stories.json` plus `item/{id}.json`.
No API key is required. Items are persisted as `kind=hacker_news` with score,
comment count, author, URL, and timestamp metadata.

## Enable Reddit

```yaml
signal_ingestion:
  enabled: true
  reddit_enabled: true
  reddit_subreddits:
    - selfhosted
    - python
  reddit_listing: hot
  reddit_requests_per_minute: 60
  max_items_per_source: 25
```

The adapter uses public subreddit JSON endpoints such as
`https://www.reddit.com/r/selfhosted/hot.json`. Credentials are not required for
public subreddits. The default request budget is 60 requests/minute and config
validation rejects values above 100 requests/minute. HTTP 429 is treated as a
rate-limit error; HTTP 401/403 is treated as an auth/permission error and trips
the source circuit breaker quickly.

## Enable Substack

Substack uses the same RSS path as normal feeds. Add the publication feed through
the existing RSS subscription flow, or resolve the URL with
`app.adapters.rss.substack.resolve_substack_feed_url`:

```text
platformer -> https://platformer.substack.com/feed
https://platformer.substack.com/p/post -> https://platformer.substack.com/feed
https://www.custom-domain.com -> https://www.custom-domain.com/feed
```

Substack feed rows are persisted as `kind=substack` while using the same
`RssSignalIngester` contract as RSS.

## X/Twitter Cost Gate

Default installs never start X/Twitter ingestion. To opt in, both flags are
required:

```yaml
signal_ingestion:
  enabled: true
  twitter_enabled: true
  twitter_ack_cost: true
```

The equivalent environment override is:

```env
TWITTER_INGESTION_ENABLED=true
TWITTER_INGESTION_ACK_COST=true
```

This is intentionally separate from `twitter.enabled`, which controls one-off
X/Twitter URL extraction. Proactive X/Twitter polling is bring-your-own-token and
has an explicit cost warning because the Basic tier is approximately
$200/month.
