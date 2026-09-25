/**
 * PyChronicle Programming Workspace Client Script
 * Handles code editing, line numbering, AJAX execution, saving, unsaved changes tracking,
 * and seamless new program creation.
 */

document.addEventListener('DOMContentLoaded', () => {
    const codeEditor = document.getElementById('code-editor');
    const lineNumbers = document.getElementById('editor-line-numbers');
    const nameInput = document.getElementById('program-name-input');
    const idInput = document.getElementById('program-id-input');
    const consoleOutput = document.getElementById('console-output');
    const lastStatusBadge = document.getElementById('badge-last-status');
    const execTimeBadge = document.getElementById('badge-exec-time');

    const saveBtn = document.getElementById('btn-save-workspace') || document.getElementById('toolbar-save-btn');
    const runBtn = document.getElementById('btn-run-workspace') || document.getElementById('toolbar-run-btn');
    const debugBtn = document.getElementById('btn-debug-workspace') || document.getElementById('toolbar-debug-btn');
    const deleteBtn = document.getElementById('btn-delete-workspace');
    const newProgBtn = document.getElementById('btn-create-new-prog');

    // Toolbar buttons fallback
    const tbSave = document.getElementById('toolbar-save-btn');
    const tbRun = document.getElementById('toolbar-run-btn');
    const tbDebug = document.getElementById('toolbar-debug-btn');

    // Track baseline state for unsaved changes detection
    let initialCode = codeEditor ? codeEditor.value : '';
    let initialName = nameInput ? (nameInput.value || '').trim() : 'Untitled Program';

    function isDirty() {
        const currentCode = codeEditor ? codeEditor.value : '';
        const currentName = nameInput ? (nameInput.value || '').trim() : '';
        return currentCode !== initialCode || currentName !== initialName;
    }

    // 1. Line Number Synchronization (Minimum 5 lines rendered)
    function updateLineNumbers() {
        if (!codeEditor || !lineNumbers) return;
        const lines = codeEditor.value.split('\n');
        const count = Math.max(lines.length, 5);
        let html = '';
        for (let i = 1; i <= count; i++) {
            html += `<div>${i}</div>`;
        }
        lineNumbers.innerHTML = html;
    }

    function syncScroll() {
        if (!codeEditor || !lineNumbers) return;
        lineNumbers.scrollTop = codeEditor.scrollTop;
    }

    if (codeEditor) {
        codeEditor.addEventListener('input', updateLineNumbers);
        codeEditor.addEventListener('scroll', syncScroll);
        updateLineNumbers();

        // 2. Tab Key Indentation & Keyboard Shortcuts
        codeEditor.addEventListener('keydown', (e) => {
            if (e.key === 'Tab') {
                e.preventDefault();
                const start = codeEditor.selectionStart;
                const end = codeEditor.selectionEnd;
                const val = codeEditor.value;

                codeEditor.value = val.substring(0, start) + '    ' + val.substring(end);
                codeEditor.selectionStart = codeEditor.selectionEnd = start + 4;
                updateLineNumbers();
            } else if ((e.ctrlKey || e.metaKey) && e.key === 's') {
                e.preventDefault();
                saveProgram();
            } else if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                e.preventDefault();
                runProgram();
            }
        });
    }

    // 3. New Program Reset (Fresh Unsaved Workspace)
    function createNewProgram(force = false) {
        if (!force && isDirty()) {
            const confirmDiscard = confirm('You have unsaved changes. Create a new program anyway?');
            if (!confirmDiscard) return;
        }

        // Clear ID, name, and code
        if (idInput) idInput.value = '';
        if (nameInput) nameInput.value = 'Untitled Program';
        if (codeEditor) codeEditor.value = '';

        initialCode = '';
        initialName = 'Untitled Program';

        updateLineNumbers();

        // Reset output console and status badges
        if (consoleOutput) consoleOutput.textContent = 'No output yet.';
        if (lastStatusBadge) {
            lastStatusBadge.textContent = 'READY';
            lastStatusBadge.className = 'badge badge-muted';
        }
        if (execTimeBadge) execTimeBadge.style.display = 'none';
        if (deleteBtn) deleteBtn.style.display = 'none';

        // Clear active highlighting in sidebar
        document.querySelectorAll('.sidebar-program-item').forEach(el => {
            el.classList.remove('active');
        });

        // Update URL to /programs
        if (window.location.pathname !== '/programs') {
            window.history.pushState({}, '', '/programs');
        }

        if (nameInput) nameInput.focus();
    }

    if (newProgBtn) {
        newProgBtn.addEventListener('click', () => createNewProgram(false));
    }

    // Warn before navigating away if there are unsaved changes
    document.addEventListener('click', (e) => {
        const link = e.target.closest('.sidebar-program-item');
        if (link && isDirty()) {
            if (!confirm('You have unsaved changes. Open another program anyway?')) {
                e.preventDefault();
            }
        }
    });

    // 4. Save Program (Creates new record if unsaved, updates if existing)
    async function saveProgram() {
        const name = (nameInput.value || '').trim();
        const source_code = codeEditor.value;
        const progId = idInput.value ? parseInt(idInput.value, 10) : null;

        if (!name) {
            alert('Please enter a program name.');
            if (nameInput) nameInput.focus();
            return null;
        }

        try {
            const res = await fetch('/api/programs/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    id: progId,
                    name: name,
                    source_code: source_code,
                })
            });
            const data = await res.json();
            if (data.success) {
                const isNew = !progId;
                idInput.value = data.program.id;
                initialCode = data.program.source_code || '';
                initialName = data.program.name || '';
                if (deleteBtn) deleteBtn.style.display = 'inline-block';
                window.history.pushState({}, '', `/programs/${data.program.id}`);
                updateSidebarAfterSave(data.program, isNew);
                showStatusMessage(`Program '${data.program.name}' saved successfully.`, 'success');
                return data.program;
            } else {
                alert(`Save failed: ${data.error}`);
                return null;
            }
        } catch (err) {
            alert(`Error saving program: ${err}`);
            return null;
        }
    }

    function updateSidebarAfterSave(program, isNew) {
        const sidebarList = document.getElementById('sidebar-programs-list');
        if (!sidebarList) return;

        if (isNew) {
            document.querySelectorAll('.sidebar-program-item').forEach(el => el.classList.remove('active'));

            let tab = document.getElementById(`prog-tab-${program.id}`);
            if (!tab) {
                tab = document.createElement('a');
                tab.href = `/programs/${program.id}`;
                tab.className = 'sidebar-program-item active';
                tab.id = `prog-tab-${program.id}`;
                tab.innerHTML = `
                    <span class="prog-item-title">${escapeHtml(program.name)}</span>
                    <span class="prog-item-status badge-dot-muted"></span>
                `;
                sidebarList.appendChild(tab);
            } else {
                tab.classList.add('active');
                const titleSpan = tab.querySelector('.prog-item-title');
                if (titleSpan) titleSpan.textContent = program.name;
            }
        } else {
            const tab = document.getElementById(`prog-tab-${program.id}`);
            if (tab) {
                const titleSpan = tab.querySelector('.prog-item-title');
                if (titleSpan) titleSpan.textContent = program.name;
            }
        }
    }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    // 5. Run Program
    async function runProgram() {
        let progId = idInput.value ? parseInt(idInput.value, 10) : null;
        if (!progId) {
            const saved = await saveProgram();
            if (!saved) return;
            progId = saved.id;
        } else {
            await saveProgram();
        }

        consoleOutput.textContent = 'Executing program via PyChronicle AST tracer...';
        lastStatusBadge.textContent = 'RUNNING';
        lastStatusBadge.className = 'badge badge-warning';

        try {
            const res = await fetch(`/api/programs/${progId}/run`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    source_code: codeEditor.value,
                })
            });
            const data = await res.json();
            if (data.success && data.result) {
                const r = data.result;
                let output = '';
                if (r.stdout) output += r.stdout;
                if (r.error) output += (output ? '\n' : '') + `Error:\n${r.error}`;
                if (!output) output = '(Program completed with no output)';

                consoleOutput.textContent = output;
                lastStatusBadge.textContent = r.status;
                lastStatusBadge.className = `badge badge-${r.status === 'SUCCESS' ? 'success' : 'error'}`;

                if (execTimeBadge) {
                    execTimeBadge.style.display = 'inline-block';
                    execTimeBadge.textContent = `${r.duration_ms} ms (${r.total_steps} steps)`;
                }

                // Update sidebar status badge
                const tab = document.getElementById(`prog-tab-${progId}`);
                if (tab) {
                    const statusDot = tab.querySelector('.prog-item-status');
                    if (statusDot) {
                        statusDot.className = `prog-item-status badge-dot-${r.status === 'SUCCESS' ? 'success' : 'error'}`;
                    }
                }
            } else {
                consoleOutput.textContent = `Execution Error: ${data.error || 'Unknown error'}`;
                lastStatusBadge.textContent = 'ERROR';
                lastStatusBadge.className = 'badge badge-error';
            }
        } catch (err) {
            consoleOutput.textContent = `Network / Execution failed: ${err}`;
            lastStatusBadge.textContent = 'ERROR';
            lastStatusBadge.className = 'badge badge-error';
        }
    }

    // 6. Debug Program
    async function debugProgram() {
        let progId = idInput.value ? parseInt(idInput.value, 10) : null;
        if (!progId) {
            const saved = await saveProgram();
            if (!saved) return;
            progId = saved.id;
        } else {
            await saveProgram();
        }

        consoleOutput.textContent = 'Launching PyChronicle AST Time-Travel Debugger...';

        try {
            const res = await fetch(`/api/programs/${progId}/debug`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    source_code: codeEditor.value,
                })
            });
            const data = await res.json();
            if (data.success && data.redirect_url) {
                window.location.href = data.redirect_url;
            } else {
                alert(`Debugger initialization failed: ${data.error || 'Unknown error'}`);
            }
        } catch (err) {
            alert(`Error starting debugger: ${err}`);
        }
    }

    // 7. Delete Program
    if (deleteBtn) {
        deleteBtn.addEventListener('click', async () => {
            const progId = idInput.value;
            const progName = nameInput.value;
            if (!progId) return;

            if (confirm(`Are you sure you want to delete '${progName}' and all its history?`)) {
                try {
                    const res = await fetch(`/api/programs/${progId}`, { method: 'DELETE' });
                    const data = await res.json();
                    if (data.success) {
                        const tab = document.getElementById(`prog-tab-${progId}`);
                        if (tab) tab.remove();
                        createNewProgram(true);
                        showStatusMessage(`Program '${progName}' deleted.`, 'info');
                    } else {
                        alert(`Failed to delete program: ${data.error}`);
                    }
                } catch (err) {
                    alert(`Error deleting program: ${err}`);
                }
            }
        });
    }

    // Bind action events
    if (saveBtn) saveBtn.addEventListener('click', saveProgram);
    if (runBtn) runBtn.addEventListener('click', runProgram);
    if (debugBtn) debugBtn.addEventListener('click', debugProgram);
    if (tbSave && tbSave !== saveBtn) tbSave.addEventListener('click', saveProgram);
    if (tbRun && tbRun !== runBtn) tbRun.addEventListener('click', runProgram);
    if (tbDebug && tbDebug !== debugBtn) tbDebug.addEventListener('click', debugProgram);

    function showStatusMessage(msg, type) {
        consoleOutput.textContent = `[System] ${msg}`;
    }
});
