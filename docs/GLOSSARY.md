# Domain glossary

| Term | Definition |
|---|---|
| T0 | Closing-auction strategy purchase trading day |
| T1 | Trading day immediately after T0; default exit day |
| T2 | Second trading day after T0; extension requires the calibrated gate |
| Paper mode | Advice and simulated fills without broker order submission |
| Quote | Point-in-time price observation with source and freshness metadata |
| Bar | Time-bucketed market observation |
| Signal | Structured strategy opinion; never an order |
| TradePlan | Entry, size, exit, stop, and invalidation conditions |
| OrderIntent | Proposed order awaiting deterministic validation |
| ValidatedOrder | Order intent that passed every risk rule |
| Fill | Simulated or observed execution result |
| Data freshness | Difference between market time and decision time |
| Point-in-time data | Information available at the historical decision time |
| Experiment lineage | Immutable parent, code, data, configuration, seed, and result chain |

