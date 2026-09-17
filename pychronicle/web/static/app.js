/**
 * PyChronicle — Advanced Developer UI
 * Programming Workspace + Focused Debugger + Immutable History
 */

(function () {
    'use strict';

    // Application State
    const state = {
        currentView: 'workspace', // 'workspace' | 'debug' | 'history' | 'historical_run'
        programs: [],
        activeProgram: null,
        activeExecution: null,
        historicalExecution: null,
        currentStep: 1,
        totalSteps: 1,
        watchVars: ['num', 'original', 'reverse', 'temp', 'digit', 'result', 'total', 'results'],
        isPlaying: false,
        playInterval: null,
        playSpeedMs: 500,
        historyRuns: [],
        historyFilter: 'ALL',
        isDirty: false,
    };

    // Code Templates
    const TEMPLATES = {
        palindrome: `num = 12321

original = num
reverse = 0
temp = num

while temp > 0:
    digit = temp % 10
    reverse = reverse * 10 + digit
    temp = temp // 10

if original == reverse:
    result = "Palindrome"
else:
    result = "Not Palindrome"

print("Number:", original)
print("Reversed:", reverse)
print("Result:", result)
`,
        factorial: `def compute_factorials(limit):
    results = []
    total = 1
    for n in range(1, limit + 1):
        total *= n
        results.append(total)
    return results

def main():
    facts = compute_factorials(4)
    print("Factorials:", facts)

if __name__ == "__main__":
    main()
`,
        fibonacci: `def fib(n):
    if n <= 1:
        return n
    return fib(n - 1) + fib(n - 2)

def main():
    vals = [fib(i) for i in range(7)]
    print("Fibonacci sequence:", vals)

if __name__ == "__main__":
    main()
`,
        calculator: `def calculate(op, a, b):
    ops = {
        "+": a + b,
        "-": a - b,
        "*": a * b,
        "/": a / b if b != 0 else None
    }
    return ops.get(op)

def main():
    res = calculate("*", 6, 7)
    print("6 * 7 =", res)

if __name__ == "__main__":
    main()
`,
        empty: `# Python script\n\ndef main():\n    print("Hello PyChronicle")\n\nif __name__ == "__main__":\n    main()\n`
    };

    // DOM Elements
    const elements = {
        // Views
        viewWorkspace: document.getElementById('viewWorkspace'),
        viewDebug: document.getElementById('viewDebug'),
        viewHistory: document.getElementById('viewHistory'),
        viewHistoricalRun: document.getElementById('viewHistoricalRun'),

        // Header
        headerProgramName: document.getElementById('headerProgramName'),
        headerVersionBadge: document.getElementById('headerVersionBadge'),
        headerDirtyIndicator: document.getElementById('headerDirtyIndicator'),
        headerStatusPill: document.getElementById('headerStatusPill'),
        btnNavHome: document.getElementById('btnNavHome'),
        btnNavSave: document.getElementById('btnNavSave'),
        btnNavRun: document.getElementById('btnNavRun'),
        btnNavDebug: document.getElementById('btnNavDebug'),
        btnNavHistory: document.getElementById('btnNavHistory'),
        btnNavBack: document.getElementById('btnNavBack'),
        btnNavQuit: document.getElementById('btnNavQuit'),
        btnDebugHome: document.getElementById('btnDebugHome'),
        btnHistoryHome: document.getElementById('btnHistoryHome'),
        btnHistRunHome: document.getElementById('btnHistRunHome'),

        // Workspace
        sidebarProgramCount: document.getElementById('sidebarProgramCount'),
        workspaceSearchInput: document.getElementById('workspaceSearchInput'),
        btnSidebarNewProgram: document.getElementById('btnSidebarNewProgram'),
        workspaceProgramList: document.getElementById('workspaceProgramList'),
        workspaceTabFilename: document.getElementById('workspaceTabFilename'),
        workspaceCursorPos: document.getElementById('workspaceCursorPos'),
        workspaceGutter: document.getElementById('workspaceGutter'),
        workspaceTextarea: document.getElementById('workspaceTextarea'),
        workspaceResizer: document.getElementById('workspaceResizer'),
        workspaceEditorPane: document.getElementById('workspaceEditorPane'),
        workspaceConsolePane: document.getElementById('workspaceConsolePane'),
        metaStatus: document.getElementById('metaStatus'),
        metaDuration: document.getElementById('metaDuration'),
        metaSession: document.getElementById('metaSession'),
        workspaceStdout: document.getElementById('workspaceStdout'),

        // Debug View
        debugProgramTitle: document.getElementById('debugProgramTitle'),
        btnDebugExit: document.getElementById('btnDebugExit'),
        debugCurrentLineIndicator: document.getElementById('debugCurrentLineIndicator'),
        debugGutter: document.getElementById('debugGutter'),
        debugSourceCode: document.getElementById('debugSourceCode'),
        debugActiveScopeIndicator: document.getElementById('debugActiveScopeIndicator'),
        debugVariablesContainer: document.getElementById('debugVariablesContainer'),
        debugWatchInput: document.getElementById('debugWatchInput'),
        btnDebugAddWatch: document.getElementById('btnDebugAddWatch'),
        btnDebugClearWatches: document.getElementById('btnDebugClearWatches'),
        debugWatchChips: document.getElementById('debugWatchChips'),
        debugStepBadge: document.getElementById('debugStepBadge'),
        btnDebugFirst: document.getElementById('btnDebugFirst'),
        btnDebugPrev: document.getElementById('btnDebugPrev'),
        btnDebugPlay: document.getElementById('btnDebugPlay'),
        btnDebugNext: document.getElementById('btnDebugNext'),
        btnDebugLast: document.getElementById('btnDebugLast'),
        debugSlider: document.getElementById('debugSlider'),
        debugDeltaSummary: document.getElementById('debugDeltaSummary'),

        // History View
        btnHistoryBack: document.getElementById('btnHistoryBack'),
        historySearchInput: document.getElementById('historySearchInput'),
        historyChips: document.querySelectorAll('[data-history-filter]'),
        historyRunsContainer: document.getElementById('historyRunsContainer'),

        // Historical Run View
        histRunTitle: document.getElementById('histRunTitle'),
        btnHistRunBackToHistory: document.getElementById('btnHistRunBackToHistory'),
        btnHistCopyToWorkspace: document.getElementById('btnHistCopyToWorkspace'),
        btnHistRunClose: document.getElementById('btnHistRunClose'),
        histCurrentLineIndicator: document.getElementById('histCurrentLineIndicator'),
        histGutter: document.getElementById('histGutter'),
        histSourceCode: document.getElementById('histSourceCode'),
        histOutputStatus: document.getElementById('histOutputStatus'),
        histStoredStdout: document.getElementById('histStoredStdout'),
        histVarsContainer: document.getElementById('histVarsContainer'),
        histStepBadge: document.getElementById('histStepBadge'),
        btnHistFirst: document.getElementById('btnHistFirst'),
        btnHistPrev: document.getElementById('btnHistPrev'),
        btnHistNext: document.getElementById('btnHistNext'),
        btnHistLast: document.getElementById('btnHistLast'),
        histSlider: document.getElementById('histSlider'),
        histDeltaSummary: document.getElementById('histDeltaSummary'),

        // Modals
        modalNewProgram: document.getElementById('modalNewProgram'),
        btnCloseNewProg: document.getElementById('btnCloseNewProg'),
        btnCancelNewProg: document.getElementById('btnCancelNewProg'),
        btnSubmitNewProg: document.getElementById('btnSubmitNewProg'),
        inputNewProgName: document.getElementById('inputNewProgName'),
        inputNewProgDesc: document.getElementById('inputNewProgDesc'),
        selectNewProgTemplate: document.getElementById('selectNewProgTemplate'),

        modalWatchPrompt: document.getElementById('modalWatchPrompt'),
        btnCloseWatchModal: document.getElementById('btnCloseWatchModal'),
        btnCancelWatchModal: document.getElementById('btnCancelWatchModal'),
        btnSubmitWatchModal: document.getElementById('btnSubmitWatchModal'),
        inputWatchVarName: document.getElementById('inputWatchVarName'),

        toastContainer: document.getElementById('toastContainer'),
    };

    // =========================================================================
    // API Client
    // =========================================================================

    async function api(endpoint, options = {}) {
        try {
            const res = await fetch(endpoint, {
                headers: { 'Content-Type': 'application/json', ...options.headers },
                ...options,
            });
            const data = await res.json();
            if (!res.ok) {
                throw new Error(data.error || `HTTP ${res.status}`);
            }
            return data;
        } catch (err) {
            console.error(`[API Error] ${endpoint}:`, err);
            throw err;
        }
    }

    function showToast(msg, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = msg;
        elements.toastContainer.appendChild(toast);
        setTimeout(() => {
            toast.style.opacity = '0';
            setTimeout(() => toast.remove(), 200);
        }, 3000);
    }

    function escapeHtml(str) {
        if (str === null || str === undefined) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function formatDate(isoStr) {
        if (!isoStr) return 'Never';
        try {
            const d = new Date(isoStr);
            return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
        } catch (e) {
            return isoStr;
        }
    }

    // =========================================================================
    // View Router & State Transitions
    // =========================================================================

    function switchView(viewName) {
        stopPlayback();
        state.currentView = viewName;

        elements.viewWorkspace.classList.remove('active');
        elements.viewDebug.classList.remove('active');
        elements.viewHistory.classList.remove('active');
        elements.viewHistoricalRun.classList.remove('active');

        // Dynamically adjust header buttons per view: Universal Home + Minimal Toolbars
        if (elements.btnNavHome) elements.btnNavHome.style.display = 'inline-flex';
        if (elements.btnNavSave) elements.btnNavSave.style.display = (viewName === 'workspace') ? 'inline-flex' : 'none';
        if (elements.btnNavRun) elements.btnNavRun.style.display = (viewName === 'workspace') ? 'inline-flex' : 'none';
        if (elements.btnNavDebug) elements.btnNavDebug.style.display = (viewName === 'workspace') ? 'inline-flex' : 'none';
        if (elements.btnNavHistory) elements.btnNavHistory.style.display = (viewName === 'workspace') ? 'inline-flex' : 'none';

        if (viewName === 'workspace') {
            elements.viewWorkspace.classList.add('active');
            updateHeader();
        } else if (viewName === 'debug') {
            elements.viewDebug.classList.add('active');
            setupDebugView();
        } else if (viewName === 'history') {
            elements.viewHistory.classList.add('active');
            loadHistoryRuns();
        } else if (viewName === 'historical_run') {
            elements.viewHistoricalRun.classList.add('active');
            setupHistoricalRunView();
        }
    }

    function updateHeader() {
        if (!state.activeProgram) {
            elements.headerProgramName.textContent = 'No program selected';
            elements.headerVersionBadge.textContent = 'v0';
            elements.headerStatusPill.className = 'status-pill status-ready';
            elements.headerStatusPill.textContent = 'READY';
            elements.headerDirtyIndicator.classList.add('hidden');
            elements.workspaceTabFilename.textContent = 'untitled.py';
            return;
        }

        elements.headerProgramName.textContent = state.activeProgram.name;
        elements.headerVersionBadge.textContent = `v${state.activeProgram.version_count || 1}`;
        elements.workspaceTabFilename.textContent = `${state.activeProgram.name.toLowerCase().replace(/\\s+/g, '_')}.py`;

        if (state.isDirty) {
            elements.headerDirtyIndicator.classList.remove('hidden');
        } else {
            elements.headerDirtyIndicator.classList.add('hidden');
        }

        let st = state.activeProgram.last_status || 'READY';
        if (st === 'NEVER_RUN') st = 'READY';
        elements.headerStatusPill.textContent = st.replace('_', ' ');
        if (st === 'SUCCESS') {
            elements.headerStatusPill.className = 'status-pill status-success';
        } else if (['USER_ERROR', 'PYCHRONICLE_ERROR', 'FAILED'].includes(st)) {
            elements.headerStatusPill.className = 'status-pill status-user-error';
        } else {
            elements.headerStatusPill.className = 'status-pill status-ready';
        }
    }

    // =========================================================================
    // Program Workspace Management
    // =========================================================================

    async function loadPrograms(preserveActive = true) {
        try {
            const res = await api('/api/programs');
            state.programs = res.programs || [];
            renderProgramList();

            if (state.programs.length > 0) {
                if (!preserveActive || !state.activeProgram) {
                    await selectProgram(state.programs[0].id);
                } else {
                    const found = state.programs.find(p => p.id === state.activeProgram.id);
                    if (found) {
                        state.activeProgram = found;
                        updateHeader();
                    } else {
                        await selectProgram(state.programs[0].id);
                    }
                }
            } else {
                state.activeProgram = null;
                elements.workspaceTextarea.value = '';
                updateWorkspaceGutter();
                updateHeader();
            }
        } catch (err) {
            showToast(`Failed to load programs: ${err.message}`, 'error');
        }
    }

    function renderProgramList() {
        elements.sidebarProgramCount.textContent = state.programs.length;
        const list = elements.workspaceProgramList;
        list.innerHTML = '';

        const query = (elements.workspaceSearchInput.value || '').toLowerCase().trim();
        const filtered = state.programs.filter(p => {
            if (!query) return true;
            return p.name.toLowerCase().includes(query) || (p.description || '').toLowerCase().includes(query);
        });

        if (filtered.length === 0) {
            list.innerHTML = `<div class="empty-state">No programs match search.</div>`;
            return;
        }

        filtered.forEach(prog => {
            const item = document.createElement('div');
            item.className = `prog-item ${state.activeProgram && state.activeProgram.id === prog.id ? 'active' : ''}`;
            item.onclick = () => selectProgram(prog.id);

            let statusClass = 'text-muted';
            let statusText = prog.last_status || 'Ready';
            if (statusText === 'SUCCESS') {
                statusClass = 'text-success';
            } else if (['USER_ERROR', 'FAILED'].includes(statusText)) {
                statusClass = 'text-danger';
            }

            item.innerHTML = `
                <div class="prog-item-title">${escapeHtml(prog.name)}</div>
                <div class="prog-item-meta">
                    <span class="${statusClass}">● ${statusText}</span>
                    <span>${formatDate(prog.last_run_at || prog.updated_at)}</span>
                </div>
            `;
            list.appendChild(item);
        });
    }

    async function selectProgram(progId) {
        try {
            const res = await api(`/api/programs/${progId}`);
            state.activeProgram = res.program;
            elements.workspaceTextarea.value = state.activeProgram.source_code;
            state.isDirty = false;
            updateWorkspaceGutter();
            updateHeader();
            renderProgramList();

            // Reset console output
            if (res.executions && res.executions.length > 0) {
                const latest = res.executions[0];
                state.activeExecution = latest;
                elements.metaStatus.textContent = `Status: ${latest.status}`;
                elements.metaDuration.textContent = `Execution: ${latest.duration_ms || 0} ms`;
                elements.metaSession.textContent = `Session: #${latest.debug_session_id || latest.id}`;
                elements.workspaceStdout.textContent = latest.stdout || '(No output recorded)';
            } else {
                state.activeExecution = null;
                elements.metaStatus.textContent = 'Status: Ready';
                elements.metaDuration.textContent = 'Execution: -';
                elements.metaSession.textContent = 'Session: -';
                elements.workspaceStdout.textContent = 'Ready. Click \'▶ Run\' to execute code or \'🐞 Debug\' for time-travel inspection.';
            }
        } catch (err) {
            showToast(`Failed to select program: ${err.message}`, 'error');
        }
    }

    async function saveProgram() {
        if (!state.activeProgram) {
            openNewProgramModal();
            return;
        }

        const code = elements.workspaceTextarea.value;
        try {
            const res = await api(`/api/programs/${state.activeProgram.id}`, {
                method: 'PUT',
                body: JSON.stringify({ source_code: code }),
            });
            state.activeProgram = res.program;
            state.isDirty = false;
            updateHeader();
            await loadPrograms(true);
            showToast(`Saved '${state.activeProgram.name}' (v${state.activeProgram.version_count})`, 'success');
        } catch (err) {
            showToast(`Save failed: ${err.message}`, 'error');
        }
    }

    function updateWorkspaceGutter() {
        const lines = elements.workspaceTextarea.value.split('\n');
        let gutterHtml = '';
        for (let i = 1; i <= lines.length; i++) {
            gutterHtml += `<div class="gutter-num">${i}</div>`;
        }
        elements.workspaceGutter.innerHTML = gutterHtml;
    }

    // =========================================================================
    // Execution & Run
    // =========================================================================

    async function runActiveProgram(isDebugTrigger = false) {
        if (!state.activeProgram) return;

        const code = elements.workspaceTextarea.value;
        elements.headerStatusPill.className = 'status-pill status-running';
        elements.headerStatusPill.textContent = 'RUNNING...';

        try {
            const res = await api(`/api/programs/${state.activeProgram.id}/run`, {
                method: 'POST',
                body: JSON.stringify({
                    source_code: code,
                    watch_vars: state.watchVars,
                    auto_save: true,
                }),
            });

            state.activeExecution = res;
            state.isDirty = false;

            // Update Console Output in Workspace
            elements.metaStatus.textContent = `Status: ${res.status}`;
            elements.metaDuration.textContent = `Execution: ${res.duration_ms || 0} ms`;
            elements.metaSession.textContent = `Session: #${res.session_id || '-'}`;
            elements.workspaceStdout.textContent = res.stdout || (res.error ? `Error: ${res.error}` : '(Execution produced no output)');

            updateHeader();
            await loadPrograms(true);

            if (isDebugTrigger) {
                switchView('debug');
            } else {
                if (res.status === 'SUCCESS') {
                    showToast(`Run complete (${res.duration_ms} ms)`, 'success');
                } else {
                    showToast(`Run failed: ${res.status}`, 'error');
                }
            }
        } catch (err) {
            showToast(`Execution failed: ${err.message}`, 'error');
            elements.workspaceStdout.textContent = `Execution Error: ${err.message}`;
            updateHeader();
        }
    }

    // =========================================================================
    // VIEW 2: FOCUSED DEBUGGER WORKSPACE
    // =========================================================================

    async function setupDebugView() {
        if (!state.activeProgram) return;
        elements.debugProgramTitle.textContent = state.activeProgram.name;

        // If not executed yet, execute first
        if (!state.activeExecution || state.isDirty) {
            await runActiveProgram(false);
        }

        const exec = state.activeExecution;
        state.totalSteps = exec.total_steps || exec.step_count || 1;

        // Render source code in debug panel
        const code = exec.source_snapshot || state.activeProgram.source_code;
        renderDebugSource(code, elements.debugGutter, elements.debugSourceCode);

        // Setup slider
        elements.debugSlider.min = 1;
        elements.debugSlider.max = state.totalSteps;

        // Go to Step 1
        await timeTravel(1, 'debug');
    }

    function renderDebugSource(sourceCode, gutterElem, codeElem) {
        const lines = sourceCode.split('\n');
        let gutterHtml = '';
        lines.forEach((_, idx) => {
            gutterHtml += `<div class="gutter-num" data-line="${idx + 1}">${idx + 1}</div>`;
        });
        gutterElem.innerHTML = gutterHtml;
        codeElem.textContent = sourceCode;
    }

    async function timeTravel(stepNum, mode = 'debug') {
        const exec = mode === 'debug' ? state.activeExecution : state.historicalExecution;
        if (!exec) return;

        const execId = exec.execution_id || exec.id;
        const targetStep = Math.max(1, Math.min(stepNum, state.totalSteps));
        state.currentStep = targetStep;

        const watchQuery = state.watchVars.join(',');
        try {
            const replayState = await api(`/api/executions/${execId}/replay/${targetStep}?watch=${encodeURIComponent(watchQuery)}`);

            if (mode === 'debug') {
                elements.debugStepBadge.textContent = `STEP ${targetStep} / ${state.totalSteps}`;
                elements.debugSlider.value = targetStep;
                elements.debugCurrentLineIndicator.textContent = `Line: ${replayState.line || '-'}`;
                elements.debugActiveScopeIndicator.textContent = `Scope: ${replayState.active_scope || '<module>'}`;

                // Highlight active source line
                highlightLine(replayState.line, elements.debugGutter, elements.debugSourceCode);

                // Render current step variables
                renderCurrentStepVariables(replayState, elements.debugVariablesContainer);

                // Render Watch Chips
                renderWatchChips(replayState.watch_values || {}, replayState.changes || {}, elements.debugWatchChips);

                // Delta summary
                updateDeltaSummary(replayState, elements.debugDeltaSummary);

            } else if (mode === 'historical') {
                elements.histStepBadge.textContent = `STEP ${targetStep} / ${state.totalSteps}`;
                elements.histSlider.value = targetStep;
                elements.histCurrentLineIndicator.textContent = `Line: ${replayState.line || '-'}`;

                // Highlight active source line
                highlightLine(replayState.line, elements.histGutter, elements.histSourceCode);

                // Render variables & watches in historical strip
                renderHistoricalVariables(replayState, elements.histVarsContainer);

                // Delta summary
                updateDeltaSummary(replayState, elements.histDeltaSummary);
            }
        } catch (err) {
            console.error('Time-travel step failed:', err);
        }
    }

    function highlightLine(lineno, gutterElem, codeElem) {
        const lines = gutterElem.querySelectorAll('.gutter-num');
        lines.forEach(lineEl => {
            if (parseInt(lineEl.dataset.line, 10) === lineno) {
                lineEl.classList.add('active-line');
            } else {
                lineEl.classList.remove('active-line');
            }
        });
    }

    function renderCurrentStepVariables(replayState, container) {
        const scopes = replayState.scopes || {};
        const activeScope = replayState.active_scope || '<module>';
        const changes = replayState.changes || {};

        container.innerHTML = '';
        const currentVars = scopes[activeScope] || {};
        const varKeys = Object.keys(currentVars);

        if (varKeys.length === 0) {
            container.innerHTML = `<div class="empty-state">No active variables in current scope (${activeScope}).</div>`;
            return;
        }

        let rowsHtml = '';
        varKeys.forEach(vName => {
            const val = currentVars[vName];
            const chg = changes[vName];
            let deltaTag = '';
            if (chg) {
                const op = chg.operation;
                const cls = op === 'CREATE' ? 'delta-create' : (op === 'UPDATE' ? 'delta-update' : 'delta-delete');
                deltaTag = `<span class="delta-badge ${cls}">${op}</span>`;
            }

            rowsHtml += `
                <tr>
                    <td class="var-cell-name">${escapeHtml(vName)}</td>
                    <td class="var-cell-val">${escapeHtml(val)}</td>
                    <td>${deltaTag}</td>
                </tr>
            `;
        });

        container.innerHTML = `
            <table class="vars-table">
                <thead>
                    <tr><th>Variable</th><th>Value</th><th>Delta</th></tr>
                </thead>
                <tbody>${rowsHtml}</tbody>
            </table>
        `;
    }

    function renderWatchChips(watchValues, changes, container) {
        container.innerHTML = '';
        if (state.watchVars.length === 0) {
            container.innerHTML = '<span class="text-muted text-sm">No watched variables. Click "+ Add Watch" to track variables.</span>';
            return;
        }

        state.watchVars.forEach(vName => {
            const val = watchValues[vName];
            const chg = changes ? changes[vName] : null;
            const isUndef = val === undefined || val === null;

            const chip = document.createElement('div');
            chip.className = 'watch-chip';

            let deltaMarker = '';
            if (chg) {
                const op = chg.operation;
                const cls = op === 'CREATE' ? 'delta-create' : (op === 'UPDATE' ? 'delta-update' : 'delta-delete');
                deltaMarker = `<span class="delta-badge ${cls}" style="margin-left:4px;">${op}</span>`;
            }

            chip.innerHTML = `
                <span class="watch-chip-name">${escapeHtml(vName)}</span>
                <span>=</span>
                <span class="watch-chip-val ${isUndef ? 'text-muted' : ''}">${isUndef ? '&lt;undefined&gt;' : escapeHtml(val)}</span>
                ${deltaMarker}
                <span class="watch-chip-del" title="Remove watch" onclick="window.PyChronicleApp.removeWatch('${escapeHtml(vName)}')">✕</span>
            `;
            container.appendChild(chip);
        });
    }

    function updateDeltaSummary(replayState, badgeElem) {
        const changes = replayState.changes || {};
        const changeKeys = Object.keys(changes);
        if (changeKeys.length > 0) {
            const first = changeKeys[0];
            const chg = changes[first];
            badgeElem.textContent = `${first}: ${chg.old || 'null'} -> ${chg.new || 'null'} (${chg.operation})`;
            badgeElem.style.display = 'inline-block';
        } else if (replayState.return_value) {
            badgeElem.textContent = `Return Value: ${replayState.return_value}`;
            badgeElem.style.display = 'inline-block';
        } else {
            badgeElem.textContent = 'No variable changes';
        }
    }

    // =========================================================================
    // VIEW 3: HISTORY WORKSPACE
    // =========================================================================

    async function loadHistoryRuns() {
        const container = elements.historyRunsContainer;
        container.innerHTML = '<div class="empty-state">Loading history runs...</div>';

        try {
            const query = (elements.historySearchInput.value || '').trim();
            const res = await api(`/api/history?search=${encodeURIComponent(query)}&status=${state.historyFilter}`);
            state.historyRuns = res.executions || [];

            container.innerHTML = '';
            if (state.historyRuns.length === 0) {
                container.innerHTML = '<div class="empty-state">No execution runs found.</div>';
                return;
            }

            state.historyRuns.forEach((run, idx) => {
                const card = document.createElement('div');
                card.className = 'history-card';

                const statusClass = run.status === 'SUCCESS' ? 'text-success' : 'text-danger';
                const runTitle = `${escapeHtml(run.program_name)} — Run #${state.historyRuns.length - idx}`;

                card.innerHTML = `
                    <div class="history-card-header">
                        <span class="history-clickable-title" onclick="window.PyChronicleApp.openHistoricalRun(${run.id})">${runTitle}</span>
                        <span class="${statusClass}"><strong>${run.status}</strong></span>
                    </div>
                    <div class="history-card-meta">
                        <span>Started: ${formatDate(run.started_at)}</span>
                        <span>Duration: ${run.duration_ms || 0} ms</span>
                        <span>Steps: ${run.step_count || 0}</span>
                        <span>Version: v${run.version_number || 1}</span>
                    </div>
                    <div class="history-card-output">${escapeHtml(run.stdout || '(No stdout output)')}</div>
                `;
                container.appendChild(card);
            });
        } catch (err) {
            showToast(`Failed to load history: ${err.message}`, 'error');
        }
    }

    // =========================================================================
    // VIEW 4: HISTORICAL EXECUTION VIEW (READ ONLY)
    // =========================================================================

    async function openHistoricalRun(executionId) {
        try {
            const res = await api(`/api/executions/${executionId}`);
            state.historicalExecution = res.execution;
            switchView('historical_run');
        } catch (err) {
            showToast(`Failed to open historical run: ${err.message}`, 'error');
        }
    }

    async function setupHistoricalRunView() {
        const run = state.historicalExecution;
        if (!run) return;

        elements.histRunTitle.textContent = `${run.program_name} — Run #${run.id}`;
        elements.histOutputStatus.textContent = run.status;
        elements.histOutputStatus.className = run.status === 'SUCCESS' ? 'meta-tag text-success' : 'meta-tag text-danger';
        elements.histStoredStdout.textContent = run.stdout || '(No stdout output recorded)';

        state.totalSteps = run.total_steps || run.step_count || 1;
        elements.histSlider.min = 1;
        elements.histSlider.max = state.totalSteps;

        // Render Immutable Source Snapshot
        renderDebugSource(run.source_snapshot, elements.histGutter, elements.histSourceCode);

        // Go to Step 1
        await timeTravel(1, 'historical');
    }

    function renderHistoricalVariables(replayState, container) {
        const scopes = replayState.scopes || {};
        const activeScope = replayState.active_scope || '<module>';
        const currentVars = scopes[activeScope] || {};

        let html = `<div style="font-size:11px; color:var(--text-muted); margin-bottom:4px;"><strong>Historical Variables (Scope: ${activeScope})</strong></div>`;
        html += '<div style="display:flex; flex-wrap:wrap; gap:8px;">';

        const keys = Object.keys(currentVars);
        if (keys.length === 0) {
            html += '<span class="text-muted text-sm">(Empty scope variables)</span>';
        } else {
            keys.forEach(k => {
                html += `<div class="watch-chip"><span class="watch-chip-name">${escapeHtml(k)}</span> = <span class="watch-chip-val">${escapeHtml(currentVars[k])}</span></div>`;
            });
        }
        html += '</div>';
        container.innerHTML = html;
    }

    async function copyHistoricalRunToWorkspace() {
        const run = state.historicalExecution;
        if (!run) return;

        try {
            const res = await api(`/api/executions/${run.id}/copy-to-workspace`, {
                method: 'POST',
                body: JSON.stringify({}),
            });
            showToast(`Copied to workspace as '${res.program.name}'`, 'success');
            await loadPrograms(false);
            await selectProgram(res.program.id);
            switchView('workspace');
        } catch (err) {
            showToast(`Copy failed: ${err.message}`, 'error');
        }
    }

    // =========================================================================
    // Watch Variables Management
    // =========================================================================

    function addWatch(varName) {
        const clean = (varName || elements.debugWatchInput.value || '').trim();
        if (!clean) return;
        if (!state.watchVars.includes(clean)) {
            state.watchVars.push(clean);
            elements.debugWatchInput.value = '';
            if (state.currentView === 'debug') {
                timeTravel(state.currentStep, 'debug');
            }
            showToast(`Watching '${clean}'`, 'info');
        }
    }

    function removeWatch(varName) {
        state.watchVars = state.watchVars.filter(v => v !== varName);
        if (state.currentView === 'debug') {
            timeTravel(state.currentStep, 'debug');
        }
    }

    function clearAllWatches() {
        state.watchVars = [];
        if (state.currentView === 'debug') {
            renderWatchChips({}, {}, elements.debugWatchChips);
        }
        showToast('Cleared all watches', 'info');
    }

    // =========================================================================
    // Auto-Play Controls
    // =========================================================================

    function togglePlayback() {
        if (state.isPlaying) {
            stopPlayback();
        } else {
            startPlayback();
        }
    }

    function startPlayback() {
        if (state.totalSteps === 0) return;
        state.isPlaying = true;
        elements.btnDebugPlay.textContent = '⏸';

        state.playInterval = setInterval(() => {
            if (state.currentStep >= state.totalSteps) {
                stopPlayback();
            } else {
                timeTravel(state.currentStep + 1, state.currentView === 'debug' ? 'debug' : 'historical');
            }
        }, state.playSpeedMs);
    }

    function stopPlayback() {
        state.isPlaying = false;
        elements.btnDebugPlay.textContent = '▶';
        if (state.playInterval) {
            clearInterval(state.playInterval);
            state.playInterval = null;
        }
    }

    // =========================================================================
    // Modals
    // =========================================================================

    function openNewProgramModal() {
        elements.inputNewProgName.value = '';
        elements.inputNewProgDesc.value = '';
        elements.selectNewProgTemplate.value = 'palindrome';
        elements.modalNewProgram.classList.remove('hidden');
        setTimeout(() => elements.inputNewProgName.focus(), 50);
    }

    function closeNewProgramModal() {
        elements.modalNewProgram.classList.add('hidden');
    }

    async function submitCreateProgram() {
        const name = elements.inputNewProgName.value.trim();
        const desc = elements.inputNewProgDesc.value.trim();
        const tmplKey = elements.selectNewProgTemplate.value;
        const code = TEMPLATES[tmplKey] || TEMPLATES.empty;

        if (!name) {
            showToast('Program name is required', 'error');
            elements.inputNewProgName.focus();
            return;
        }

        try {
            const res = await api('/api/programs', {
                method: 'POST',
                body: JSON.stringify({
                    name: name,
                    description: desc,
                    source_code: code,
                }),
            });
            closeNewProgramModal();
            showToast(`Created '${res.program.name}'`, 'success');
            await loadPrograms(false);
            await selectProgram(res.program.id);
            switchView('workspace');
        } catch (err) {
            showToast(`Creation failed: ${err.message}`, 'error');
        }
    }

    // =========================================================================
    // Event Listeners & Shortcuts
    // =========================================================================

    function setupEventListeners() {
        // Workspace Editor
        elements.workspaceTextarea.addEventListener('input', () => {
            updateWorkspaceGutter();
            if (!state.isDirty) {
                state.isDirty = true;
                updateHeader();
            }
        });
        elements.workspaceTextarea.addEventListener('scroll', () => {
            elements.workspaceGutter.scrollTop = elements.workspaceTextarea.scrollTop;
        });
        elements.workspaceTextarea.addEventListener('keyup', updateCursorPos);
        elements.workspaceTextarea.addEventListener('click', updateCursorPos);

        // Tab Key in Editor
        elements.workspaceTextarea.addEventListener('keydown', e => {
            if (e.key === 'Tab') {
                e.preventDefault();
                const start = elements.workspaceTextarea.selectionStart;
                const end = elements.workspaceTextarea.selectionEnd;
                elements.workspaceTextarea.value = elements.workspaceTextarea.value.substring(0, start) + '    ' + elements.workspaceTextarea.value.substring(end);
                elements.workspaceTextarea.selectionStart = elements.workspaceTextarea.selectionEnd = start + 4;
                updateWorkspaceGutter();
            }
        });

        function updateCursorPos() {
            const selStart = elements.workspaceTextarea.selectionStart;
            const text = elements.workspaceTextarea.value.substring(0, selStart);
            const lines = text.split('\n');
            const row = lines.length;
            const col = lines[lines.length - 1].length + 1;
            elements.workspaceCursorPos.textContent = `Ln ${row}, Col ${col}`;
        }

        // Global Keyboard Shortcuts
        window.addEventListener('keydown', e => {
            // Save (Ctrl+S / Cmd+S)
            if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
                e.preventDefault();
                saveProgram();
                return;
            }

            // Run (Ctrl+Enter / Cmd+Enter / F5)
            if (((e.ctrlKey || e.metaKey) && e.key === 'Enter') || e.key === 'F5') {
                e.preventDefault();
                if (state.currentView === 'workspace') {
                    runActiveProgram(false);
                }
                return;
            }

            // Step Next (F10 / ArrowRight in Debug/Historical)
            if (e.key === 'F10' && !e.shiftKey) {
                e.preventDefault();
                if (state.currentView === 'debug') timeTravel(state.currentStep + 1, 'debug');
                else if (state.currentView === 'historical_run') timeTravel(state.currentStep + 1, 'historical');
                return;
            }

            // Step Prev (Shift+F10 / ArrowLeft in Debug/Historical)
            if (e.key === 'F10' && e.shiftKey) {
                e.preventDefault();
                if (state.currentView === 'debug') timeTravel(state.currentStep - 1, 'debug');
                else if (state.currentView === 'historical_run') timeTravel(state.currentStep - 1, 'historical');
                return;
            }

            // Step First (Home key in Debug/Historical when not typing in input)
            if (e.key === 'Home' && (state.currentView === 'debug' || state.currentView === 'historical_run') && !['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) {
                e.preventDefault();
                timeTravel(1, state.currentView === 'debug' ? 'debug' : 'historical');
                return;
            }

            // Step Last (End key in Debug/Historical when not typing in input)
            if (e.key === 'End' && (state.currentView === 'debug' || state.currentView === 'historical_run') && !['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) {
                e.preventDefault();
                timeTravel(state.totalSteps, state.currentView === 'debug' ? 'debug' : 'historical');
                return;
            }

            // H / Home shortcut when not typing in an input
            if ((e.key === 'h' || e.key === 'H' || e.key === 'F1') && !['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) {
                e.preventDefault();
                switchView('workspace');
                return;
            }

            // Q / Quit shortcut when not typing in an input
            if ((e.key === 'q' || e.key === 'Q') && !['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) {
                e.preventDefault();
                if (confirm("Quit PyChronicle?")) {
                    window.close();
                }
                return;
            }

            // Escape to Exit Debug or History
            if (e.key === 'Escape') {
                if (state.currentView === 'debug' || state.currentView === 'history') {
                    switchView('workspace');
                } else if (state.currentView === 'historical_run') {
                    switchView('history');
                }
            }
        });

        // Top Navigation Buttons
        if (elements.btnNavHome) elements.btnNavHome.onclick = () => switchView('workspace');
        if (elements.btnNavNew) elements.btnNavNew.onclick = openNewProgramModal;
        if (elements.btnNavSave) elements.btnNavSave.onclick = saveProgram;
        if (elements.btnNavRun) elements.btnNavRun.onclick = () => runActiveProgram(false);
        if (elements.btnNavDebug) elements.btnNavDebug.onclick = () => runActiveProgram(true);
        if (elements.btnNavHistory) elements.btnNavHistory.onclick = () => switchView('history');
        if (elements.btnNavQuit) {
            elements.btnNavQuit.onclick = () => {
                if (confirm("Quit PyChronicle?")) {
                    window.close();
                }
            };
        }

        // Sidebar
        if (elements.btnSidebarNewProgram) elements.btnSidebarNewProgram.onclick = openNewProgramModal;
        if (elements.workspaceSearchInput) elements.workspaceSearchInput.addEventListener('input', renderProgramList);

        // Debug Controls
        if (elements.btnDebugFirst) elements.btnDebugFirst.onclick = () => timeTravel(1, 'debug');
        if (elements.btnDebugPrev) elements.btnDebugPrev.onclick = () => timeTravel(state.currentStep - 1, 'debug');
        if (elements.btnDebugNext) elements.btnDebugNext.onclick = () => timeTravel(state.currentStep + 1, 'debug');
        if (elements.btnDebugLast) elements.btnDebugLast.onclick = () => timeTravel(state.totalSteps, 'debug');
        if (elements.btnDebugPlay) elements.btnDebugPlay.onclick = togglePlayback;
        if (elements.debugSlider) elements.debugSlider.addEventListener('input', e => timeTravel(parseInt(e.target.value, 10), 'debug'));

        if (elements.btnDebugAddWatch) elements.btnDebugAddWatch.onclick = () => addWatch();
        if (elements.debugWatchInput) {
            elements.debugWatchInput.addEventListener('keydown', e => {
                if (e.key === 'Enter') addWatch();
            });
        }
        if (elements.btnDebugClearWatches) elements.btnDebugClearWatches.onclick = clearAllWatches;

        // History View Controls
        if (elements.historySearchInput) elements.historySearchInput.addEventListener('input', loadHistoryRuns);
        if (elements.historyChips) {
            elements.historyChips.forEach(chip => {
                chip.onclick = () => {
                    elements.historyChips.forEach(c => c.classList.remove('active'));
                    chip.classList.add('active');
                    state.historyFilter = chip.dataset.historyFilter;
                    loadHistoryRuns();
                };
            });
        }

        // Historical Run Controls
        if (elements.btnHistCopyToWorkspace) elements.btnHistCopyToWorkspace.onclick = copyHistoricalRunToWorkspace;
        if (elements.btnHistFirst) elements.btnHistFirst.onclick = () => timeTravel(1, 'historical');
        if (elements.btnHistPrev) elements.btnHistPrev.onclick = () => timeTravel(state.currentStep - 1, 'historical');
        if (elements.btnHistNext) elements.btnHistNext.onclick = () => timeTravel(state.currentStep + 1, 'historical');
        if (elements.btnHistLast) elements.btnHistLast.onclick = () => timeTravel(state.totalSteps, 'historical');
        if (elements.histSlider) elements.histSlider.addEventListener('input', e => timeTravel(parseInt(e.target.value, 10), 'historical'));

        // Modals
        elements.btnCloseNewProg.onclick = closeNewProgramModal;
        elements.btnCancelNewProg.onclick = closeNewProgramModal;
        elements.btnSubmitNewProg.onclick = submitCreateProgram;

        // Resizer between editor and console
        setupResizer();
    }

    function setupResizer() {
        let isResizing = false;
        elements.workspaceResizer.addEventListener('mousedown', () => {
            isResizing = true;
            elements.workspaceResizer.classList.add('resizing');
            document.body.style.cursor = 'row-resize';
            document.body.style.userSelect = 'none';
        });

        window.addEventListener('mousemove', e => {
            if (!isResizing) return;
            const containerRect = elements.workspaceEditorPane.parentElement.getBoundingClientRect();
            const relativeY = e.clientY - containerRect.top;
            const pct = (relativeY / containerRect.height) * 100;
            if (pct >= 20 && pct <= 80) {
                elements.workspaceEditorPane.style.flex = `${pct}`;
                elements.workspaceConsolePane.style.flex = `${100 - pct}`;
            }
        });

        window.addEventListener('mouseup', () => {
            if (isResizing) {
                isResizing = false;
                elements.workspaceResizer.classList.remove('resizing');
                document.body.style.cursor = '';
                document.body.style.userSelect = '';
            }
        });
    }

    // Global App Interface for inline handlers
    window.PyChronicleApp = {
        switchView: (viewName) => switchView(viewName),
        openHistoricalRun: (execId) => openHistoricalRun(execId),
        removeWatch: (varName) => removeWatch(varName),
    };

    // App Initialization
    async function init() {
        setupEventListeners();
        await loadPrograms(false);
        switchView('workspace');
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
