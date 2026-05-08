/**
 * PolicyChecker — Compliance Dashboard (Light Theme)
 * Frontend logic: rule browsing, entity-detail compliance results
 */

// ── State ────────────────────────────────────────────────────
const state = {
    currentTab: 'rules',
    rules: [],
    rulesPage: 1,
    rulesTotalPages: 1,
    rulesTotal: 0,
    ruleFilter: 'all',
    ruleSearch: '',
    stats: {},
    validating: false,
    // DB state
    dbOnline: false,
    dbEntities: [],
};

// ── Init ─────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    loadStats();
    loadRules();
    checkDbStatus();
    setupTabs();
    setupSearch();
    setupFilters();
});

// ── Tabs ─────────────────────────────────────────────────────
function setupTabs() {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const tab = btn.dataset.tab;
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById(`panel-${tab}`).classList.add('active');
            state.currentTab = tab;
        });
    });
}

// ── Stats ────────────────────────────────────────────────────
async function loadStats() {
    try {
        const res = await fetch('/api/stats');
        const data = await res.json();
        state.stats = data;
        renderStats(data);
    } catch (err) {
        console.error('Failed to load stats:', err);
    }
}

function renderStats(s) {
    document.getElementById('stat-rules').textContent = s.total_rules || 0;
    document.getElementById('stat-shapes').textContent = s.shapes_valid || 0;
    document.getElementById('stat-sentences').textContent = s.sentences_extracted || 0;
    document.getElementById('stat-fol').textContent = s.fol_ok || 0;

    const v = s.pipeline_version || 'unknown';
    document.getElementById('pipeline-version').textContent = `v${v}`;

    const dist = s.type_distribution || {};
    const obl = dist.obligation || 0;
    const proh = dist.prohibition || 0;
    const perm = dist.permission || 0;
    const total = obl + proh + perm;

    if (total > 0) {
        const bar = document.getElementById('type-bar');
        bar.innerHTML = `
            <div class="seg seg-obl" style="flex:${obl}" title="${obl} obligations"></div>
            <div class="seg seg-proh" style="flex:${proh}" title="${proh} prohibitions"></div>
            <div class="seg seg-perm" style="flex:${perm}" title="${perm} permissions"></div>
        `;

        const legend = document.getElementById('type-legend');
        legend.innerHTML = `
            <div class="legend-item"><div class="legend-dot" style="background:var(--rose-500)"></div>${obl} Obl</div>
            <div class="legend-item"><div class="legend-dot" style="background:var(--amber-500)"></div>${proh} Proh</div>
            <div class="legend-item"><div class="legend-dot" style="background:var(--emerald-500)"></div>${perm} Perm</div>
        `;
    }
}

// ── Rules ────────────────────────────────────────────────────
async function loadRules() {
    const params = new URLSearchParams({ page: state.rulesPage, per_page: 15 });
    if (state.ruleFilter !== 'all') params.set('rule_type', state.ruleFilter);
    if (state.ruleSearch) params.set('search', state.ruleSearch);

    try {
        const res = await fetch(`/api/rules?${params}`);
        const data = await res.json();
        state.rules = data.rules;
        state.rulesTotal = data.total;
        state.rulesTotalPages = data.total_pages;
        renderRules();
    } catch (err) {
        console.error('Failed to load rules:', err);
    }
}

function renderRules() {
    const list = document.getElementById('rules-list');
    if (state.rules.length === 0) {
        list.innerHTML = `<div class="empty-state"><div class="icon">📋</div><p>No rules found matching your criteria</p></div>`;
        document.getElementById('pagination').innerHTML = '';
        return;
    }

    list.innerHTML = state.rules.map(r => `
        <div class="rule-card" onclick="showRuleDetail('${r.rule_id}')">
            <span class="rule-id">${r.rule_id}</span>
            <div class="rule-text">${highlightSearch(truncate(r.text, 200))}</div>
            <span class="rule-badge badge-${r.rule_type}">${r.rule_type}</span>
        </div>
    `).join('');

    renderPagination();
}

