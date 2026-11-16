---
title: INC-2026-14 Postmortem for ThreatScanner
doc_id: doc_incident_threatscanner
acl_scope: security
valid_from: 2026-04-12T00:00:00Z
source_tier: 1
---

# INC-2026-14 Postmortem for ThreatScanner

INC-2026-14 is the postmortem for a production incident affecting ThreatScanner.

## Summary
INC-2026-14 affected ThreatScanner for 62 minutes.

## Root Cause
The root cause was connection-pool exhaustion in DriftMonitor.

## Remediation
The Security team restored ThreatScanner by rolling back DriftMonitor.
