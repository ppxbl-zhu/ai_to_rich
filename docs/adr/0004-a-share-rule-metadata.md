# ADR 0004: Version A-share rules and consume daily price-limit metadata

- Status: Accepted
- Date: 2026-07-29

## Context

A-share rules vary by board, security status, listing stage, and effective date.
The 2026 exchange rules changed some behavior, including the Shanghai main-board
risk-warning price limit effective 2026-07-06. Hard-coding one percentage would
make historical decisions incorrect.

## Decision

- Main-board and ChiNext buys use 100-share lots.
- STAR Market buys require at least 200 shares and may increment by one share.
- Sell validation uses available quantity and T+1 settlement.
- ST, suspended, and delisting securities are excluded regardless of their
  theoretical price limit.
- Every tradable quote must carry point-in-time `limit_up` and `limit_down`
  values from versioned market data. The risk engine does not infer limits from
  the current rulebook.

## References

- Shanghai Stock Exchange 2026 rules announcement:
  <https://www.sse.com.cn/aboutus/mediacenter/hotandd/c/c_20260424_10816474.shtml>
- STAR Market order quantity guidance:
  <https://edu.sse.com.cn/tib/>
- Shenzhen Stock Exchange 2026 trading rules:
  <https://docs.static.szse.cn/www/lawrules/rule/trade/current/W020260424690713155663.pdf>

## Consequences

Historical and live providers must supply the applicable daily limits. Missing
limit metadata fails closed. Exchange-rule changes require a documented data or
rule version rather than silent constant edits.
