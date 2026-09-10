import { z } from 'zod';

export type Data = Record<string, unknown>;
export const object = (value: unknown): Data =>
  value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Data : {};
export const list = (value: unknown): Data[] => Array.isArray(value) ? value.map(object) : [];
export const strings = (value: unknown): string[] => Array.isArray(value)
  ? value.filter((item): item is string => typeof item === 'string') : [];
export const text = (value: unknown): string => typeof value === 'string' || typeof value === 'number'
  ? String(value) : 'Non disponibile';

const id = z.string().uuid();
const hash = z.string().regex(/^[a-f0-9]{64}$/);
const timestamp = z.iso.datetime({ offset: true });
export const SummarySchema = z.object({
  record_id: id, kind: z.string(), label: z.string(), canonical_id: z.string().nullable(),
  input_fingerprint: hash.nullable(), as_of: timestamp.nullable(), knowledge_mode: z.string().nullable(),
  stored_at: timestamp, payload_sha256: hash,
  opportunity_id: id.nullable(), opportunity_fingerprint: hash.nullable(),
});
export type Summary = z.infer<typeof SummarySchema>;
const record = z.record(z.string(), z.unknown());
const version = z.literal('aie-product-ui-v1');
export const DetailSchema = z.object({
  contract_version: version, summary: SummarySchema, record, card: record.nullable(),
  fits: z.array(z.object({ summary: SummarySchema, record })),
  verification: z.literal('storage_verified_not_financial_replay'),
});
export type Detail = z.infer<typeof DetailSchema>;
export const SessionSchema = z.object({
  contract_version: version, write_enabled: z.boolean(), intake_enabled: z.boolean(),
  reference_data: z.boolean(),
  write_token: z.string().nullable(),
});
export type Session = z.infer<typeof SessionSchema>;

async function request(path: string, signal?: AbortSignal, body?: string, token?: string | null) {
  const response = await fetch('/ui-api/' + path, {
    method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin', cache: 'no-store', signal,
    headers: body === undefined ? {} : { 'Content-Type': 'application/json', 'X-AIE-Workspace-Token': token ?? '' },
    body,
  });
  const data: unknown = await response.json();
  if (!response.ok) {
    const error = object(data);
    const fields = list(error.fields).map(f => `${strings(f.loc).join(' · ')}: ${text(f.msg)}`).join('\n');
    throw new Error(fields || (typeof error.message === 'string' ? error.message : 'AIE ha bloccato la richiesta.'));
  }
  return data;
}

export const api = {
  session: async (signal?: AbortSignal) => SessionSchema.parse(await request('session', signal)),
  records: async (signal?: AbortSignal) => z.object({ contract_version: version, records: z.array(SummarySchema) })
    .parse(await request('records', signal)).records,
  detail: async (recordId: string, signal?: AbortSignal) => {
    id.parse(recordId);
    const detail = DetailSchema.parse(await request('records/' + recordId, signal));
    if (detail.summary.record_id !== recordId) throw new Error('Il record ricevuto non corrisponde al dossier selezionato.');
    return detail;
  },
  prepare: async (payload: string, token: string | null) => z.object({
    contract_version: version, request: record, verification: z.literal('schema_only'),
  }).parse(await request('prepare', undefined, payload, token)),
  submit: async (payload: Data, token: string | null) => z.object({
    contract_version: version, response: record,
    persisted: z.array(z.object({ record_id: id, kind: z.string(), status: z.string() })),
  }).parse(await request('submit', undefined, JSON.stringify(payload), token)),
};

// Presentation only. Exact decimals remain untouched in the canonical JSON audit view.
export function number(value: unknown, digits = 2): string {
  if ((typeof value !== 'string' && typeof value !== 'number') || value === '' || !Number.isFinite(Number(value)))
    return 'Non disponibile';
  return Number(value).toLocaleString('it-IT', { maximumFractionDigits: digits });
}
export function percent(value: unknown): string {
  if ((typeof value !== 'string' && typeof value !== 'number') || value === '' || !Number.isFinite(Number(value)))
    return 'Non disponibile';
  return `${number(Number(value) * 100, 1)}%`;
}
export function money(value: unknown): string {
  const amount = object(value);
  return typeof amount.currency === 'string' && amount.amount != null
    ? `${number(amount.amount)} ${amount.currency}` : 'Non disponibile';
}
export function date(value: unknown): string {
  if (typeof value !== 'string' || !Number.isFinite(Date.parse(value))) return 'Non disponibile';
  return new Date(value).toLocaleString('it-IT', {
    dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC',
  }) + ' UTC';
}
export function safeSource(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  try {
    const url = new URL(value);
    return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password
      && !url.hostname.endsWith('.test') ? url.href : null;
  } catch { return null; }
}

export function exactRelated(records: Summary[], kind: string, reference: unknown, idField: string): Summary | undefined {
  const ref = object(reference), boundary = object(ref.knowledge_boundary);
  return records.find(item => item.kind === kind && item.canonical_id === ref[idField]
    && item.input_fingerprint === ref.input_fingerprint && item.as_of === boundary.as_of
    && item.knowledge_mode === boundary.knowledge_mode);
}

export function evidenceFor(dossier: Data, item?: Data): { claims: Data[]; evidence: Data[] } {
  if (!item) return { claims: list(dossier.claims), evidence: list(dossier.evidence) };
  const claimIds = new Set([...strings(item.claim_ids), ...strings(item.assumption_claim_ids)]);
  const pending = [...strings(item.input_fact_ids), ...strings(item.supporting_fact_ids), ...strings(item.fact_ids)];
  const visited = new Set<string>();
  const facts = [...list(dossier.financial_facts), ...list(dossier.derived_facts)];
  while (pending.length) {
    const next = pending.pop()!;
    if (visited.has(next)) continue;
    visited.add(next);
    const fact = facts.find(f => f.fact_id === next);
    if (!fact) continue;
    strings(fact.claim_ids).forEach(id => claimIds.add(id));
    pending.push(...strings(fact.input_fact_ids));
  }
  const claims = list(dossier.claims).filter(c => claimIds.has(text(c.claim_id)));
  const evidenceIds = new Set(claims.flatMap(c => strings(c.evidence_ids)));
  return { claims, evidence: list(dossier.evidence).filter(e => evidenceIds.has(text(e.evidence_id))) };
}
