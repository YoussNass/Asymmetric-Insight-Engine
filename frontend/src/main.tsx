import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, date, evidenceFor, exactRelated, list, money, number, object, percent, safeSource, strings, text } from './api';
import type { Data, Detail, Session, Summary } from './api';
import './style.css';

const client = new QueryClient({ defaultOptions: {
  queries: { retry: false, staleTime: Infinity, refetchOnWindowFocus: false, refetchOnReconnect: false },
  mutations: { retry: false },
} });
const labels: Record<string, string> = {
  opportunity_state: 'Analisi aziendale', portfolio_state: 'Portafoglio', marginal_decision: 'Nuovo capitale',
  portfolio_fit: 'Compatibilità con il portafoglio', policy_constrained_decision: 'Decisione con vincoli',
  replacement_decision: 'Sostituzione', position_review: 'Revisione posizione',
  ready_for_portfolio_review: 'Pronta per il confronto', ready_for_underwriting: 'Pronta per l’analisi',
  supportive: 'A favore', mixed: 'Elementi contrastanti', adverse: 'Critica', insufficient_evidence: 'Dati insufficienti',
  pass: 'Superato', fail: 'Non superato', unknown: 'Non determinato',
  allocate: 'Allocazione', no_allocation: 'Nessuna allocazione', hold: 'Mantenimento', replace: 'Sostituzione',
  revenue_and_margins: 'Ricavi e margini', cash_and_earnings_quality: 'Qualità degli utili e della cassa',
  roic: 'Rendimento del capitale', balance_sheet_and_capital_needs: 'Bilancio e fabbisogno di capitale',
  dilution_and_per_share_economics: 'Diluizione e valore per azione', value_capture_and_competition: 'Valore catturato e concorrenza',
  operating_execution: 'Esecuzione operativa', valuation_and_asymmetry: 'Valutazione e asimmetria',
  causal_handoff: 'Tesi causale', survivability: 'Sopravvivenza finanziaria', economic_value_capture: 'Cattura di valore',
  per_share_integrity: 'Integrità per azione', valuation_completeness: 'Completezza della valutazione', falsifiability: 'Falsificabilità',
  historical_reconstruction: 'Ricostruzione storica', live_system_replay: 'Replay di quanto noto ad AIE',
  uncalibrated: 'Non calibrata', conditional: 'Condizionata',
  candidate_equity: 'Candidata', existing_holding: 'Posizione esistente', core_etf: 'ETF core', investment_cash: 'Liquidità investibile',
  emergency_reserve: 'Riserva di emergenza', opportunistic: 'Opportunistica', strategic: 'Strategica', unallocated: 'Non allocata',
  reported: 'Dato riportato', market_observed: 'Dato di mercato', analyst_adjusted: 'Ipotesi dell’analista',
  bear: 'Prudente', base: 'Centrale', bull: 'Favorevole', low: 'Bassa', moderate: 'Moderata', high: 'Alta',
  first_preferred: 'Prima alternativa preferita', second_preferred: 'Seconda alternativa preferita',
  indeterminate: 'Indeterminato', equivalent: 'Equivalenti', first: 'Prima alternativa', second: 'Seconda alternativa', balanced: 'Bilanciato',
  standalone_case: 'Caso d’investimento', permanent_loss: 'Perdita permanente', portfolio_effect: 'Effetto sul portafoglio', uncertainty: 'Incertezza',
  observation: 'Osservazione', statistical_result: 'Risultato statistico', inference: 'Inferenza', hypothesis: 'Ipotesi', qualitative_judgement: 'Giudizio qualitativo',
  build_opportunity_state: 'Analisi aziendale', build_portfolio_state: 'Stato del portafoglio', build_marginal_decision: 'Confronto per nuovo capitale',
};
const label = (value: unknown) => labels[text(value)] ?? text(value).replaceAll('_', ' ');
const navigate = (route: string) => { window.location.hash = route; };
const sectionFor = (kind: string) => kind === 'opportunity_state' ? 'analyze' : kind === 'portfolio_state' ? 'portfolio' : 'decisions';
const openRecord = (record: Summary) => navigate(`/${sectionFor(record.kind)}/${record.record_id}`);