function renderPagination() {
    const el = document.getElementById('pagination');
    const { rulesPage: p, rulesTotalPages: total, rulesTotal } = state;
    if (total <= 1) { el.innerHTML = ''; return; }

    let html = `<button class="page-btn" onclick="goPage(${p-1})" ${p<=1?'disabled':''}>‹</button>`;
    const pages = getPageRange(p, total);
    pages.forEach(pg => {
        if (pg === '...') html += `<span class="page-info">…</span>`;
        else html += `<button class="page-btn ${pg===p?'active':''}" onclick="goPage(${pg})">${pg}</button>`;
    });
    html += `<button class="page-btn" onclick="goPage(${p+1})" ${p>=total?'disabled':''}>›</button>`;
    html += `<span class="page-info">${state.rulesTotal} rules</span>`;
    el.innerHTML = html;
}

function getPageRange(cur, total) {
    if (total <= 7) return Array.from({length: total}, (_, i) => i+1);
    if (cur <= 3) return [1,2,3,4,'...',total];
    if (cur >= total - 2) return [1,'...',total-3,total-2,total-1,total];
    return [1,'...',cur-1,cur,cur+1,'...',total];
}

function goPage(p) {
    if (p < 1 || p > state.rulesTotalPages) return;
    state.rulesPage = p;
    loadRules();
}

function setupSearch() {
    const input = document.getElementById('rule-search');
    let timeout;
    input.addEventListener('input', () => {
        clearTimeout(timeout);
        timeout = setTimeout(() => { state.ruleSearch = input.value.trim(); state.rulesPage = 1; loadRules(); }, 300);
    });
}

function setupFilters() {
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            state.ruleFilter = btn.dataset.type;
            state.rulesPage = 1;
            loadRules();
        });
    });
}

// ── Rule Detail Modal ────────────────────────────────────────
async function showRuleDetail(ruleId) {
    const overlay = document.getElementById('modal-overlay');
    const body = document.getElementById('modal-body');
    body.innerHTML = `<div class="loading"><div class="spinner"></div> Loading...</div>`;
    overlay.classList.add('active');

    try {
        const res = await fetch(`/api/rules/${ruleId}`);
        const data = await res.json();
        renderRuleDetail(data);
    } catch (err) {
        body.innerHTML = `<div class="empty-state"><p>Failed to load rule details</p></div>`;
    }
}

function renderRuleDetail(data) {
    const r = data.rule;
    const fol = data.fol;
    const shape = data.shacl_shape;

    const body = document.getElementById('modal-body');
    document.getElementById('modal-title').textContent = r.rule_id;

    body.innerHTML = `
        <div class="detail-section">
            <h3>📝 Rule Text</h3>
            <div class="detail-text">${escapeHtml(r.text)}</div>
        </div>

        <div class="detail-section">
            <div class="detail-meta">
                <div class="detail-meta-item">
                    <span class="label">Type</span>
                    <span class="rule-badge badge-${r.rule_type}" style="font-size:0.78rem">${r.rule_type}</span>
                </div>
                <div class="detail-meta-item">
                    <span class="label">Confidence</span>
                    <span style="font-weight:700;color:${r.confidence >= 0.8 ? 'var(--emerald-600)' : 'var(--amber-600)'}">
                        ${(r.confidence * 100).toFixed(0)}%
                    </span>
                </div>
                <div class="detail-meta-item">
                    <span class="label">Source</span>
                    <span style="font-size:0.82rem;color:var(--text-500)">${escapeHtml(r.source_document || 'N/A')}</span>
                </div>
            </div>
        </div>

        ${fol ? `
        <div class="detail-section">
            <h3>🔬 First-Order Logic</h3>
            <pre class="code-block" style="color:var(--violet-500)">${escapeHtml(fol.deontic_formula || fol.formula || '')}</pre>
        </div>` : ''}

        ${shape ? `
        <div class="detail-section">
            <h3>🛡️ SHACL Shape (Turtle)</h3>
            <pre class="code-block">${escapeHtml(shape)}</pre>
        </div>` : `
        <div class="detail-section">
            <h3>🛡️ SHACL Shape</h3>
            <p style="color:var(--text-400);font-size:0.85rem">No shape generated for this rule</p>
        </div>`}
    `;
}

function closeModal() { document.getElementById('modal-overlay').classList.remove('active'); }
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

// ── Data Source Management ────────────────────────────────────

function resetData() {
    if (state.dbOnline) {
        loadFromDatabase();
    } else {
        document.getElementById('data-editor').value = '';
    }
    document.getElementById('results-container').innerHTML = `
        <div class="empty-state"><div class="icon">🛡️</div><p>Submit RDF data to see compliance results</p></div>`;
    document.getElementById('results-timer').textContent = '';
}

// ── Database Status & Entity Loading ─────────────────────────

