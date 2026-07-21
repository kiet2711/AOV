/* ============================================================
   KGVN Load Tran — Frontend Script
   ============================================================ */

document.addEventListener('DOMContentLoaded', function () {

    // ── DOM refs ──
    const tokenInput      = document.getElementById('token');
    const verifyBtn       = document.getElementById('verifyBtn');
    const verifyBtnIcon   = document.getElementById('verifyBtnIcon');
    const verifyStatus    = document.getElementById('verifyStatus');
    const accountPreview  = document.getElementById('accountPreview');
    const previewPosterImg        = document.getElementById('previewPosterImg');
    const previewPosterPlaceholder= document.getElementById('previewPosterPlaceholder');
    const previewUID      = document.getElementById('previewUID');
    const previewPosterLabel = document.getElementById('previewPosterLabel');
    const accountNameInput= document.getElementById('accountNameInput');
    const saveAccountBtn  = document.getElementById('saveAccountBtn');
    const accountsList    = document.getElementById('accountsList');
    const noAccountsMsg   = document.getElementById('noAccountsMsg');
    const accountCountBadge = document.getElementById('accountCountBadge');
    const imageInput      = document.getElementById('imageInput');
    const imageElement    = document.getElementById('image');
    const cropperWrapper  = document.getElementById('cropperWrapper');
    const uploadBtn       = document.getElementById('uploadBtn');
    const logBox          = document.getElementById('logBox');
    const isShareInput    = document.getElementById('isShare');
    const renameModal     = document.getElementById('renameModal');
    const renameInput     = document.getElementById('renameInput');
    const renameCancelBtn = document.getElementById('renameCancelBtn');
    const renameConfirmBtn= document.getElementById('renameConfirmBtn');

    let cropper = null;
    let logInterval = null;
    let verifyDebounce = null;
    let currentVerifyData = null;   // thong tin tu verify thanh cong
    let renameTargetId = null;

    // ════════════════════════════════════════
    //  ACCOUNT MANAGEMENT
    // ════════════════════════════════════════

    async function loadAccounts() {
        try {
            const res = await fetch('/api/accounts');
            const data = await res.json();
            renderAccounts(data.accounts || []);
        } catch (e) {
            console.error('Load accounts failed', e);
        }
    }

    function renderAccounts(accounts) {
        accountCountBadge.textContent = `${accounts.length}/5`;
        accountsList.innerHTML = '';

        if (accounts.length === 0) {
            noAccountsMsg.style.display = 'flex';
            return;
        }
        noAccountsMsg.style.display = 'none';

        accounts.forEach(acc => {
            const card = document.createElement('div');
            card.className = 'account-card';
            card.dataset.id = acc.id;

            // Kiem tra xem dang dung account nay khong
            const isActive = currentVerifyData && currentVerifyData.user_id === acc.short_id?.padStart
                ? false
                : false; // se cap nhat sau

            // Status badge
            const statusMap = {
                new:     { cls: 'status-new',     label: '🟢 Mới' },
                old:     { cls: 'status-old',      label: '🟡 Cũ' },
                expired: { cls: 'status-expired',  label: '🔴 Hết hạn' },
            };
            const s = statusMap[acc.status] || statusMap.expired;

            // Age text
            let ageText = '';
            if (acc.age_minutes < 60) ageText = `${acc.age_minutes} phút trước`;
            else if (acc.age_minutes < 120) ageText = `${Math.floor(acc.age_minutes/60)}g ${acc.age_minutes%60}p trước`;
            else ageText = `${Math.floor(acc.age_minutes/60)} giờ trước`;

            // Poster image or placeholder
            const posterHtml = acc.current_poster_url
                ? `<img class="account-card-poster" src="${acc.current_poster_url}" alt="poster" onerror="this.style.display='none';this.nextSibling.style.display='flex'">`
                  + `<div class="account-card-poster-placeholder" style="display:none">🎮</div>`
                : `<div class="account-card-poster-placeholder">🎮</div>`;

            card.innerHTML = `
                <div class="account-card-actions">
                    <button class="account-card-btn rename-btn" title="Đổi tên">✏️</button>
                    <button class="account-card-btn del-btn" title="Xóa">🗑️</button>
                </div>
                ${posterHtml}
                <div class="account-card-name" title="${acc.name}">${acc.name}</div>
                <div class="account-card-uid">${acc.short_id || '——'}</div>
                <span class="status-badge ${s.cls}">${s.label}</span>
                <div style="font-size:0.62rem;color:var(--text-faint)">${ageText}</div>
            `;

            // Click card → load token
            card.addEventListener('click', (e) => {
                if (e.target.closest('.account-card-btn')) return;
                loadTokenFromAccount(acc.id, card);
            });

            // Rename
            card.querySelector('.rename-btn').addEventListener('click', () => {
                openRenameModal(acc.id, acc.name);
            });

            // Delete
            card.querySelector('.del-btn').addEventListener('click', () => {
                deleteAccount(acc.id);
            });

            accountsList.appendChild(card);
        });
    }

    async function loadTokenFromAccount(accountId, cardEl) {
        // Visual feedback
        document.querySelectorAll('.account-card').forEach(c => c.classList.remove('active-card'));
        cardEl.classList.add('active-card');

        try {
            const res = await fetch(`/api/accounts/${accountId}/token`);
            const data = await res.json();
            if (data.success) {
                tokenInput.value = data.token;
                verifyBtn.disabled = false;
                // Auto verify
                triggerVerify();
            }
        } catch (e) {
            console.error('Load token failed', e);
        }
    }

    async function saveAccount() {
        if (!currentVerifyData) return;

        const name = accountNameInput.value.trim() || null;
        saveAccountBtn.disabled = true;
        saveAccountBtn.textContent = '⏳ Đang lưu...';

        try {
            const res = await fetch('/api/accounts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    token: tokenInput.value.trim(),
                    name: name,
                    user_id: currentVerifyData.user_id,
                    short_id: currentVerifyData.short_id,
                    current_poster_url: currentVerifyData.current_poster_url,
                    user_path: currentVerifyData.user_path,
                })
            });
            const data = await res.json();
            if (data.success) {
                saveAccountBtn.textContent = data.updated ? '✅ Đã cập nhật!' : '✅ Đã lưu!';
                await loadAccounts();
                setTimeout(() => {
                    saveAccountBtn.textContent = '💾 Lưu tài khoản';
                    saveAccountBtn.disabled = false;
                }, 2000);
            }
        } catch (e) {
            saveAccountBtn.textContent = '❌ Lỗi lưu';
            setTimeout(() => {
                saveAccountBtn.textContent = '💾 Lưu tài khoản';
                saveAccountBtn.disabled = false;
            }, 2000);
        }
    }

    async function deleteAccount(accountId) {
        try {
            await fetch(`/api/accounts/${accountId}`, { method: 'DELETE' });
            await loadAccounts();
        } catch (e) {
            console.error('Delete failed', e);
        }
    }

    // ── Rename modal ──
    function openRenameModal(accountId, currentName) {
        renameTargetId = accountId;
        renameInput.value = currentName;
        renameModal.style.display = 'flex';
        setTimeout(() => renameInput.focus(), 50);
    }
    function closeRenameModal() {
        renameModal.style.display = 'none';
        renameTargetId = null;
    }
    renameCancelBtn.addEventListener('click', closeRenameModal);
    renameModal.addEventListener('click', (e) => {
        if (e.target === renameModal) closeRenameModal();
    });
    renameConfirmBtn.addEventListener('click', async () => {
        if (!renameTargetId) return;
        const name = renameInput.value.trim();
        if (!name) return;
        try {
            await fetch(`/api/accounts/${renameTargetId}/rename`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name })
            });
            closeRenameModal();
            await loadAccounts();
        } catch (e) {
            console.error('Rename failed', e);
        }
    });
    renameInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') renameConfirmBtn.click();
        if (e.key === 'Escape') closeRenameModal();
    });

    // ════════════════════════════════════════
    //  MODE / GENDER TOGGLE
    // ════════════════════════════════════════
    const modeSelect = document.getElementById('mode');
    const genderGroup = document.getElementById('genderGroup');
    modeSelect.addEventListener('change', () => {
        if (modeSelect.value.startsWith('flowborn_')) {
            genderGroup.style.display = 'block';
        } else {
            genderGroup.style.display = 'none';
        }
    });

    // ════════════════════════════════════════
    //  TOKEN VERIFY
    // ════════════════════════════════════════

    tokenInput.addEventListener('input', () => {
        const val = tokenInput.value.trim();
        verifyBtn.disabled = !val;
        if (currentVerifyData) {
            currentVerifyData = null;
            accountPreview.style.display = 'none';
            verifyStatus.style.display = 'none';
        }
        checkUploadReady();

        // Debounce auto-verify (1.2s sau khi dung go)
        clearTimeout(verifyDebounce);
        if (val.length > 20) {
            verifyDebounce = setTimeout(triggerVerify, 1200);
        }
    });

    verifyBtn.addEventListener('click', triggerVerify);

    function triggerVerify() {
        const token = tokenInput.value.trim();
        if (!token) return;
        clearTimeout(verifyDebounce);
        doVerify(token);
    }

    async function doVerify(token) {
        // Show loading
        verifyStatus.style.display = 'flex';
        verifyStatus.className = 'verify-status loading';
        verifyStatus.innerHTML = '<span class="spinner"></span> Đang xác thực token...';
        accountPreview.style.display = 'none';
        verifyBtnIcon.textContent = '⏳';
        verifyBtn.disabled = true;

        try {
            const res = await fetch('/api/verify_token', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token })
            });
            const data = await res.json();

            if (data.success) {
                // Success
                verifyStatus.className = 'verify-status success';
                verifyStatus.innerHTML = `✅ Token hợp lệ! Tài khoản đã được xác thực.`;
                verifyBtnIcon.textContent = '✅';

                currentVerifyData = data;

                // Update preview
                previewUID.textContent = data.short_id ? `${data.short_id}...` : '(không rõ)';
                if (data.current_poster_url) {
                    previewPosterImg.src = data.current_poster_url;
                    previewPosterImg.style.display = 'block';
                    previewPosterPlaceholder.style.display = 'none';
                    previewPosterLabel.textContent = '✅ Đang có ảnh tải trận';
                } else {
                    previewPosterImg.style.display = 'none';
                    previewPosterPlaceholder.style.display = 'flex';
                    previewPosterLabel.textContent = 'Chưa có ảnh tải trận';
                }

                // Check if this account already saved, auto-fill name
                const accRes = await fetch('/api/accounts');
                const accData = await accRes.json();
                const existing = (accData.accounts || []).find(a => a.short_id === data.short_id);
                if (existing) {
                    accountNameInput.value = existing.name;
                    // Highlight active card
                    document.querySelectorAll('.account-card').forEach(c => {
                        c.classList.toggle('active-card', c.dataset.id === existing.id);
                    });
                } else {
                    if (!accountNameInput.value.trim()) {
                        accountNameInput.value = 'Tài khoản ' + ((accData.accounts || []).length + 1);
                    }
                }

                accountPreview.style.display = 'flex';
                saveAccountBtn.disabled = false;
                saveAccountBtn.textContent = '💾 Lưu tài khoản';

                // Tự động lưu tài khoản
                saveAccount();

            } else {
                verifyStatus.className = 'verify-status error';
                verifyStatus.innerHTML = `❌ ${data.message || 'Token không hợp lệ'}`;
                verifyBtnIcon.textContent = '❌';
                currentVerifyData = null;
                accountPreview.style.display = 'none';
            }
        } catch (e) {
            verifyStatus.className = 'verify-status error';
            verifyStatus.innerHTML = '❌ Lỗi kết nối máy chủ. Thử lại sau.';
            verifyBtnIcon.textContent = '🔍';
        }

        verifyBtn.disabled = false;
        checkUploadReady();
    }

    saveAccountBtn.addEventListener('click', saveAccount);

    // ════════════════════════════════════════
    //  IMAGE CROP
    // ════════════════════════════════════════

    imageInput.addEventListener('change', function (e) {
        const files = e.target.files;
        if (!files || files.length === 0) return;

        const reader = new FileReader();
        reader.onload = function (ev) {
            imageElement.src = ev.target.result;
            cropperWrapper.style.display = 'block';
            if (cropper) { cropper.destroy(); }
            cropper = new Cropper(imageElement, {
                aspectRatio: 1080 / 1701,
                viewMode: 1,
                autoCropArea: 1,
                responsive: true,
            });
            checkUploadReady();
        };
        reader.readAsDataURL(files[0]);
    });

    function checkUploadReady() {
        uploadBtn.disabled = !(tokenInput.value.trim() && cropper);
    }

    // ════════════════════════════════════════
    //  UPLOAD
    // ════════════════════════════════════════

    uploadBtn.addEventListener('click', function () {
        if (!cropper) return;

        uploadBtn.disabled = true;
        uploadBtn.textContent = '⏳ Đang xử lý...';
        logBox.innerHTML = '';

        if (logInterval) clearInterval(logInterval);
        logInterval = setInterval(fetchLogs, 1200);

        cropper.getCroppedCanvas({
            width: 1080,
            height: 1701,
            fillColor: '#000',
            imageSmoothingEnabled: true,
            imageSmoothingQuality: 'high',
        }).toBlob(function (blob) {
            const formData = new FormData();
            formData.append('file', blob, 'cropped.jpg');
            formData.append('token', tokenInput.value.trim());
            formData.append('is_share', isShareInput.checked);
            formData.append('mode', document.getElementById('mode').value);
            formData.append('gender', document.getElementById('flowbornGender').value);

            fetch('/upload', { method: 'POST', body: formData })
                .then(r => r.json())
                .then(data => {
                    if (!data.success) {
                        appendLog('❌ ' + data.message, 'text-red');
                        stopPolling();
                    }
                })
                .catch(err => {
                    appendLog('❌ Lỗi kết nối server: ' + err, 'text-red');
                    stopPolling();
                });
        }, 'image/jpeg', 0.9);
    });

    // ════════════════════════════════════════
    //  LOG POLLING
    // ════════════════════════════════════════

    function fetchLogs() {
        fetch('/logs')
            .then(r => r.json())
            .then(data => {
                if (data.logs && data.logs.length > 0) {
                    data.logs.forEach(log => appendLog(log));
                    if (data.logs.some(l => l.includes('== HOÀN THÀNH =='))) {
                        stopPolling();
                    }
                }
            })
            .catch(console.error);
    }

    function appendLog(msg, colorClass) {
        const div = document.createElement('div');
        div.textContent = msg;

        if (colorClass) {
            div.className = colorClass;
        } else if (
            msg.includes('THÀNH CÔNG') || msg.includes('thành công') ||
            msg.includes('✅') || msg.includes('🎉')
        ) {
            div.className = 'text-green';
        } else if (
            msg.includes('❌') || msg.includes('thất bại') ||
            msg.includes('Lỗi') || msg.includes('không hợp lệ')
        ) {
            div.className = 'text-red';
        } else if (
            msg.includes('⚠️') || msg.includes('mặc định')
        ) {
            div.className = 'text-yellow';
        } else if (
            msg.includes('🔑') || msg.includes('⏳') || msg.includes('☁️') ||
            msg.includes('🔄') || msg.includes('📤') || msg.includes('💾') ||
            msg.includes('🔍') || msg.includes('🚀') || msg.includes('🖼️') ||
            msg.includes('📊') || msg.includes('== ')
        ) {
            div.className = 'text-blue';
        }

        logBox.appendChild(div);
        logBox.scrollTop = logBox.scrollHeight;
    }

    function stopPolling() {
        if (logInterval) { clearInterval(logInterval); logInterval = null; }
        uploadBtn.disabled = false;
        uploadBtn.textContent = '📤 Tải lên & Xử lý';
    }

    // ════════════════════════════════════════
    //  INIT
    // ════════════════════════════════════════
    loadAccounts();

    // Reload accounts every 60s to update badges
    setInterval(loadAccounts, 60000);
});
