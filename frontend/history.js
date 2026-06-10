// DeskWatch - History Tab Module

let activeDetailRecord = null;

async function loadHistoryData(page = 1) {
    if (!config) await fetchConfig();
    
    historyCurrentPage = page;
    
    const filterDateInput = document.getElementById("filter-date");
    const filterReviewedSelect = document.getElementById("filter-reviewed");
    
    const dateVal = filterDateInput ? filterDateInput.value : "";
    const reviewedVal = filterReviewedSelect ? filterReviewedSelect.value : "";
    
    let url = `/api/records?limit=${historyLimit}&offset=${(page - 1) * historyLimit}`;
    if (dateVal) {
        url += `&date=${dateVal}`;
    }
    if (reviewedVal !== "") {
        url += `&reviewed=${reviewedVal}`;
    }
    
    try {
        const res = await fetch(url);
        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || `HTTP ${res.status}`);
        }
        const data = await res.json();
        
        const total = data.total || 0;
        const records = data.records || [];
        
        historyTotalPages = Math.max(1, Math.ceil(total / historyLimit));
        
        // Update total label
        document.getElementById("history-total-count").innerText = total;
        document.getElementById("history-current-page").innerText = historyCurrentPage;
        document.getElementById("history-total-pages").innerText = historyTotalPages;
        
        // Update pagination buttons
        const btnHistoryPrev = document.getElementById("btn-history-prev");
        const btnHistoryNext = document.getElementById("btn-history-next");
        if (btnHistoryPrev) btnHistoryPrev.disabled = historyCurrentPage <= 1;
        if (btnHistoryNext) btnHistoryNext.disabled = historyCurrentPage >= historyTotalPages;
        
        renderHistoryGrid(records);
    } catch (e) {
        console.error("Error fetching history records:", e);
        showToast("获取历史样本失败", "error");
    }
}

function renderHistoryGrid(records) {
    const grid = document.getElementById("history-gallery-grid");
    const emptyEl = document.getElementById("history-gallery-empty");
    
    grid.innerHTML = "";
    
    if (records.length === 0) {
        grid.style.display = "none";
        emptyEl.style.display = "flex";
        return;
    }
    
    grid.style.display = "grid";
    emptyEl.style.display = "none";
    
    records.forEach((record, index) => {
        const card = document.createElement("div");
        card.className = "photo-card";
        
        const isReviewed = record.reviewed === 1;
        const label = isReviewed ? record.corrected_label : record.predicted_label;
        const badgeClass = isReviewed ? "reviewed" : "unreviewed";
        const badgeText = isReviewed ? "已核对" : "未核对";
        const confPct = record.confidence ? `${Math.round(record.confidence * 100)}%` : "N/A";
        
        card.innerHTML = `
            <div class="photo-card-img-wrapper">
                <img src="/${record.image_path}?t=${new Date().getTime()}" alt="Record capture" loading="lazy">
                <span class="photo-card-badge ${badgeClass}">${badgeText}</span>
            </div>
            <div class="photo-card-meta">
                <h4 class="photo-card-title">${label}</h4>
                <span class="photo-card-time"><i class="ph ph-clock"></i>${record.timestamp}</span>
                <div class="photo-card-footer">
                    <span class="photo-card-model">${record.model_type.toUpperCase()}</span>
                    <span class="photo-card-conf">${confPct}</span>
                </div>
            </div>
        `;
        
        card.addEventListener("click", () => openDetailModal(record));
        grid.appendChild(card);
    });
}

function openDetailModal(record) {
    activeDetailRecord = record;
    
    document.getElementById("modal-detail-id").innerText = record.id;
    document.getElementById("modal-detail-time").innerText = record.timestamp;
    document.getElementById("modal-detail-model").innerText = record.model_type.toUpperCase();
    document.getElementById("modal-detail-predicted").innerText = record.predicted_label;
    document.getElementById("modal-detail-confidence").innerText = record.confidence ? `${Math.round(record.confidence * 100)}%` : "N/A";
    
    const statusBadge = document.getElementById("modal-detail-status");
    if (record.reviewed === 1) {
        statusBadge.className = "status-badge active";
        statusBadge.innerText = "已核对 (更正为: " + record.corrected_label + ")";
    } else {
        statusBadge.className = "status-badge";
        statusBadge.innerText = "未核对";
    }
    
    const detailImg = document.getElementById("modal-detail-image");
    detailImg.src = `/${record.image_path}?t=${new Date().getTime()}`;
    
    renderModalCategoryButtons();
    
    const historyModal = document.getElementById("history-modal");
    historyModal.style.display = "flex";
    setTimeout(() => historyModal.classList.add("show"), 10);
}