async function checkDbStatus() {
    const statusEl = document.getElementById('db-status');
    const dot = statusEl.querySelector('.db-dot');
    const label = statusEl.querySelector('.db-label');

    try {
        const res = await fetch('/api/db-status');
        const data = await res.json();

        if (data.ok) {
            state.dbOnline = true;
            dot.classList.remove('offline');
            dot.classList.add('online');
            const count = data.entities || 0;
            label.textContent = `DB Connected (${count} entities)`;

            if (count > 0) {
                await loadDbEntityList();
            }
        } else {
            state.dbOnline = false;
            dot.classList.remove('online');
            dot.classList.add('offline');
            label.textContent = 'DB Offline';
            document.getElementById('btn-load-db').disabled = true;
        }
    } catch (err) {
        state.dbOnline = false;
        dot.classList.remove('online');
        dot.classList.add('offline');
        label.textContent = 'DB Offline';
        document.getElementById('btn-load-db').disabled = true;
    }
}

async function loadDbEntityList() {
    try {
        const res = await fetch('/api/db-entities');
        const data = await res.json();
        state.dbEntities = data.entities || [];
        renderEntityCheckboxes();
    } catch (err) {
        console.error('Failed to load DB entities:', err);
    }
}

function renderEntityCheckboxes() {
    const grid = document.getElementById('entity-checkbox-grid');
    if (state.dbEntities.length === 0) {
        grid.innerHTML = '<div class="loading-sm">No entities in database</div>';
        return;
    }

    const typeIcons = {
        'Student': '🎓', 'PostgraduateStudent': '🎓',
        'Faculty': '👨‍🏫', 'Employee': '👔',
        'Resident': '🏠', 'Committee': '🏛️',
    };

    grid.innerHTML = state.dbEntities.map(e => {
        const icon = typeIcons[e.type] || '👤';
        return `
            <label class="entity-checkbox" title="${escapeHtml(e.label || e.name)}">
                <input type="checkbox" value="${escapeHtml(e.name)}" checked
                       class="entity-cb">
                <span class="cb-content">
                    <span class="cb-icon">${icon}</span>
                    <span class="cb-name">${escapeHtml(e.name)}</span>
                    <span class="cb-type">${escapeHtml(e.type)}</span>
                    <span class="cb-props">${e.property_count} props</span>
                </span>
            </label>`;
    }).join('');
}

function selectAllEntities(checked) {
    document.querySelectorAll('.entity-cb').forEach(cb => {
        cb.checked = checked;
    });
}

function getSelectedEntityNames() {
    const checked = document.querySelectorAll('.entity-cb:checked');
    return Array.from(checked).map(cb => cb.value);
}

async function loadFromDatabase() {
    const btn = document.getElementById('btn-load-db');
    const editor = document.getElementById('data-editor');
    const selected = getSelectedEntityNames();

    if (selected.length === 0) {
        editor.value = '# No entities selected. Check some entities above.';
        return;
    }

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-sm"></span> Loading…';

    try {
        const allSelected = selected.length === state.dbEntities.length;
        const body = allSelected
            ? { entities: 'all' }
            : { entities: selected };

        const res = await fetch('/api/load-from-db', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        const data = await res.json();

        if (data.error) {
            editor.value = `# Error loading from database:\n# ${data.error}`;
        } else {
            editor.value = data.turtle;
            // Flash success on button
            btn.innerHTML = '✓ Loaded!';
            setTimeout(() => {
                btn.innerHTML = '🗄️ Load from Database';
            }, 1500);
        }
    } catch (err) {
        editor.value = `# Failed to load from database:\n# ${err.message}`;
    } finally {
        btn.disabled = false;
        if (btn.innerHTML.includes('Loading')) {
            btn.innerHTML = '🗄️ Load from Database';
        }
    }
}

// ── Compliance Validation ────────────────────────────────────
async function runValidation() {
    const editor = document.getElementById('data-editor');
    const data = editor.value.trim();
    if (!data) return;

    const btn = document.getElementById('validate-btn');
    const container = document.getElementById('results-container');
    const timer = document.getElementById('results-timer');

    btn.disabled = true;
    btn.innerHTML = '<div class="spinner"></div> Validating…';
    container.innerHTML = `<div class="loading"><div class="spinner"></div> Running pyshacl validation…</div>`;
    state.validating = true;

    const t0 = performance.now();

    try {
        const res = await fetch('/api/validate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ data, shapes: 'all' }),
        });
        const result = await res.json();
        const elapsed = ((performance.now() - t0) / 1000).toFixed(1);
        timer.textContent = `${elapsed}s`;

        if (result.error) {
            container.innerHTML = `
                <div class="empty-state" style="color:var(--rose-500)">
                    <div class="icon">⚠️</div>
                    <p>${escapeHtml(result.error)}</p>
                </div>`;
        } else {
            // Parse entities from editor for property display
            const entities = parseEntitiesFromTurtle(data);
            renderResults(result, entities);
        }
    } catch (err) {
        container.innerHTML = `
            <div class="empty-state" style="color:var(--rose-500)">
                <div class="icon">❌</div>
                <p>Request failed: ${escapeHtml(err.message)}</p>
            </div>`;
    } finally {
        btn.disabled = false;
        btn.innerHTML = '🔍 Run Compliance Check';
        state.validating = false;
    }
}