function Icon({ name }: { name: string }) {
  const paths: Record<string, React.ReactNode> = {
    home: <><path d="m3 10 9-7 9 7v11h-6v-7H9v7H3Z" /></>,
    analyze: <><circle cx="10" cy="10" r="6" /><path d="m15 15 6 6M7 10h6m-3-3v6" /></>,
    portfolio: <><rect x="3" y="7" width="18" height="14" rx="2" /><path d="M8 7V3h8v4M3 13h18m-9-2v4" /></>,
    decisions: <><path d="M7 3h13v18H4V6m3-3v5H2m6 5 2 2 5-5m-7 9h8" /></>,
    arrow: <path d="M4 12h16m-6-6 6 6-6 6" />,
    source: <><path d="M14 3h7v7m-10 3L21 3M10 5H3v16h16v-7" /></>,
    refresh: <><path d="M20 7v5h-5M4 17v-5h5" /><path d="M5 8a8 8 0 0 1 14-3l1 2M4 17l1 2a8 8 0 0 0 14-3" /></>,
    close: <path d="m6 6 12 12M6 18 18 6" />,
  };
  return <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] ?? paths.source}</svg>;
}
function Badge({ value }: { value: unknown }) {
  const status = text(value);
  return <span className={`badge ${['pass', 'supportive'].includes(status) ? 'positive' : ['fail', 'adverse', 'unknown', 'mixed', 'insufficient_evidence', 'uncalibrated'].includes(status) ? 'caution' : ''}`}>{label(value)}</span>;
}
function ErrorBox({ error }: { error: unknown }) {
  return <div className="notice danger" role="alert"><strong>Operazione bloccata</strong><p>{error instanceof Error ? error.message : 'Risposta non valida. I risultati precedenti non sono utilizzati.'}</p></div>;
}
function Empty({ title, children }: { title: string; children: React.ReactNode }) {
  return <div className="empty"><span className="empty-mark"><Icon name="decisions" /></span><h3>{title}</h3><p>{children}</p></div>;
}
function Disclosure({ title, items, tone = '' }: { title: string; items: unknown; tone?: string }) {
  const values = strings(items);
  return values.length ? <section className={`disclosure ${tone}`}><h3>{title} <span className="count">{values.length}</span></h3><ul>{values.map((s, i) => <li key={i}>{s}</li>)}</ul></section> : null;
}
function Audit({ detail }: { detail: Detail }) {
  return <details className="audit"><summary>Provenienza e record originale</summary>
    <p>Integrità dell’archivio verificata. Questa lettura non ricalcola la decisione finanziaria.</p>
    <dl><dt>Data dell’analisi</dt><dd>{date(detail.summary.as_of)}</dd><dt>Modalità</dt><dd>{label(detail.summary.knowledge_mode)}</dd><dt>Salvato per la prima volta</dt><dd>{date(detail.summary.stored_at)}</dd><dt>Impronta degli input</dt><dd><code>{detail.summary.input_fingerprint ?? 'Non disponibile'}</code></dd><dt>SHA-256 del record</dt><dd><code>{detail.summary.payload_sha256}</code></dd></dl>
    <p>I numeri nelle schede sono formattati per leggibilità. Qui restano visibili i decimali originali.</p>
    <pre>{JSON.stringify(detail.record, null, 2)}</pre>
  </details>;
}

function Modal({ title, children, close, wide = false }: { title: string; children: React.ReactNode; close: () => void; wide?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    const previous = document.activeElement;
    ref.current?.showModal(); heading.current?.focus();
    return () => { ref.current?.close(); if (previous instanceof HTMLElement) previous.focus(); };
  }, []);
  return <dialog ref={ref} className={wide ? 'modal wide' : 'modal'} aria-labelledby="dialog-title"
    onCancel={e => { e.preventDefault(); close(); }} onClick={e => { if (e.target === e.currentTarget) close(); }}>
    <div className="modal-inner"><header className="modal-head"><h2 id="dialog-title" ref={heading} tabIndex={-1}>{title}</h2><button className="icon-button" aria-label="Chiudi pannello" onClick={close}><Icon name="close" /></button></header>{children}</div>
  </dialog>;
}
type EvidenceContext = { dossier: Data; item?: Data; title: string };
function EvidenceDrawer({ context, close }: { context: EvidenceContext; close: () => void }) {
  const { dossier, item } = context;
  const { claims, evidence } = evidenceFor(dossier, item);
  return <Modal title={context.title} close={close}>
    <p className="muted">Fonti e interpretazioni conservate con questo dossier, alla sua data di analisi.</p>
    {item && <details><summary>Elemento selezionato</summary><pre>{JSON.stringify(item, null, 2)}</pre></details>}
    {claims.map(c => <article className="claim" key={text(c.claim_id)}><Badge value={c.claim_type} /><p>{text(c.text)}</p><small>Calibrazione: {label(object(c.confidence).calibration_status)}</small></article>)}
    {!evidence.length && <div className="notice">Nessuna evidenza direttamente collegata a questo elemento. Consulta i riferimenti nel record originale.</div>}
    {evidence.map(e => <article className="source-card" key={text(e.evidence_id)}>
      <span className="eyebrow">{label(e.source_type)}</span><h3>{text(e.title)}</h3>
      <dl><dt>Evento / periodo</dt><dd>{date(e.effective_at)}</dd><dt>Disponibile alla fonte</dt><dd>{date(e.available_at)}</dd><dt>Registrata da AIE</dt><dd>{date(e.recorded_at)}</dd><dt>Posizione nel documento</dt><dd>{text(e.source_locator)}</dd><dt>Hash dell’evidenza</dt><dd><code>{text(e.content_hash)}</code></dd></dl>
      <Disclosure title="Dati mancanti della fonte" items={object(e.quality).missing_fields} tone="caution" />
      {safeSource(e.source_uri) ? <a className="text-link" href={safeSource(e.source_uri)!} target="_blank" rel="noreferrer noopener">Apri riferimento esterno <Icon name="source" /></a> : <p className="muted">Fonte locale o dimostrativa. Riferimento: <code>{text(e.source_uri)}</code></p>}
      <small>La pagina esterna può cambiare; il riferimento e l’impronta qui mostrati appartengono al dossier salvato.</small>
    </article>)}
  </Modal>;
}

