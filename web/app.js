document.addEventListener('DOMContentLoaded', () => {
    // State
    let currentFileId = null;
    let currentFileName = null;
    let analysisResult = null;
    let activeTab = 'intersection';
    let currentPage = 1;
    const pageSize = 50;
    let searchQuery = '';

    // DOM Elements
    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('file-input');
    const fileInfo = document.getElementById('file-info');
    const fileNameSpan = document.getElementById('file-name');
    const btnChangeFile = document.getElementById('btn-change-file');

    const setupForm = document.getElementById('setup-form');
    const sheetSelectA = document.getElementById('sheet-select-a');
    const colSelectA = document.getElementById('col-select-a');
    const colSelectB = document.getElementById('col-select-b');
    
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

    // Drag & Drop
    ['dragenter', 'dragover'].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            dropzone.classList.add('dragover');
        });
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            dropzone.classList.remove('dragover');
        });
    });

    dropzone.addEventListener('drop', (e) => {
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleFileUpload(files[0]);
        }
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFileUpload(e.target.files[0]);
        }
    });

    btnChangeFile.addEventListener('click', () => {
        fileInput.value = '';
        dropzone.classList.remove('hidden');
        fileInfo.classList.add('hidden');
        setupForm.classList.add('disabled');
        currentFileId = null;
    });

    async function handleFileUpload(file) {
        const formData = new FormData();
        formData.append('file', file);

        try {
            const res = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });

            if (!res.ok) {
                const err = await res.json();
                alert('파일 업로드 오류: ' + (err.error || '업로드 실패'));
                return;
            }

            const data = await res.json();
            currentFileId = data.file_id;
            currentFileName = data.filename;

            fileNameSpan.textContent = currentFileName;
            dropzone.classList.add('hidden');
            fileInfo.classList.remove('hidden');
            setupForm.classList.remove('disabled');

            sheetSelectA.innerHTML = '';
            data.sheets.forEach(sheet => {
                const opt = document.createElement('option');
                opt.value = sheet;
                opt.textContent = sheet;
                sheetSelectA.appendChild(opt);
            });

            if (data.sheets.length > 0) {
                await loadColumns(data.sheets[0]);
            }
        } catch (err) {
            console.error(err);
            alert('파일 처리 중 오류가 발생했습니다.');
        }
    }

    sheetSelectA.addEventListener('change', async (e) => {
        if (currentFileId) {
            await loadColumns(e.target.value);
        }
    });

    async function loadColumns(sheetName) {
        try {
            const res = await fetch('/api/columns', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file_id: currentFileId, sheet_name: sheetName })
            });

            if (!res.ok) return;

            const data = await res.json();
            colSelectA.innerHTML = '';
            colSelectB.innerHTML = '';

            data.columns.forEach((col, idx) => {
                const optA = document.createElement('option');
                optA.value = col;
                optA.textContent = col;
                colSelectA.appendChild(optA);

                const optB = document.createElement('option');
                optB.value = col;
                optB.textContent = col;
                colSelectB.appendChild(optB);
            });

            if (data.columns.length > 1) {
                colSelectB.selectedIndex = 1;
            }
        } catch (err) {
            console.error(err);
        }
    }

    // Load Sample Button
    btnLoadSample.addEventListener('click', async () => {
        try {
            const res = await fetch('/api/sample');
            const data = await res.json();
            
            currentFileId = data.file_id;
            currentFileName = "sample_data.xlsx";

            fileNameSpan.textContent = currentFileName;
            dropzone.classList.add('hidden');
            fileInfo.classList.remove('hidden');
            setupForm.classList.remove('disabled');

            sheetSelectA.innerHTML = '<option value="임직원비교">임직원비교</option>';
            colSelectA.innerHTML = '<option value="전산팀_명단">전산팀_명단</option>';
            colSelectB.innerHTML = '<option value="인사팀_등록명단">인사팀_등록명단</option>';

            await runAnalysis();
        } catch (err) {
            console.error(err);
            alert('샘플 데이터 로드 실패');
        }
    });

    btnAnalyze.addEventListener('click', async () => {
        await runAnalysis();
    });

    async function runAnalysis() {
        if (!currentFileId) {
            alert('엑셀 파일을 업로드해주세요.');
            return;
        }

        const payload = {
            file_id: currentFileId,
            sheet_a: sheetSelectA.value,
            col_a: colSelectA.value,
            sheet_b: sheetSelectA.value,
            col_b: colSelectB.value,
            case_sensitive: optCase.checked,
            trim_space: optTrim.checked,
            drop_empty: optDropEmpty.checked
        };

        try {
            btnAnalyze.disabled = true;
            btnAnalyze.innerHTML = '<span>⏳ 분석 중...</span>';

            const res = await fetch('/api/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (!res.ok) {
                const err = await res.json();
                alert('분석 오류: ' + (err.error || '오류 발생'));
                return;
            }

            analysisResult = await res.json();
            renderDashboard();
        } catch (err) {
            console.error(err);
            alert('분석 중 오류가 발생했습니다.');
        } finally {
            btnAnalyze.disabled = false;
            btnAnalyze.innerHTML = '<span>⚡ 집합 비교 분석 수행</span>';
        }
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
    // CLIPBOARD COPY LOGIC
    // -------------------------------------------------------------
    btnCopyValuesOnly.addEventListener('click', () => {
        copyToClipboard('values_only', activeTab);
    });

    btnCopyTable.addEventListener('click', () => {
        copyToClipboard('tsv_table', activeTab);
    });

    document.querySelectorAll('.btn-copy-mini').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const type = e.target.getAttribute('data-type');
            copyToClipboard('values_only', type);
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
            // 줄바꿈 구분 (엑셀 1컬럼 붙여넣기 최적화)
            textToCopy = items.map(item => item.val).join('\n');
        } else if (format === 'tsv_table') {
            # TSV 표 형태 (엑셀 여러 컬럼 붙여넣기 최적화)
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
