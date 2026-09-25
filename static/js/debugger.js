/**
 * PyChronicle Time-Travel Debugger Client Script
 * Handles interactive stepping, timeline scrubbing, active line highlighting,
 * scope variable updates, watch variable tracking, and historical copy-to-workspace.
 */

document.addEventListener('DOMContentLoaded', () => {
    const root = document.getElementById('debugger-root');
    if (!root) return;

    const executionId = parseInt(root.dataset.executionId, 10);
    const totalSteps = parseInt(root.dataset.totalSteps, 10) || 1;
    const isReadonly = root.dataset.isReadonly === 'true';

    let currentStep = 1;
    let watchedVariables = [];

    // UI Elements
    const btnFirst = document.getElementById('btn-step-first');
    const btnPrev = document.getElementById('btn-step-prev');
    const btnNext = document.getElementById('btn-step-next');
    const btnLast = document.getElementById('btn-step-last');
    const stepSlider = document.getElementById('step-slider');
    const currentStepDisplay = document.getElementById('current-step-display');
    const eventTypeBadge = document.getElementById('event-type-badge');
    const lineIndicator = document.getElementById('current-line-indicator');
    const activeScopeTag = document.getElementById('active-scope-tag');
    const variablesTableBody = document.getElementById('variables-table-body');
    const watchTableBody = document.getElementById('watch-table-body');
    const btnToggleWatch = document.getElementById('btn-toggle-watch-input');
    const watchInputBox = document.getElementById('watch-input-box');
    const watchVarInput = document.getElementById('watch-var-input');
    const btnAddWatch = document.getElementById('btn-add-watch');
    const btnCopyWorkspace = document.getElementById('btn-copy-to-workspace');

    // Load step data from backend ReplayEngine
    async function loadStep(stepNum) {
        if (stepNum < 1) stepNum = 1;
        if (stepNum > totalSteps) stepNum = totalSteps;
        currentStep = stepNum;

        // Update Slider and Counter
        if (stepSlider) stepSlider.value = currentStep;
        if (currentStepDisplay) currentStepDisplay.textContent = currentStep;

        // Build query with watched variables
        let url = `/api/executions/${executionId}/step/${currentStep}`;
        if (watchedVariables.length > 0) {
            const params = watchedVariables.map(v => `watch=${encodeURIComponent(v)}`).join('&');
            url += `?${params}`;
        }

        try {
            const res = await fetch(url);
            const data = await res.json();
            if (data.success && data.state) {
                renderStepState(data.state);
            }
        } catch (err) {
            console.error('Failed to load step state:', err);
        }
    }

    function renderStepState(state) {
        // 1. Highlight Active Execution Line
        document.querySelectorAll('.code-line-row.active-line').forEach(el => el.classList.remove('active-line'));
        if (state.line) {
            const lineRow = document.getElementById(`code-line-${state.line}`);
            if (lineRow) {
                lineRow.classList.add('active-line');
                lineRow.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }
            if (lineIndicator) lineIndicator.textContent = `Line ${state.line}`;
        } else {
            if (lineIndicator) lineIndicator.textContent = 'Line -';
        }

        // 2. Update Event Type Badge
        if (eventTypeBadge) {
            eventTypeBadge.textContent = `event: ${state.event || 'line'}`;
        }

        // 3. Update Scope Tag
        if (activeScopeTag) {
            activeScopeTag.textContent = `Scope: ${state.active_scope || '<module>'}`;
        }

        // 4. Render Active Scope Variables
        if (variablesTableBody) {
            const vars = state.active_variables || {};
            const keys = Object.keys(vars);
            if (keys.length === 0) {
                variablesTableBody.innerHTML = '<tr><td colspan="2" class="text-muted">No variables in current scope.</td></tr>';
            } else {
                let html = '';
                for (const key of keys) {
                    const val = escapeHtml(String(vars[key]));
                    html += `
                        <tr>
                            <td class="var-name text-accent font-semibold">${escapeHtml(key)}</td>
                            <td class="var-val font-mono">${val}</td>
                        </tr>
                    `;
                }
                variablesTableBody.innerHTML = html;
            }
        }

        // 5. Render Watched Variables
        renderWatchTable(state.watch_values || {});
    }

    function renderWatchTable(watchValues) {
        if (!watchTableBody) return;
        if (watchedVariables.length === 0) {
            watchTableBody.innerHTML = '<tr id="empty-watch-row"><td colspan="3" class="text-muted">No variables being watched. Click + Add Variable above.</td></tr>';
            return;
        }

        let html = '';
        for (const varName of watchedVariables) {
            const val = watchValues[varName] !== undefined && watchValues[varName] !== null 
                ? escapeHtml(String(watchValues[varName])) 
                : '<span class="text-muted">&lt;undefined&gt;</span>';
            
            html += `
                <tr>
                    <td class="var-name text-accent font-semibold">${escapeHtml(varName)}</td>
                    <td class="var-val font-mono">${val}</td>
                    <td class="text-right">
                        <button type="button" class="btn btn-xs btn-danger btn-remove-watch" data-var="${escapeHtml(varName)}">✕</button>
                    </td>
                </tr>
            `;
        }
        watchTableBody.innerHTML = html;

        // Bind delete events
        document.querySelectorAll('.btn-remove-watch').forEach(btn => {
            btn.addEventListener('click', () => {
                const targetVar = btn.dataset.var;
                watchedVariables = watchedVariables.filter(v => v !== targetVar);
                loadStep(currentStep);
            });
        });
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Step Control Listeners
    if (btnFirst) btnFirst.addEventListener('click', () => loadStep(1));
    if (btnPrev) btnPrev.addEventListener('click', () => loadStep(currentStep - 1));
    if (btnNext) btnNext.addEventListener('click', () => loadStep(currentStep + 1));
    if (btnLast) btnLast.addEventListener('click', () => loadStep(totalSteps));

    if (stepSlider) {
        stepSlider.addEventListener('input', (e) => {
            loadStep(parseInt(e.target.value, 10));
        });
    }

    // Keyboard Arrow Controls
    document.addEventListener('keydown', (e) => {
        // Only trigger if not focused in an input
        if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) return;

        if (e.key === 'ArrowLeft') {
            e.preventDefault();
            loadStep(currentStep - 1);
        } else if (e.key === 'ArrowRight') {
            e.preventDefault();
            loadStep(currentStep + 1);
        } else if (e.key === 'Home') {
            e.preventDefault();
            loadStep(1);
        } else if (e.key === 'End') {
            e.preventDefault();
            loadStep(totalSteps);
        }
    });

    // Watch Variable Toggle & Add
    if (btnToggleWatch && watchInputBox) {
        btnToggleWatch.addEventListener('click', () => {
            const isHidden = watchInputBox.style.display === 'none';
            watchInputBox.style.display = isHidden ? 'flex' : 'none';
            if (isHidden && watchVarInput) watchVarInput.focus();
        });
    }

    function addWatchVariable() {
        if (!watchVarInput) return;
        const varName = watchVarInput.value.trim();
        if (varName && !watchedVariables.includes(varName)) {
            watchedVariables.push(varName);
            watchVarInput.value = '';
            loadStep(currentStep);
        }
    }

    if (btnAddWatch) btnAddWatch.addEventListener('click', addWatchVariable);
    if (watchVarInput) {
        watchVarInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                addWatchVariable();
            }
        });
    }

    // Copy to Workspace Action (Historical Replay)
    if (btnCopyWorkspace) {
        btnCopyWorkspace.addEventListener('click', async () => {
            try {
                const res = await fetch(`/api/executions/${executionId}/copy`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                });
                const data = await res.json();
                if (data.success && data.redirect_url) {
                    window.location.href = data.redirect_url;
                } else {
                    alert(`Failed to copy to workspace: ${data.error || 'Unknown error'}`);
                }
            } catch (err) {
                alert(`Error copying execution: ${err}`);
            }
        });
    }

    // Initial step load
    loadStep(1);
});