function ImportDossier({ session, close }: { session: Session; close: () => void }) {
  const [payload, setPayload] = useState('');
  const [filename, setFilename] = useState('');
  const [fileError, setFileError] = useState<Error | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const cache = useQueryClient();
  const prepare = useMutation({ mutationFn: () => api.prepare(payload, session.write_token) });
  const submit = useMutation({ mutationFn: (request: Data) => api.submit(request, session.write_token),
    onSuccess: async result => {
      await cache.invalidateQueries({ queryKey: ['records'] });
      const last = result.persisted.at(-1);
      if (last) navigate(`/${sectionFor(last.kind)}/${last.record_id}`);
      close();
    },
  });
  const prepared = prepare.data?.request;
  const decisionInput = object(prepared?.decision_input);
  const busy = prepare.isPending || submit.isPending;
  return <Modal title="Carica un dossier AIE" close={() => { if (!busy) close(); }} wide>
    <p>Carica una richiesta JSON già preparata per AIE: analisi aziendale, stato del portafoglio o confronto per nuovo capitale. Il motore ricontrolla gli input prima di salvare il risultato.</p>
    <div className="notice">Questa versione richiede dati e ipotesi espliciti. Un ticker, un PDF o una domanda libera non costituiscono ancora un dossier completo.</div>
    <label className="file-label">Dossier JSON <span>Massimo 2 MB</span><input type="file" accept=".json,application/json" disabled={busy} onChange={async e => {
      prepare.reset(); submit.reset(); setConfirmed(false); setPayload(''); setFileError(null);
      const file = e.target.files?.[0]; if (!file) return;
      if (file.size > 2_000_000) { setFileError(new Error('Il dossier supera il limite di 2 MB.')); return; }
      setFilename(file.name);
      try { setPayload(await file.text()); }
      catch { setFileError(new Error('Impossibile leggere il file selezionato. Selezionalo di nuovo.')); }
    }} /></label>
    {filename && <p className="muted">{filename}</p>}
    {!prepared && <button className="primary" disabled={!payload || busy} onClick={() => prepare.mutate()}>{prepare.isPending ? 'Verifica del formato…' : 'Controlla e mostra gli input'}</button>}
    {(fileError || prepare.error || submit.error) && <ErrorBox error={fileError || prepare.error || submit.error} />}
    {prepared && <div className="review-inputs"><span className="eyebrow">Riepilogo prima dell’invio</span><h3>{label(prepared.operation)}</h3>
      <div className="notice">Formato riconosciuto. La verifica finanziaria e delle fonti avviene con l’invio al motore.</div>
      {prepared.operation === 'build_marginal_decision' && <><div className="amount-line">Capitale da confrontare <strong>{money(object(decisionInput.capital_unit).amount)}</strong></div><p>Candidata: {text(object(decisionInput.candidate_instrument).name)}</p><p>Data: {date(object(decisionInput.knowledge_boundary).as_of)}</p><p>Il dossier include candidata, posizione esistente, ETF core e liquidità; i sei confronti restano espliciti.</p><Disclosure title="Motivazioni proposte dall’analista" items={decisionInput.decision_rationale} /></>}
      <details><summary>Rivedi tutti i dati, le ipotesi e i confronti</summary><pre>{JSON.stringify(prepared, null, 2)}</pre></details>
      <label className="confirm"><input type="checkbox" checked={confirmed} disabled={busy} onChange={e => setConfirmed(e.target.checked)} />Ho verificato il dossier, incluse le ipotesi e la data di riferimento.</label>
      <button className="primary" disabled={!confirmed || busy} onClick={() => submit.mutate(prepared)}>{submit.isPending ? 'AIE verifica e salva…' : 'Valida con AIE e salva il risultato'}</button>
      <p className="muted">Il risultato crea nuovi record immutabili. Un’allocazione è una decisione registrata, non un ordine al broker.</p>
      {submit.error && <p className="muted">La scrittura può essere parziale in caso di errore. Controlla l’archivio prima di riprovare: non viene effettuato alcun tentativo automatico.</p>}
    </div>}
  </Modal>;
}