function closeDetailModal() {
    const historyModal = document.getElementById("history-modal");
    if (!historyModal) return;
    historyModal.classList.remove("show");
    setTimeout(() => {
        historyModal.style.display = "none";
        activeDetailRecord = null;
    }, 300);
}

function renderModalCategoryButtons() {
    const container = document.getElementById("modal-categories-grid");
    container.innerHTML = "";
    
    if (!config || !config.categories || !activeDetailRecord) return;
    
    const activeLabel = activeDetailRecord.reviewed === 1 ? activeDetailRecord.corrected_label : activeDetailRecord.predicted_label;
    
    config.categories.forEach((cat, idx) => {
        const btn = document.createElement("button");
        btn.className = "btn-category-select";
        
        if (cat === activeLabel) {
            btn.style.borderColor = "var(--primary)";
            btn.style.backgroundColor = "var(--primary-light)";
            btn.style.color = "var(--text-primary)";
        }
        
        btn.innerHTML = `<span>${cat}</span>`;
        btn.addEventListener("click", () => correctRecordLabel(cat));
        container.appendChild(btn);
    });
}

async function correctRecordLabel(label) {
    if (!activeDetailRecord) return;
    
    try {
        const res = await fetch(`/api/records/${activeDetailRecord.id}/review`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ corrected_label: label })
        });
        const data = await res.json();
        
        if (data.status === "success") {
            showToast(`标注已成功更新为 [${label}]`, "success");
            
            activeDetailRecord.reviewed = 1;
            activeDetailRecord.corrected_label = label;
            
            const statusBadge = document.getElementById("modal-detail-status");
            statusBadge.className = "status-badge active";
            statusBadge.innerText = "已核对 (更正为: " + label + ")";
            
            renderModalCategoryButtons();
            loadHistoryData(historyCurrentPage);
            
            try {
                const resReview = await fetch("/api/records/unreviewed");
                const unreviewed = await resReview.json();
                updateReviewBadgeCount(unreviewed.length);
            } catch(err) {}
        } else {
            showToast("更新标注失败", "error");
        }
    } catch (e) {
        showToast("请求失败", "error");
    }
}

function initHistoryHandlers() {
    const filterDateInput = document.getElementById("filter-date");
    const filterReviewedSelect = document.getElementById("filter-reviewed");
    const btnResetFilters = document.getElementById("btn-reset-filters");
    
    if (filterDateInput) {
        filterDateInput.addEventListener("change", () => loadHistoryData(1));
    }
    if (filterReviewedSelect) {
        filterReviewedSelect.addEventListener("change", () => loadHistoryData(1));
    }
    if (btnResetFilters) {
        btnResetFilters.addEventListener("click", () => {
            filterDateInput.value = "";
            filterReviewedSelect.value = "";
            loadHistoryData(1);
        });
    }
    
    const btnHistoryPrev = document.getElementById("btn-history-prev");
    const btnHistoryNext = document.getElementById("btn-history-next");
    
    if (btnHistoryPrev) {
        btnHistoryPrev.addEventListener("click", () => {
            if (historyCurrentPage > 1) {
                loadHistoryData(historyCurrentPage - 1);
            }
        });
    }
    if (btnHistoryNext) {
        btnHistoryNext.addEventListener("click", () => {
            if (historyCurrentPage < historyTotalPages) {
                loadHistoryData(historyCurrentPage + 1);
            }
        });
    }
    
    const btnCloseHistoryModal = document.getElementById("btn-close-history-modal");
    const btnModalDelete = document.getElementById("btn-modal-delete");
    const historyModal = document.getElementById("history-modal");
    
    if (btnCloseHistoryModal) {
        btnCloseHistoryModal.addEventListener("click", closeDetailModal);
    }
    if (historyModal) {
        historyModal.addEventListener("click", (e) => {
            if (e.target === historyModal) {
                closeDetailModal();
            }
        });
    }
    if (btnModalDelete) {
        btnModalDelete.addEventListener("click", async () => {
            if (!activeDetailRecord) return;
            if (confirm("确定要永久删除此图片和记录吗？此操作不可撤销。")) {
                try {
                    const res = await fetch(`/api/records/${activeDetailRecord.id}`, { method: "DELETE" });
                    const result = await res.json();
                    
                    if (result.status === "success") {
                        showToast("记录已删除", "success");
                        closeDetailModal();
                        loadHistoryData(historyCurrentPage);
                        try {
                            const resReview = await fetch("/api/records/unreviewed");
                            const unreviewed = await resReview.json();
                            updateReviewBadgeCount(unreviewed.length);
                        } catch(err) {}
                    } else {
                        showToast("删除失败", "error");
                    }
                } catch (e) {
                    showToast("接口请求失败", "error");
                }
            }
        });
    }
}
