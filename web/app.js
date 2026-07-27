document.addEventListener('DOMContentLoaded', () => {
    // State
    let analysisResult = null;
    let activeTab = 'intersection';
    let currentPage = 1;
    const pageSize = 50;
    let searchQuery = '';

    // DOM Elements - Tab 1 (Set Analyzer)
    const setPasteA = document.getElementById('set-paste-a');
    const setPasteB = document.getElementById('set-paste-b');
    const btnClipA = document.getElementById('btn-clip-a');
    const btnClipB = document.getElementById('btn-clip-b');
    const optHeaderA = document.getElementById('opt-header-a');
    const optTrim = document.getElementById('opt-trim');
    const optCase = document.getElementById('opt-case');
    const optDropEmpty = document.getElementById('opt-drop-empty');
    const btnAnalyze = document.getElementById('btn-analyze');
    const btnLoadSample = document.getElementById('btn-load-sample');

    const emptyState = document.getElementById('empty-state');
    const dashboardContent = document.getElementById('dashboard-content');
    const currentViewTitle = document.getElementById('current-view-title');

    const btnCopyValuesOnly = document.getElementById('btn-copy-values-only');
    const btnCopyTable = document.getElementById('btn-copy-table');
    const toast = document.getElementById('toast');

    const searchInput = document.getElementById('search-input');
    const tableBody = document.getElementById('table-body');
    const pageInfo = document.getElementById('page-info');
    const btnPrevPage = document.getElementById('btn-prev-page');
    const btnNextPage = document.getElementById('btn-next-page');
    const currentPageNum = document.getElementById('current-page-num');

    // Tab Titles Map
    const tabTitles = {
        'intersection': '🔵 교집합 (A와 B 모두 존재)',
        'a_only': '🟡 A 전용 / 차집합 A (A에만 존재)',
        'b_only': '🔴 B 전용 / 차집합 B (B에만 존재)',
        'sym_diff': '🟣 통합 대칭차집합 (불일치 데이터 전체)',
        'union': '🟢 합집합 (A 또는 B 전체)'
    };

    // Clipboard Read Buttons
    btnClipA.addEventListener('click', async () => {
        try {
            if (navigator.clipboard && navigator.clipboard.readText) {
                const text = await navigator.clipboard.readText();
                setPasteA.value = text;
                computeSetAnalysis();
            }
        } catch (err) {
            console.error(err);
        }
    });

    btnClipB.addEventListener('click', async () => {
        try {
            if (navigator.clipboard && navigator.clipboard.readText) {
                const text = await navigator.clipboard.readText();
                setPasteB.value = text;
                computeSetAnalysis();
            }
        } catch (err) {
            console.error(err);
        }
    });

    // Inputs change -> compute set analysis
    setPasteA.addEventListener('input', computeSetAnalysis);
    setPasteB.addEventListener('input', computeSetAnalysis);
    optHeaderA.addEventListener('change', computeSetAnalysis);
    optTrim.addEventListener('change', computeSetAnalysis);
    optCase.addEventListener('change', computeSetAnalysis);
    optDropEmpty.addEventListener('change', computeSetAnalysis);

    btnAnalyze.addEventListener('click', computeSetAnalysis);

    // Sample Data Loader
    btnLoadSample.addEventListener('click', () => {
        setPasteA.value = "김철수\n이영희\n박민수\n정수진\n최동훈\n홍길동\n임재범";
        setPasteB.value = "이영희\n최동훈\n강하늘\n윤서준\n홍길동\n송중기";
        computeSetAnalysis();
        showToast("💡 샘플 데이터가 입력되었습니다!");
    });

    function computeSetAnalysis() {
        const rawTextA = setPasteA.value || '';
        const rawTextB = setPasteB.value || '';

        if (!rawTextA.trim() && !rawTextB.trim()) {
            analysisResult = null;
            emptyState.classList.remove('hidden');
            dashboardContent.classList.add('hidden');
            return;
        }

        const doTrim = optTrim.checked;
        const doCase = optCase.checked;
        const dropEmpty = optDropEmpty.checked;
        const skipHeader = optHeaderA.checked;

        function parseItems(text) {
            if (!text || !text.trim()) return [];
            let lines = text.split(/\r?\n/).filter(l => l.length > 0);
            if (skipHeader && lines.length > 0) lines = lines.slice(1);

            const items = [];
            lines.forEach(line => {
                const parts = line.split('\t');
                let val = parts[0];
                if (doTrim) val = val.trim();
                if (dropEmpty && (!val || val === '')) return;

                const norm = doCase ? val : val.toLowerCase();
                items.push({ norm, raw: val });
            });
            return items;
        }

        const itemsA = parseItems(rawTextA);
        const itemsB = parseItems(rawTextB);

        const setNormA = new Set(itemsA.map(i => i.norm));
        const setNormB = new Set(itemsB.map(i => i.norm));

        const rawMapA = new Map(itemsA.map(i => [i.norm, i.raw]));
        const rawMapB = new Map(itemsB.map(i => [i.norm, i.raw]));

        const normIntersection = new Set([...setNormA].filter(x => setNormB.has(x)));
        const normAOnly = new Set([...setNormA].filter(x => !setNormB.has(x)));
        const normBOnly = new Set([...setNormB].filter(x => !setNormA.has(x)));
        const normSymDiff = new Set([...normAOnly, ...normBOnly]);
        const normUnion = new Set([...setNormA, ...setNormB]);

        function buildList(normSet, originFilter) {
            const sorted = [...normSet].sort();
            const results = [];
            sorted.forEach(norm => {
                const inA = setNormA.has(norm);
                const inB = setNormB.has(norm);
                const rawVal = rawMapA.get(norm) || rawMapB.get(norm) || norm;

                if (originFilter === 'A_ONLY' && !(inA && !inB)) return;
                if (originFilter === 'B_ONLY' && !(inB && !inA)) return;

                let origin = '공통(교집합)';
                if (inA && !inB) origin = 'A전용(차집합A)';
                else if (inB && !inA) origin = 'B전용(차집합B)';

                results.push({
                    val: rawVal,
                    origin: origin,
                    in_a: inA ? 'O' : 'X',
                    in_b: inB ? 'O' : 'X'
                });
            });
            return results;
        }

        const listIntersection = buildList(normIntersection);
        const listAOnly = buildList(normAOnly, 'A_ONLY');
        const listBOnly = buildList(normBOnly, 'B_ONLY');
        const listSymDiff = [...listAOnly, ...listBOnly];
        const listUnion = buildList(normUnion);

        analysisResult = {
            stats: {
                intersection_count: normIntersection.size,
                a_only_count: normAOnly.size,
                b_only_count: normBOnly.size,
                sym_diff_count: normSymDiff.size,
                union_count: normUnion.size
            },
            intersection: listIntersection,
            a_only: listAOnly,
            b_only: listBOnly,
            sym_diff: listSymDiff,
            union: listUnion
        };

        renderDashboard();
    }

    function renderDashboard() {
        if (!analysisResult) return;

        const stats = analysisResult.stats;

        document.getElementById('stat-intersection').textContent = stats.intersection_count.toLocaleString();
        document.getElementById('stat-a-only').textContent = stats.a_only_count.toLocaleString();
        document.getElementById('stat-b-only').textContent = stats.b_only_count.toLocaleString();
        document.getElementById('stat-sym-diff').textContent = stats.sym_diff_count.toLocaleString();

        document.getElementById('badge-intersection').textContent = stats.intersection_count;
        document.getElementById('badge-a-only').textContent = stats.a_only_count;
        document.getElementById('badge-b-only').textContent = stats.b_only_count;
        document.getElementById('badge-sym-diff').textContent = stats.sym_diff_count;
        document.getElementById('badge-union').textContent = stats.union_count;

        emptyState.classList.add('hidden');
        dashboardContent.classList.remove('hidden');

        currentPage = 1;
        renderTable();
    }

    // Tabs Switch
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            const targetBtn = e.target.closest('.tab-btn');
            targetBtn.classList.add('active');
            activeTab = targetBtn.getAttribute('data-tab');
            currentViewTitle.textContent = tabTitles[activeTab] || activeTab;
            currentPage = 1;
            renderTable();
        });
    });

    // Search Input
    searchInput.addEventListener('input', (e) => {
        searchQuery = e.target.value.trim().toLowerCase();
        currentPage = 1;
        renderTable();
    });

    function renderTable() {
        if (!analysisResult) return;

        let items = analysisResult[activeTab] || [];

        if (searchQuery) {
            items = items.filter(item => 
                String(item.val).toLowerCase().includes(searchQuery) ||
                String(item.origin).toLowerCase().includes(searchQuery)
            );
        }

        const totalItems = items.length;
        const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
        currentPage = Math.min(currentPage, totalPages);

        const startIdx = (currentPage - 1) * pageSize;
        const pageItems = items.slice(startIdx, startIdx + pageSize);

        tableBody.innerHTML = '';

        if (pageItems.length === 0) {
            tableBody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding: 30px; color: var(--text-muted);">조회할 데이터가 없습니다.</td></tr>`;
        } else {
            pageItems.forEach((item, idx) => {
                const row = document.createElement('tr');

                let badgeClass = 'common';
                if (item.origin.includes('A전용')) badgeClass = 'a-only';
                else if (item.origin.includes('B전용')) badgeClass = 'b-only';

                row.innerHTML = `
                    <td>${startIdx + idx + 1}</td>
                    <td><strong>${escapeHtml(item.val)}</strong></td>
                    <td><span class="tag-badge ${badgeClass}">${escapeHtml(item.origin)}</span></td>
                    <td class="${item.in_a === 'O' ? 'status-o' : 'status-x'}">${item.in_a}</td>
                    <td class="${item.in_b === 'O' ? 'status-o' : 'status-x'}">${item.in_b}</td>
                `;
                tableBody.appendChild(row);
            });
        }

        pageInfo.textContent = totalItems > 0 
            ? `${startIdx + 1}-${Math.min(startIdx + pageSize, totalItems)} / 전체 ${totalItems}개`
            : '전체 0개';
        
        currentPageNum.textContent = `${currentPage} / ${totalPages}`;
        btnPrevPage.disabled = (currentPage <= 1);
        btnNextPage.disabled = (currentPage >= totalPages);
    }

    btnPrevPage.addEventListener('click', () => {
        if (currentPage > 1) {
            currentPage--;
            renderTable();
        }
    });

    btnNextPage.addEventListener('click', () => {
        currentPage++;
        renderTable();
    });

    // -------------------------------------------------------------
    // MAIN FEATURE NAVIGATION TABS
    // -------------------------------------------------------------
    const navTabBtns = document.querySelectorAll('.nav-tab-btn');
    const viewSetAnalyzer = document.getElementById('nav-view-set-analyzer');
    const viewColumnConcat = document.getElementById('nav-view-column-concat');

    navTabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            navTabBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const targetNav = btn.getAttribute('data-nav');

            if (targetNav === 'set-analyzer') {
                viewSetAnalyzer.classList.remove('hidden');
                viewSetAnalyzer.classList.add('active');
                viewColumnConcat.classList.add('hidden');
                viewColumnConcat.classList.remove('active');
            } else if (targetNav === 'column-concat') {
                viewColumnConcat.classList.remove('hidden');
                viewColumnConcat.classList.add('active');
                viewSetAnalyzer.classList.add('hidden');
                viewSetAnalyzer.classList.remove('active');
            }
        });
    });

    // -------------------------------------------------------------
    // COLUMN CONCAT ENGINE LOGIC
    // -------------------------------------------------------------
    let concatRawRows = [];
    let concatHeaders = [];
    let selectedColumnIndices = [];
    let concatResults = [];

    const concatPasteInput = document.getElementById('concat-paste-input');
    const btnReadClipboard = document.getElementById('btn-read-clipboard');
    const btnClearConcat = document.getElementById('btn-clear-concat');
    const concatSetupPanel = document.getElementById('concat-setup-panel');
    const chkConcatHeader = document.getElementById('chk-concat-header');
    const concatColumnChips = document.getElementById('concat-column-chips');
    const concatSequenceTags = document.getElementById('concat-sequence-tags');
    const btnResetSequence = document.getElementById('btn-reset-sequence');

    const concatDelimiterSelect = document.getElementById('concat-delimiter-select');
    const customDelimiterWrapper = document.getElementById('custom-delimiter-wrapper');
    const concatCustomDelimiter = document.getElementById('concat-custom-delimiter');
    const concatOptTrim = document.getElementById('concat-opt-trim');
    const concatOptSkipEmpty = document.getElementById('concat-opt-skip-empty');

    const concatEmptyState = document.getElementById('concat-empty-state');
    const concatResultDashboard = document.getElementById('concat-result-dashboard');
    const concatRowCount = document.getElementById('concat-row-count');
    const concatTableBody = document.getElementById('concat-table-body');
    const concatSearchInput = document.getElementById('concat-search-input');
    const concatPageInfo = document.getElementById('concat-page-info');
    const btnCopyConcatResult = document.getElementById('btn-copy-concat-result');

    concatPasteInput.addEventListener('input', () => {
        parseConcatData(concatPasteInput.value);
    });

    btnReadClipboard.addEventListener('click', async () => {
        try {
            if (navigator.clipboard && navigator.clipboard.readText) {
                const text = await navigator.clipboard.readText();
                concatPasteInput.value = text;
                parseConcatData(text);
                showToast('📋 클립보드 데이터를 성공적으로 불러왔습니다!');
            } else {
                alert('클립보드 읽기 권한을 지원하지 않는 브라우저입니다. Ctrl+V로 붙여넣어주세요.');
            }
        } catch (err) {
            console.error(err);
            alert('클립보드 데이터를 읽을 수 없습니다. 직접 Ctrl+V로 붙여넣어주세요.');
        }
    });

    btnClearConcat.addEventListener('click', () => {
        concatPasteInput.value = '';
        concatRawRows = [];
        concatHeaders = [];
        selectedColumnIndices = [];
        concatResults = [];
        concatSetupPanel.classList.add('disabled');
        renderColumnChips();
        renderSequenceTags();
        renderConcatResults();
    });

    chkConcatHeader.addEventListener('change', () => {
        if (concatPasteInput.value.trim()) {
            parseConcatData(concatPasteInput.value);
        }
    });

    concatDelimiterSelect.addEventListener('change', (e) => {
        if (e.target.value === 'custom') {
            customDelimiterWrapper.classList.remove('hidden');
        } else {
            customDelimiterWrapper.classList.add('hidden');
        }
        computeAndRenderConcat();
    });

    concatCustomDelimiter.addEventListener('input', computeAndRenderConcat);
    concatOptTrim.addEventListener('change', computeAndRenderConcat);
    concatOptSkipEmpty.addEventListener('change', computeAndRenderConcat);

    btnResetSequence.addEventListener('click', () => {
        selectedColumnIndices = [];
        renderSequenceTags();
        computeAndRenderConcat();
    });

    concatSearchInput.addEventListener('input', renderConcatTable);

    function getColumnLetter(index) {
        let letter = '';
        while (index >= 0) {
            letter = String.fromCharCode((index % 26) + 65) + letter;
            index = Math.floor(index / 26) - 1;
        }
        return letter;
    }

    function parseConcatData(rawText) {
        if (!rawText || !rawText.trim()) {
            concatRawRows = [];
            concatHeaders = [];
            selectedColumnIndices = [];
            concatSetupPanel.classList.add('disabled');
            renderColumnChips();
            renderSequenceTags();
            computeAndRenderConcat();
            return;
        }

        const lines = rawText.split(/\r?\n/).filter(line => line.length > 0);
        if (lines.length === 0) return;

        // Determine separator: TSV (\t) preferred, fallback to comma or multiple spaces
        const firstLine = lines[0];
        let sep = '\t';
        if (!firstLine.includes('\t')) {
            if (firstLine.includes(',')) sep = ',';
            else sep = /\s{2,}/;
        }

        const parsedRows = lines.map(line => line.split(sep));
        const maxCols = Math.max(...parsedRows.map(r => r.length));

        const hasHeader = chkConcatHeader.checked;
        if (hasHeader && parsedRows.length > 0) {
            const headerRow = parsedRows[0];
            concatHeaders = [];
            for (let i = 0; i < maxCols; i++) {
                const name = (headerRow[i] !== undefined && headerRow[i].trim() !== '') 
                    ? headerRow[i].trim() 
                    : `열 ${getColumnLetter(i)}`;
                concatHeaders.push(name);
            }
            concatRawRows = parsedRows.slice(1);
        } else {
            concatHeaders = [];
            for (let i = 0; i < maxCols; i++) {
                concatHeaders.push(`열 ${getColumnLetter(i)}`);
            }
            concatRawRows = parsedRows;
        }

        concatSetupPanel.classList.remove('disabled');
        renderColumnChips();

        // Default: If no columns selected, auto select first 2 columns if available
        if (selectedColumnIndices.length === 0 && concatHeaders.length > 0) {
            selectedColumnIndices = concatHeaders.length > 1 ? [0, 1] : [0];
        } else {
            // Remove any invalid indices
            selectedColumnIndices = selectedColumnIndices.filter(idx => idx < concatHeaders.length);
        }

        renderSequenceTags();
        computeAndRenderConcat();
    }

    function renderColumnChips() {
        concatColumnChips.innerHTML = '';
        if (concatHeaders.length === 0) {
            concatColumnChips.innerHTML = '<span class="empty-chips-hint">붙여넣은 데이터가 없습니다.</span>';
            return;
        }

        concatHeaders.forEach((header, idx) => {
            const colLetter = getColumnLetter(idx);
            const chip = document.createElement('div');
            chip.className = 'column-chip';
            chip.innerHTML = `<span>+ [${colLetter}] ${escapeHtml(header)}</span>`;
            chip.addEventListener('click', () => {
                selectedColumnIndices.push(idx);
                renderSequenceTags();
                computeAndRenderConcat();
            });
            concatColumnChips.appendChild(chip);
        });
    }

    function renderSequenceTags() {
        concatSequenceTags.innerHTML = '';
        if (selectedColumnIndices.length === 0) {
            concatSequenceTags.innerHTML = '<span class="empty-chips-hint">컬럼을 클릭하여 병합 순서를 지정하세요.</span>';
            return;
        }

        selectedColumnIndices.forEach((colIdx, seqIdx) => {
            if (seqIdx > 0) {
                const arrow = document.createElement('span');
                arrow.className = 'sequence-arrow';
                arrow.textContent = '➔';
                concatSequenceTags.appendChild(arrow);
            }

            const headerName = concatHeaders[colIdx] || `열 ${getColumnLetter(colIdx)}`;
            const tag = document.createElement('div');
            tag.className = 'sequence-tag';
            tag.innerHTML = `
                <span class="tag-num">${seqIdx + 1}</span>
                <span>[${getColumnLetter(colIdx)}] ${escapeHtml(headerName)}</span>
                <span class="btn-remove-tag" data-seq="${seqIdx}">✕</span>
            `;

            tag.querySelector('.btn-remove-tag').addEventListener('click', (e) => {
                e.stopPropagation();
                selectedColumnIndices.splice(seqIdx, 1);
                renderSequenceTags();
                computeAndRenderConcat();
            });

            concatSequenceTags.appendChild(tag);
        });
    }

    function getSelectedDelimiter() {
        const type = concatDelimiterSelect.value;
        switch (type) {
            case 'space': return ' ';
            case 'hyphen': return '-';
            case 'underscore': return '_';
            case 'comma': return ', ';
            case 'slash': return '/';
            case 'none': return '';
            case 'custom': return concatCustomDelimiter.value;
            default: return ' ';
        }
    }

    function computeAndRenderConcat() {
        if (concatRawRows.length === 0 || selectedColumnIndices.length === 0) {
            concatResults = [];
            renderConcatResults();
            return;
        }

        const delimiter = getSelectedDelimiter();
        const doTrim = concatOptTrim.checked;
        const skipEmpty = concatOptSkipEmpty.checked;

        concatResults = concatRawRows.map((row, rowIdx) => {
            const rowValues = [];
            const sourceSummaries = [];

            selectedColumnIndices.forEach(colIdx => {
                let rawVal = row[colIdx] !== undefined ? row[colIdx] : '';
                if (doTrim) rawVal = rawVal.trim();

                if (!skipEmpty || rawVal !== '') {
                    rowValues.push(rawVal);
                }

                const hName = concatHeaders[colIdx] || getColumnLetter(colIdx);
                sourceSummaries.push(`${hName}: "${rawVal}"`);
            });

            const outputVal = rowValues.join(delimiter);
            return {
                row_idx: rowIdx + 1,
                val: outputVal,
                summary: sourceSummaries.join(' | ')
            };
        });

        renderConcatResults();
    }

    function renderConcatResults() {
        if (concatResults.length === 0) {
            concatEmptyState.classList.remove('hidden');
            concatResultDashboard.classList.add('hidden');
            return;
        }

        concatEmptyState.classList.add('hidden');
        concatResultDashboard.classList.remove('hidden');

        concatRowCount.textContent = concatResults.length.toLocaleString();
        renderConcatTable();
    }

    function renderConcatTable() {
        const query = concatSearchInput.value.trim().toLowerCase();
        let items = concatResults;

        if (query) {
            items = items.filter(item => 
                String(item.val).toLowerCase().includes(query) ||
                String(item.summary).toLowerCase().includes(query)
            );
        }

        concatTableBody.innerHTML = '';

        if (items.length === 0) {
            concatTableBody.innerHTML = `<tr><td colspan="3" style="text-align:center; padding: 30px; color: var(--text-muted);">검색 결과가 없습니다.</td></tr>`;
        } else {
            // Display first 100 preview rows
            const previewItems = items.slice(0, 100);
            previewItems.forEach((item, idx) => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${item.row_idx}</td>
                    <td><strong style="color: #60a5fa; font-size: 14px;">${escapeHtml(item.val)}</strong></td>
                    <td style="color: var(--text-muted); font-size: 12px;">${escapeHtml(item.summary)}</td>
                `;
                concatTableBody.appendChild(tr);
            });
        }

        concatPageInfo.textContent = `전체 ${items.length.toLocaleString()}개 중 상위 ${Math.min(items.length, 100)}개 표시 중`;
    }

    btnCopyConcatResult.addEventListener('click', () => {
        if (concatResults.length === 0) {
            alert('복사할 병합 결과 데이터가 없습니다.');
            return;
        }

        const textToCopy = concatResults.map(item => item.val).join('\n');
        navigator.clipboard.writeText(textToCopy).then(() => {
            showToast(`📋 병합 결과 ${concatResults.length.toLocaleString()}행 클립보드 복사 완료! (Ctrl+V로 엑셀에 붙여넣으세요)`);
        }).catch(err => {
            console.error(err);
            alert('클립보드 복사에 실패했습니다.');
        });
    });

    function copyToClipboard(format, tabKey) {
        if (!analysisResult || !analysisResult[tabKey]) {
            alert('복사할 데이터가 없습니다.');
            return;
        }

        const items = analysisResult[tabKey];
        let textToCopy = "";

        if (format === 'values_only') {
            textToCopy = items.map(item => item.val).join('\n');
        } else if (format === 'tsv_table') {
            const headers = ["번호", "데이터값", "구분(출처)", "A존재", "B존재"];
            const rows = items.map((item, idx) => 
                `${idx + 1}\t${item.val}\t${item.origin}\t${item.in_a}\t${item.in_b}`
            );
            textToCopy = [headers.join('\t'), ...rows].join('\n');
        }

        navigator.clipboard.writeText(textToCopy).then(() => {
            showToast(`📋 '${tabTitles[tabKey] || tabKey}' (${items.length}개) 클립보드에 복사 완료! (Ctrl+V로 붙여넣기 하세요)`);
        }).catch(err => {
            console.error('Clipboard copy failed:', err);
            alert('클립보드 복사 실패');
        });
    }

    function showToast(message) {
        toast.textContent = message;
        toast.classList.remove('hidden');
        setTimeout(() => {
            toast.classList.add('hidden');
        }, 3000);
    }

    function escapeHtml(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }
});