function RecordList({ records, title, empty }: { records: Summary[]; title: string; empty: string }) {
  return <section className="panel"><div className="section-heading"><h2>{title}</h2><span className="count">{records.length}</span></div>
    {!records.length ? <Empty title={empty}>Carica un dossier AIE per creare un risultato verificabile. I dati assenti restano visibili come assenti.</Empty> :
      <div className="record-list">{records.map(r => <button className="record-row" key={r.record_id} onClick={() => openRecord(r)}><span className="record-emblem"><Icon name={sectionFor(r.kind)} /></span><span className="record-main"><strong>{r.label}</strong><span>{label(r.kind)} · Analisi del {date(r.as_of)}</span></span><span className="record-tail"><code>{r.input_fingerprint?.slice(0, 8) ?? '—'}</code><Icon name="arrow" /></span></button>)}</div>}
  </section>;
}
function Home({ records, onImport }: { records: Summary[]; onImport: () => void }) {
  const [search, setSearch] = useState('');
  const visible = records.filter(r => ['opportunity_state', 'portfolio_state', 'marginal_decision', 'replacement_decision', 'position_review'].includes(r.kind));
  const matched = visible.filter(r => `${r.label} ${r.kind} ${r.canonical_id}`.toLocaleLowerCase().includes(search.toLocaleLowerCase()));
  return <><div className="home-intro"><div className="eyebrow">Il tuo spazio decisionale</div><h1>Quale decisione<br />vuoi prendere?</h1><p>Parti da una domanda. Segui le evidenze fino al confronto tra le alternative.</p></div>
    <div className="command"><Icon name="analyze" /><label className="sr-only" htmlFor="dossier-search">Cerca nei dossier salvati</label><input id="dossier-search" type="search" value={search} onChange={e => setSearch(e.target.value)} placeholder="Cerca un’azienda, un portafoglio o un dossier…" /><kbd>Ricerca archivio</kbd></div>
    <div className="actions-grid">{[['analyze', 'Analizza un’azienda', 'Tesi, evidenze e scenari', '/analyze'], ['decisions', 'Valuta nuovo capitale', 'Candidata, posizione, ETF e cash', '/decisions'], ['portfolio', 'Rivedi il portafoglio', 'Posizioni, liquidità e contesto', '/portfolio']].map(([icon, title, subtitle, route]) => <button className="action-tile" key={route} onClick={() => navigate(route)}><Icon name={icon} /><strong>{title}</strong><span>{subtitle}</span><Icon name="arrow" /></button>)}</div>
    <div className="workspace-note"><span><strong>Una nuova analisi?</strong> Servono fonti e ipotesi esplicite, raccolte in un dossier.</span><button className="text-button" onClick={onImport}>Carica dossier <Icon name="arrow" /></button></div>
    <RecordList records={(search ? matched : visible.slice().reverse()).slice(0, 8)} title={search ? 'Risultati nell’archivio' : 'Dossier salvati di recente'} empty={search ? 'Nessun dossier corrispondente' : 'Il tuo primo caso parte da qui'} />
  </>;
}

