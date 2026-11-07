export interface DocumentFixture {
  id: string;
  title: string;
  file_type: string;
  size_kb: number;
  chunks: number;
  entities_extracted: number;
  relations_extracted: number;
  tier: number;
  ingested_at: string;
  target_node_id: string;
  valid_from: string;
}

export const INITIAL_DOCS_FIXTURE: DocumentFixture[] = [
  {
    id: "doc-1",
    title: "incident-postmortem-2026-03-outbox.md",
    file_type: "md",
    size_kb: 48,
    chunks: 14,
    entities_extracted: 8,
    relations_extracted: 12,
    tier: 1,
    ingested_at: "2026-03-24 14:15",
    target_node_id: "outbox",
    valid_from: "2026-03-20",
  },
  {
    id: "doc-2",
    title: "runbook-data-platform-cdc.md",
    file_type: "md",
    size_kb: 32,
    chunks: 9,
    entities_extracted: 5,
    relations_extracted: 8,
    tier: 2,
    ingested_at: "2026-04-02 09:30",
    target_node_id: "data_platform",
    valid_from: "2026-04-01",
  },
  {
    id: "doc-3",
    title: "arch-dual-write-consistency.md",
    file_type: "md",
    size_kb: 64,
    chunks: 18,
    entities_extracted: 9,
    relations_extracted: 16,
    tier: 1,
    ingested_at: "2026-01-15 11:20",
    target_node_id: "postgres",
    valid_from: "2026-01-01",
  },
  {
    id: "doc-4",
    title: "sla-contracts-2026-q1.json",
    file_type: "json",
    size_kb: 24,
    chunks: 6,
    entities_extracted: 4,
    relations_extracted: 7,
    tier: 1,
    ingested_at: "2026-01-05 16:45",
    target_node_id: "core_banking",
    valid_from: "2026-01-01",
  },
];
