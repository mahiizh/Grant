---
title: SentimentAnalyzer Service Specification
doc_id: doc_service_sentimentanalyzer
acl_scope: customer-support
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# SentimentAnalyzer Service Specification

SentimentAnalyzer is a Tier 2 production service in the GraphRAG lab.

## Overview
SentimentAnalyzer is owned by the Customer Support team. The service owner is Mei Tan.

## SLA
SentimentAnalyzer targets a p99 latency of 112ms and an error budget of 0.4% per 30 days.

## Dependencies
SentimentAnalyzer depends on PaymentRail for its upstream data path.

## Runbook
Runbook RB-0703 covers SentimentAnalyzer.

## Change Log
Version v1 of SentimentAnalyzer was deployed on 2026-03-09.