function Opportunity({ detail, records, evidence }: { detail: Detail; records: Summary[]; evidence: (c: EvidenceContext) => void }) {
  const [tab, setTab] = useState('overview');
  const d = detail.record;
  const openEvidence = (item?: Data, title = 'Evidenze del dossier') => evidence({ dossier: d, item, title });
  const candidateDecisions = records.filter(r => r.kind === 'marginal_decision'
    && r.opportunity_id === d.opportunity_id && r.opportunity_fingerprint === d.input_fingerprint
    && r.as_of === detail.summary.as_of && r.knowledge_mode === detail.summary.knowledge_mode);
  return <><header className="detail-heading"><span className="eyebrow">Analisi aziendale</span><h1>{detail.summary.label}</h1><Badge value={d.status} /><p className="muted">La prontezza dell’analisi consente il confronto; non equivale a una raccomandazione di acquisto.</p></header>
    <nav className="view-tabs" aria-label="Sezioni dell’analisi">{[['overview', 'Panoramica'], ['evidence', 'Evidenze'], ['underwriting', 'Underwriting'], ['valuation', 'Valutazione']].map(([key, name]) => <button key={key} aria-pressed={tab === key} onClick={() => setTab(key)}>{name}</button>)}</nav>
    {tab === 'overview' && <><section className="thesis panel"><span className="eyebrow">La tesi da verificare</span><h2>{text(d.thesis_summary)}</h2><p>{text(d.readiness_rationale)}</p><button className="text-button" onClick={() => openEvidence()}>Segui le evidenze <Icon name="source" /></button></section>
      <div className="scenario-grid">{list(d.valuation_scenarios).map(s => <div className="scenario panel" key={text(s.kind)}><span className="eyebrow">Scenario {label(s.kind)}</span><strong>{percent(s.return_from_reference)}</strong><span>{number(s.value_per_share)} {text(s.currency)} / azione</span><small>Orizzonte {text(s.horizon_date)} · Ipotesi senza probabilità</small></div>)}</div>
      <div className="two-columns"><Disclosure title="Rischi della tesi" items={list(d.risks).map(r => text(r.description ?? r.rationale))} /><Disclosure title="Cosa potrebbe invalidarla" items={d.invalidation_conditions} /></div>
      <Disclosure title="Cosa manca" items={d.missing_data} tone="caution" /><Disclosure title="Segnali in conflitto" items={d.conflicts} tone="caution" />
      <section className="next-step"><span><strong>Il passo successivo è il portafoglio</strong><p>Qui compaiono soltanto i confronti che citano esattamente questa analisi, la sua impronta e la stessa data.</p></span><button className="secondary" disabled={!candidateDecisions.length} onClick={() => candidateDecisions[0] && openRecord(candidateDecisions[0])}>Apri il confronto collegato <Icon name="arrow" /></button></section>
      {candidateDecisions.length > 1 && <RecordList records={candidateDecisions} title="Tutti i confronti collegati" empty="Nessun confronto" />}{!candidateDecisions.length && <p className="muted">Manca un confronto collegato a questa analisi. Carica il dossier per nuovo capitale con questi esatti riferimenti.</p>}</>}
    {tab === 'evidence' && <section className="panel"><div className="section-heading"><h2>Ogni dato ha una provenienza</h2><button className="text-button" onClick={() => openEvidence()}>Tutte le fonti <Icon name="source" /></button></div>
      <div className="table-wrap"><table><thead><tr><th>Dato</th><th>Valore originale</th><th>Origine</th><th>Tracciabilità</th></tr></thead><tbody>{list(d.financial_facts).map(f => <tr key={text(f.fact_id)}><th>{label(f.metric)}</th><td>{text(f.value)} {typeof f.currency === 'string' ? f.currency : ''}<small>{label(f.unit)}</small></td><td><Badge value={f.basis} /></td><td><button className="text-button" onClick={() => openEvidence(f, label(f.metric))}>Evidenze <Icon name="source" /></button></td></tr>)}{list(d.derived_facts).map(f => <tr key={text(f.fact_id)}><th>{label(f.metric)}</th><td>{text(f.value)}<small>{label(f.unit)}</small></td><td><span className="badge">Derivato da AIE</span></td><td><button className="text-button" onClick={() => openEvidence(f, 'Formula e input')}>Formula e input <Icon name="source" /></button></td></tr>)}</tbody></table></div>
    </section>}
    {tab === 'underwriting' && <><div className="dimension-grid">{list(d.dimensions).map(dimension => <article className="panel dimension" key={text(dimension.kind)}><div className="section-heading"><h2>{label(dimension.kind)}</h2><Badge value={dimension.outcome} /></div><p>{text(dimension.rationale)}</p><Disclosure title="Dati mancanti" items={dimension.missing_data} tone="caution" /><Disclosure title="Conflitti" items={dimension.conflicts} tone="caution" /><button className="text-button" onClick={() => openEvidence(dimension, label(dimension.kind))}>Esamina le evidenze <Icon name="source" /></button></article>)}</div><section className="panel"><h2>Requisiti di ammissibilità</h2><div className="gates">{list(d.eligibility_gates).map(g => <div key={text(g.kind)}><span>{label(g.kind)}</span><Badge value={g.result} /><p>{text(g.rationale)}</p></div>)}</div></section></>}
    {tab === 'valuation' && <><div className="notice">Tre scenari espliciti, senza probabilità assegnate. Valori, valuta, orizzonte e ipotesi provengono dall’analisi salvata.</div><div className="scenario-grid">{list(d.valuation_scenarios).map(s => <article className="panel scenario full" key={text(s.kind)}><span className="eyebrow">{label(s.kind)}</span><strong>{number(s.value_per_share)} <small>{text(s.currency)}</small></strong><p>{percent(s.return_from_reference)} rispetto al prezzo di riferimento</p><dl><dt>Prezzo di riferimento</dt><dd>{text(s.reference_price)} {text(s.currency)}</dd><dt>Data prezzo</dt><dd>{text(s.reference_price_date)}</dd><dt>Orizzonte</dt><dd>{text(s.horizon_date)}</dd><dt>Metodo</dt><dd>{text(s.method_version)}</dd></dl><Badge value={s.calibration_status} /><Disclosure title="Ipotesi" items={s.assumptions} /><button className="text-button" onClick={() => openEvidence(s, 'Scenario ' + label(s.kind))}>Ipotesi e fonti <Icon name="source" /></button></article>)}</div></>}
    <Audit detail={detail} />
  </>;
}