// ── Parse RDF entities from Turtle text ──────────────────────
function parseEntitiesFromTurtle(turtle) {
    const entities = {};
    const lines = turtle.split('\n');
    let current = null;

    for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith('#') || trimmed === '') continue;
        if (trimmed.startsWith('@prefix')) continue;

        // New entity: "ait:Name a ait:Type ;"
        const entityMatch = trimmed.match(/^(ait:\w+)\s+a\s+(ait:\w+)\s*[;.]/);
        if (entityMatch) {
            const name = entityMatch[1].replace('ait:', '');
            const type = entityMatch[2].replace('ait:', '');
            current = name;
            entities[name] = { type, properties: {}, label: '' };
            continue;
        }

        // Property lines: "ait:prop value ;"
        if (current && entities[current]) {
            // Label
            const labelMatch = trimmed.match(/rdfs:label\s+"([^"]+)"/);
            if (labelMatch) {
                entities[current].label = labelMatch[1];
                continue;
            }

            const propMatch = trimmed.match(/^(ait:\w+)\s+(.+?)\s*[;.]\s*$/);
            if (propMatch) {
                const key = propMatch[1].replace('ait:', '');
                let val = propMatch[2];
                if (val === 'true') val = true;
                else if (val === 'false') val = false;
                else val = val.replace(/"/g, '');
                entities[current].properties[key] = val;
            }
        }

        // End of entity
        if (trimmed.endsWith('.')) current = null;
    }

    return entities;
}

