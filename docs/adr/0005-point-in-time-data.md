# ADR 0005: Point-in-time data and immutable dataset versions

- Status: Accepted
- Date: 2026-07-29

## Context

Daily prices, intraday bars, financial statements, announcements, and news
become available at different times. Using a report-period date instead of its
actual availability time creates look-ahead bias.

## Decision

Every normalized record stores:

- event time;
- first availability time;
- capture time;
- provider source;
- quality state;
- immutable payload.

Datasets reject duplicate record IDs and derive an order-independent SHA-256
version from canonical record content. A decision may consume only valid records
whose availability time is not later than the decision time. Source conflicts
raise an explicit error.

## Consequences

Financial reports must use disclosure time, not only report period. Intraday
freshness uses market event time. Provider ingestion cannot mutate an existing
dataset version; corrections produce a new version.