function Portfolio({ detail }: { detail: Detail }) {
  const d = detail.record;
  const instruments = list(d.instruments);
  const name = (id: unknown) => text(instruments.find(i => i.instrument_id === id)?.name ?? id);
  return <><header className="detail-heading"><span className="eyebrow">Stato del portafoglio</span><h1>{text(d.title)}</h1><p>Posizioni e liquidità della fotografia selezionata. Ogni importo conserva la propria valuta.</p></header>
    <div className="notice">La riserva di emergenza è separata dal capitale investibile. La presenza di uno strumento non ne autorizza l’acquisto.</div>
    <section className="panel"><h2>Posizioni</h2><div className="table-wrap"><table><thead><tr><th>Strumento</th><th>Quantità</th><th>Valore nella valuta nativa</th><th>Conto</th></tr></thead><tbody>{list(d.positions).map(p => <tr key={text(p.position_id)}><th>{name(p.instrument_id)}</th><td>{text(p.quantity)}</td><td>{money(p.current_value)}</td><td>{text(p.account_id)}</td></tr>)}</tbody></table></div></section>
    <section className="panel"><h2>Liquidità e ruolo</h2><div className="cash-grid">{list(d.cash_balances).map(c => <article key={text(c.cash_id)} className={c.role === 'emergency_reserve' ? 'cash reserve' : 'cash'}><span>{label(c.role)}</span><strong>{money(c.balance)}</strong><small>{text(c.account_id)}</small>{c.role === 'emergency_reserve' && <span className="badge caution">Non investibile</span>}</article>)}</div></section>
    <Disclosure title="Dati mancanti" items={d.missing_data} tone="caution" /><Disclosure title="Conflitti" items={d.conflicts} tone="caution" /><Audit detail={detail} />
  </>;
}

