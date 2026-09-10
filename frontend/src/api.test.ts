import { readFileSync } from 'node:fs';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, DetailSchema, evidenceFor, exactRelated, money, number, object, percent, safeSource, SummarySchema } from './api';

const fixture = JSON.parse(readFileSync(new URL('../.contract-fixture.json', import.meta.url), 'utf-8'));
const records = SummarySchema.array().parse(fixture.records);
const details = DetailSchema.array().parse(fixture.details);

afterEach(() => vi.unstubAllGlobals());

describe('contract between actual Python output and TypeScript', () => {
  it('accepts all real states and an actual computed decision without rewriting decimals', () => {
    expect(details.map(d => d.summary.kind).sort()).toEqual(['marginal_decision', 'opportunity_state', 'portfolio_state']);
    const decision = details.find(d => d.summary.kind === 'marginal_decision')!;
    expect(decision.fits).toHaveLength(4);
    expect(decision.card?.action).toBe('allocate');
    expect(typeof object(decision.card?.evaluated_amount).amount).toBe('string');
    expect(decision.card?.execution_status).toBe('not_evaluated');
  });
  it('rejects incompatible transport versions', () => {
    expect(() => DetailSchema.parse({ ...details[0], contract_version: 'aie-product-ui-v2' })).toThrow();
  });
  it('joins only exact canonical identity, fingerprint and knowledge boundary', () => {
    const decision = details.find(d => d.summary.kind === 'marginal_decision')!;
    const reference = object(decision.record.opportunity_state);
    const linked = exactRelated(records, 'opportunity_state', reference, 'opportunity_id');
    expect(linked?.label).toBe('Micron Technology');
    expect(exactRelated(records, 'opportunity_state', { ...reference, input_fingerprint: '0'.repeat(64) }, 'opportunity_id')).toBeUndefined();
    expect(exactRelated(records, 'opportunity_state', { ...reference, knowledge_boundary: { ...object(reference.knowledge_boundary), as_of: '2027-01-01T00:00:00Z' } }, 'opportunity_id')).toBeUndefined();
    expect(exactRelated(records, 'opportunity_state', { ...reference, knowledge_boundary: { ...object(reference.knowledge_boundary), knowledge_mode: 'invented_mode' } }, 'opportunity_id')).toBeUndefined();
  });
  it('follows declared formula inputs to claims and evidence, never unrelated sources', () => {
    const opportunity = details.find(d => d.summary.kind === 'opportunity_state')!.record;
    const derived = (opportunity.derived_facts as Record<string, unknown>[])[0];
    const linked = evidenceFor(opportunity, derived);
    expect(linked.claims.length).toBeGreaterThan(0);
    expect(linked.evidence.length).toBeGreaterThan(0);
    expect(evidenceFor(opportunity, { claim_ids: ['missing'] }).evidence).toEqual([]);
    expect(evidenceFor(opportunity).evidence).toEqual(opportunity.evidence);
  });
});

describe('display and request failure behavior', () => {
  it('preserves unknown rather than formatting it as zero', () => {
    for (const value of [null, undefined, '', 'not-a-number']) {
      expect(number(value)).toBe('Non disponibile');
      expect(percent(value)).toBe('Non disponibile');
    }
    expect(money({ amount: '0', currency: 'USD' })).toBe('0 USD');
    expect(money({ amount: '100', currency: 'EUR' })).toBe('100 EUR');
    expect(money({ amount: '100', currency: 'USD' })).toBe('100 USD');
  });
  it('disallows active content and credential-bearing evidence links', () => {
    for (const url of ['javascript:alert(1)', 'data:text/html,x', 'file:///etc/passwd', 'https://user:secret@example.org', 'https://example.test/filing', 'not a url'])
      expect(safeSource(url)).toBeNull();
    expect(safeSource('https://www.sec.gov/Archives/filing.htm')).toBe('https://www.sec.gov/Archives/filing.htm');
  });
  it('blocks a mismatched record instead of displaying the wrong company', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => details[0] }));
    await expect(api.detail('00000000-0000-4000-8000-000000000000')).rejects.toThrow('non corrisponde');
  });
  it('does not retry a failed mutation or invent a successful result', async () => {
    const fetch = vi.fn().mockResolvedValue({ ok: false, json: async () => ({ blocking: true, message: 'Fingerprint mismatch' }) });
    vi.stubGlobal('fetch', fetch);
    await expect(api.submit({ operation: 'build_marginal_decision' }, 'token')).rejects.toThrow('Fingerprint mismatch');
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});