// ── Render Results with Entity Cards ─────────────────────────
function renderResults(result, entities) {
    const container = document.getElementById('results-container');
    const violations = result.violations || [];

    // Group violations by entity
    const byEntity = {};
    violations.forEach(v => {
        const name = v.focus_node;
        if (!byEntity[name]) byEntity[name] = [];
        byEntity[name].push(v);
    });

    // Count severities
    const sevCounts = {};
    violations.forEach(v => { sevCounts[v.severity] = (sevCounts[v.severity] || 0) + 1; });

    const conformsClass = result.conforms ? 'pass' : 'fail';
    const conformsText = result.conforms ? '✓ CONFORMING' : '✗ NON-CONFORMING';
    const affectedCount = Object.keys(byEntity).length;
    const cleanCount = Math.max(0, result.total_entities - affectedCount);

    let html = `
        <div class="results-header">
            <span class="conform-badge ${conformsClass}">${conformsText}</span>
        </div>

        <div class="metrics-row">
            <div class="metric-card red"><div class="val">${result.total_violations}</div><div class="lbl">Violations</div></div>
            <div class="metric-card blue"><div class="val">${affectedCount}</div><div class="lbl">Affected</div></div>
            <div class="metric-card green"><div class="val">${cleanCount}</div><div class="lbl">Clean</div></div>
        </div>
    `;

    // Severity pills
    if (Object.keys(sevCounts).length > 0) {
        html += '<div class="sev-pills">';
        if (sevCounts.Violation) html += `<span class="sev-pill violation">🔴 ${sevCounts.Violation} violations</span>`;
        if (sevCounts.Warning) html += `<span class="sev-pill warning">🟡 ${sevCounts.Warning} warnings</span>`;
        if (sevCounts.Info) html += `<span class="sev-pill info">🔵 ${sevCounts.Info} info</span>`;
        html += '</div>';
    }

    // Entity cards — all entities (including clean ones)
    const entityNames = new Set([...Object.keys(entities), ...Object.keys(byEntity)]);
    const sortedNames = [...entityNames].sort((a, b) => {
        const aV = (byEntity[a] || []).length;
        const bV = (byEntity[b] || []).length;
        return bV - aV; // violated first
    });

    html += `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.6rem">
        <span style="font-size:0.78rem;font-weight:600;color:var(--text-500)">${sortedNames.length} entities</span>
        <div style="display:flex;gap:0.4rem">
            <button class="btn btn-ghost" style="padding:0.3rem 0.7rem;font-size:0.72rem" onclick="expandAllEntities()">▼ Expand All</button>
            <button class="btn btn-ghost" style="padding:0.3rem 0.7rem;font-size:0.72rem" onclick="collapseAllEntities()">▲ Collapse All</button>
        </div>
    </div>`;
    html += '<div class="entity-cards">';

    sortedNames.forEach(name => {
        const entity = entities[name] || { type: 'Unknown', properties: {}, label: name };
        const entityViolations = byEntity[name] || [];
        const isClean = entityViolations.length === 0;
        const type = entity.type || 'Unknown';
        const typeClass = getTypeClass(type);
        const initial = name.charAt(0).toUpperCase();
        const displayLabel = entity.label || name;

        html += `
        <div class="entity-card" id="entity-${name}">
            <div class="entity-head" onclick="toggleEntity('${name}')">
                <div class="entity-name-group">
                    <div class="entity-avatar ${typeClass}">${initial}</div>
                    <div>
                        <div class="entity-name">${escapeHtml(displayLabel)}</div>
                        <div class="entity-type-label">${escapeHtml(type)}</div>
                    </div>
                </div>
                <div class="entity-status-pills">
                    ${isClean
                        ? '<span class="entity-clean">✓ Clean</span>'
                        : `<span class="entity-violation-count">${entityViolations.length} violations</span>`
                    }
                    <span class="entity-toggle">▼</span>
                </div>
            </div>
            <div class="entity-body">`;

        // Properties section
        const props = entity.properties;
        if (Object.keys(props).length > 0) {
            html += `
                <div class="props-section">
                    <div class="section-label">📋 Entity Properties</div>
                    <div class="props-grid">`;
            Object.entries(props).forEach(([k, v]) => {
                let valClass = 'val-str';
                let display = v;
                if (v === true) { valClass = 'val-true'; display = '✓ true'; }
                else if (v === false) { valClass = 'val-false'; display = '✗ false'; }
                html += `
                    <div class="prop-item">
                        <span class="prop-key">${escapeHtml(k)}</span>
                        <span class="prop-val ${valClass}">${display}</span>
                    </div>`;
            });
            html += '</div></div>';
        }

        // Violations section
        if (entityViolations.length > 0) {
            html += `
                <div class="props-section">
                    <div class="section-label">⚠️ Policy Violations (${entityViolations.length})</div>
                    <div class="violation-list">`;
            entityViolations.forEach(v => {
                html += `
                    <div class="violation-item sev-${v.severity}">
                        <div class="violation-msg">${escapeHtml(v.message)}</div>
                        <div class="violation-meta">
                            <span>shape: ${escapeHtml(v.source_shape)}</span>
                            <span>path: ${escapeHtml(v.path)}</span>
                        </div>
                    </div>`;
            });
            html += '</div></div>';
        }

        html += '</div></div>';
    });

    html += '</div>';
    container.innerHTML = html;
}

function getTypeClass(type) {
    const t = type.toLowerCase();
    if (t.includes('student')) return 'student';
    if (t.includes('faculty')) return 'faculty';
    if (t.includes('employee')) return 'employee';
    if (t.includes('resident')) return 'resident';
    return 'default';
}

function toggleEntity(name) {
    const card = document.getElementById(`entity-${name}`);
    if (card) card.classList.toggle('open');
}

function expandAllEntities() {
    document.querySelectorAll('.entity-card').forEach(c => c.classList.add('open'));
}

function collapseAllEntities() {
    document.querySelectorAll('.entity-card').forEach(c => c.classList.remove('open'));
}

// ── Utilities ────────────────────────────────────────────────
function truncate(text, max) {
    if (!text) return '';
    const clean = text.replace(/\n/g, ' ').replace(/\s+/g, ' ').trim();
    return clean.length > max ? clean.slice(0, max) + '…' : clean;
}

function highlightSearch(text) {
    if (!state.ruleSearch) return text;
    const q = state.ruleSearch.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    return text.replace(new RegExp(`(${q})`, 'gi'), '<strong>$1</strong>');
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