function FitView({ fits }: { fits: Detail['fits'] }) {
  return <section className="panel"><h2>Effetto sul portafoglio</h2><p className="muted">Confronto descrittivo. Nessun punteggio di compatibilità.</p>
    {fits.map(f => { const alternative = object(f.record.alternative), effect = object(f.record.effect); return <details className="fit" key={f.summary.record_id}><summary>{text(alternative.label)} <span>{money(alternative.amount)}</span></summary><div className="fit-values"><div><small>Valore prima</small><strong>{money(effect.gross_value_before)}</strong></div><div><small>Valore dopo</small><strong>{money(effect.gross_value_after)}</strong></div></div>
      <details><summary>Concentrazione: limiti HHI originali</summary><pre>{JSON.stringify({ prima: effect.company_hhi_before, dopo: effect.company_hhi_after }, null, 2)}</pre></details>
      <div className="table-wrap"><table><thead><tr><th>Componente</th><th>Prima</th><th>Dopo</th><th>Nota</th></tr></thead><tbody>{list(effect.weight_deltas).map((w, i) => <tr key={i}><th>{text(w.component_id)}<small>{label(w.dimension)}</small></th><td>{percent(w.before_weight)}</td><td>{percent(w.after_weight)}</td><td>{w.is_non_additive === true ? 'Driver sovrapposti: non sommabili' : ''}</td></tr>)}</tbody></table></div><Disclosure title="Dati mancanti" items={f.record.missing_data} tone="caution" /><Disclosure title="Conflitti" items={f.record.conflicts} tone="caution" />
    </details>; })}
  </section>;
}
function Decision({ detail, records }: { detail: Detail; records: Summary[] }) {
  const d = detail.record, card = detail.card;
  const opportunity = exactRelated(records, 'opportunity_state', d.opportunity_state, 'opportunity_id');
  const portfolio = exactRelated(records, 'portfolio_state', d.portfolio_state, 'portfolio_state_id');
  return <><header className="detail-heading"><span className="eyebrow">Decisione registrata</span><h1>Ogni euro ha un’alternativa.</h1><p>Un confronto delimitato dai suoi input e dalla sua data di riferimento.</p></header>
    <div className="lineage"><span>Collegamenti esatti</span>{opportunity ? <button className="text-button" onClick={() => openRecord(opportunity)}>Analisi sorgente <Icon name="arrow" /></button> : <span className="muted">Analisi sorgente non collegata</span>}{portfolio ? <button className="text-button" onClick={() => openRecord(portfolio)}>Portafoglio sorgente <Icon name="arrow" /></button> : <span className="muted">Portafoglio sorgente non collegato</span>}</div>
    {card ? <section className="decision-card"><span className="eyebrow">Esito del motore AIE</span><h2>{label(card.action)}</h2><div className="decision-amount">{card.evaluated_amount ? money(card.evaluated_amount) : 'Revisione senza nuovo capitale'}<span>{text(card.selected_alternative_label)}</span></div><p>{card.action === 'no_allocation' ? 'Il capitale valutato resta in liquidità. Nessuna alternativa ha prevalso secondo il confronto registrato.' : 'Risultato del confronto salvato. L’esecuzione resta una valutazione separata.'}</p><div className="decision-meta"><span>Confidenza: {label(object(card.confidence).level)}</span><span>Calibrazione: {label(object(card.confidence).calibration_status)}</span><span>Esecuzione: non valutata</span></div></section> : <div className="notice">La scheda compatta non è disponibile per questo tipo di record. Il risultato originale è consultabile in fondo alla pagina.</div>}
    {card && <div className="two-columns"><Disclosure title="Perché questo esito" items={card.why} /><Disclosure title="Rischi e incognite" items={card.main_risks_and_unknowns} tone="caution" /></div>}
    {list(d.alternatives).length > 0 && <section className="panel"><h2>Le quattro alternative</h2><div className="alternative-grid">{list(d.alternatives).map(a => <article key={text(a.alternative_id)}><span className="eyebrow">{label(a.kind)}</span><h3>{text(a.label)}</h3><strong>{money(a.amount)}</strong><p>{text(a.rationale)}</p></article>)}</div><div className="comparisons"><h3>I sei confronti a coppie</h3>{list(d.comparisons).map((pair, i) => <details key={i}><summary>{text(pair.first_alternative_id)} / {text(pair.second_alternative_id)} <Badge value={pair.conclusion} /></summary><p>{text(pair.rationale)}</p><div className="table-wrap"><table><thead><tr><th>Dimensione</th><th>Preferenza</th><th>Motivazione</th></tr></thead><tbody>{list(pair.components).map((component, j) => <tr key={j}><th>{label(component.dimension)}</th><td><Badge value={component.preference} /></td><td>{text(component.rationale)}<Disclosure title="Dati mancanti" items={component.missing_data} tone="caution" /></td></tr>)}</tbody></table></div></details>)}</div></section>}
    {detail.fits.length > 0 && <FitView fits={detail.fits} />}
    {card && <Disclosure title="Cosa cambierebbe la decisione" items={card.what_would_change_the_decision} />}
    <Disclosure title="Dati mancanti" items={d.missing_data} tone="caution" /><Disclosure title="Conflitti" items={d.conflicts} tone="caution" /><Audit detail={detail} />
  </>;
}

function App() {
  const [route, setRoute] = useState(window.location.hash.slice(1) || '/');
  const [importing, setImporting] = useState(false);
  const [evidence, setEvidence] = useState<EvidenceContext | null>(null);
  const heading = useRef<HTMLElement>(null);
  useEffect(() => { const change = () => { setRoute(window.location.hash.slice(1) || '/'); setEvidence(null); }; window.addEventListener('hashchange', change); return () => window.removeEventListener('hashchange', change); }, []);
  useEffect(() => { heading.current?.focus(); window.scrollTo(0, 0); }, [route]);
  const [section = '', recordId] = route.split('/').filter(Boolean);
  const session = useQuery({ queryKey: ['session'], queryFn: ({ signal }) => api.session(signal) });
  const records = useQuery({ queryKey: ['records'], queryFn: ({ signal }) => api.records(signal) });
  const detail = useQuery({ queryKey: ['record', recordId], queryFn: ({ signal }) => api.detail(recordId!, signal), enabled: !!recordId });
  const all = records.data ?? [];
  const nav = [['', 'Home', 'home'], ['analyze', 'Analisi', 'analyze'], ['portfolio', 'Portafoglio', 'portfolio'], ['decisions', 'Decisioni', 'decisions']];
  const title = nav.find(n => n[0] === section)?.[1] ?? 'Dossier';
  const onImport = () => setImporting(true);
  const filtered = all.filter(r => section === 'analyze' ? r.kind === 'opportunity_state' : section === 'portfolio' ? r.kind === 'portfolio_state' : ['marginal_decision', 'replacement_decision', 'policy_constrained_decision', 'position_review'].includes(r.kind));
  return <><a className="skip" href="#main-content" onClick={e => { e.preventDefault(); heading.current?.focus(); }}>Vai al contenuto</a><div className="app-shell"><aside className="sidebar"><a className="brand" href="#/"><span className="brand-symbol">A</span><span>AIE<small>Asymmetric Insight Engine</small></span></a><span className="nav-label">Workspace</span><nav aria-label="Navigazione principale">{nav.map(([path, name, icon]) => <a key={path} href={'#/' + path} aria-current={section === path ? 'page' : undefined}><Icon name={icon} />{name}</a>)}</nav><div className="sidebar-bottom"><span className="mode-label">Locale · Frontend 0.1</span><p>I dati restano nel tuo ambiente AIE.</p><a href="/" className="operator-link">Workspace operatore <Icon name="source" /></a></div></aside>
    <div className="workspace"><header className="topbar"><span>{title}</span><div><span className="topbar-date">{detail.data ? date(detail.data.summary.as_of) : 'Archivio locale'}</span><button className="icon-button" aria-label="Aggiorna l’archivio" disabled={records.isFetching} onClick={() => { void records.refetch(); void session.refetch(); if (recordId) void detail.refetch(); }}><Icon name="refresh" /></button><button className="primary small" disabled={!session.data?.write_enabled} onClick={onImport}>Carica dossier</button></div></header>
      <main id="main-content" tabIndex={-1} ref={heading}>
        {session.isError || records.isError ? <ErrorBox error={session.error || records.error} /> : session.isPending || records.isPending ? <div className="loading" role="status">Apertura dell’archivio AIE…</div> : <>
          {session.data.reference_data && <div className="notice"><strong>Caso dimostrativo</strong> · Dati e ipotesi dei test AIE. Non rappresentano il tuo portafoglio né una raccomandazione finanziaria.</div>}{!session.data.write_enabled && <div className="notice">Archivio in sola lettura. Le richieste al motore sono disabilitate.</div>}
          {recordId ? detail.isPending ? <p role="status">Caricamento del dossier…</p> : detail.isError ? <ErrorBox error={detail.error} /> : detail.data ? <><button className="back text-button" onClick={() => navigate('/' + section)}>← Tutti i dossier</button><div className="boundary-line"><span>Data fissa: {date(detail.data.summary.as_of)}</span><span>{label(detail.data.summary.knowledge_mode)}</span></div>{detail.data.summary.kind === 'opportunity_state' ? <Opportunity key={recordId} detail={detail.data} records={all} evidence={setEvidence} /> : detail.data.summary.kind === 'portfolio_state' ? <Portfolio detail={detail.data} /> : <Decision detail={detail.data} records={all} />}</> : null : section === '' ? <Home records={all} onImport={onImport} /> : <><header className="detail-heading"><span className="eyebrow">Archivio dei dossier</span><h1>{title}</h1><p>Apri una fotografia salvata. La data dell’analisi resta esplicita durante tutto il percorso.</p></header><RecordList records={filtered.slice().reverse()} title={title + ' salvate'} empty="Nessun dossier in questa sezione" /></>}
        </>}
        <footer>AIE · Decisioni tracciabili alle evidenze <span>Nessun invio di ordini</span></footer>
      </main>
    </div></div>{evidence && <EvidenceDrawer context={evidence} close={() => setEvidence(null)} />}{importing && session.data && <ImportDossier session={session.data} close={() => setImporting(false)} />}</>;
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><QueryClientProvider client={client}><App /></QueryClientProvider></React.StrictMode>);
