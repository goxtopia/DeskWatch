// DeskWatch - Review Tab Module

async function loadReviewData() {
    if (!config) await fetchConfig();
    
    try {
        const res = await fetch("/api/records/unreviewed");
        unreviewedRecords = await res.json();
        reviewIndex = 0;
        
        // Update review badges globally
        updateReviewBadgeCount(unreviewedRecords.length);
        
        renderReviewImage();
    } catch (e) {
        console.error("Error loading unreviewed records:", e);
        showToast("获取审查列表失败", "error");
    }
}

function updateReviewBadgeCount(count) {
    const reviewBadge = document.getElementById("review-badge");
    if (!reviewBadge) return;
    if (count > 0) {
        reviewBadge.innerText = count;
        reviewBadge.style.display = "inline-block";
    } else {
        reviewBadge.style.display = "none";
    }
}

function renderReviewImage() {
    const placeholder = document.getElementById("review-placeholder");
    const image = document.getElementById("review-image");
    const detailPane = document.getElementById("review-details-pane");
    const emptyPane = document.getElementById("review-empty-pane");
    
    document.getElementById("review-total-count").innerText = unreviewedRecords.length;
    
    if (unreviewedRecords.length === 0 || reviewIndex >= unreviewedRecords.length) {
        placeholder.style.display = "flex";
        image.style.display = "none";
        detailPane.style.display = "none";
        emptyPane.style.display = "flex";
        document.getElementById("review-current-index").innerText = "0";
        return;
    }
    
    placeholder.style.display = "none";
    image.style.display = "block";
    detailPane.style.display = "flex";
    emptyPane.style.display = "none";
    
    const record = unreviewedRecords[reviewIndex];
    document.getElementById("review-current-index").innerText = reviewIndex + 1;
    image.src = `/${record.image_path}?t=${new Date().getTime()}`;
    
    document.getElementById("review-time").innerText = record.timestamp;
    document.getElementById("review-model").innerText = record.model_type.toUpperCase();
    document.getElementById("review-predicted").innerText = record.predicted_label;
    document.getElementById("review-confidence-val").innerText = record.confidence ? `${Math.round(record.confidence * 100)}%` : "N/A";
    
    // Render action buttons
    renderReviewCategoriesButtons(record.predicted_label);
}

function renderReviewCategoriesButtons(predictedLabel) {
    const container = document.getElementById("review-categories-buttons");
    container.innerHTML = "";
    
    if (!config || !config.categories) return;
    
    config.categories.forEach((cat, idx) => {
        const btn = document.createElement("button");
        btn.className = "btn-category-select";
        
        // Highlight if predicted
        if (cat === predictedLabel) {
            btn.style.borderColor = "var(--primary)";
            btn.style.backgroundColor = "var(--primary-light)";
        }
        
        const numberBadge = idx < 9 ? `<span class="category-number-badge">${idx + 1}</span>` : "";
        
        btn.innerHTML = `
            <span>${cat}</span>
            ${numberBadge}
        `;
        
        btn.addEventListener("click", () => reviewChoice(cat));
        container.appendChild(btn);
    });
}

async function reviewChoice(label) {
    if (unreviewedRecords.length === 0 || reviewIndex >= unreviewedRecords.length) return;
    
    const record = unreviewedRecords[reviewIndex];
    try {
        const res = await fetch(`/api/records/${record.id}/review`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ corrected_label: label })
        });
        const data = await res.json();
        
        if (data.status === "success") {
            showToast(`已成功归档至类 [${label}]`, "success");
            
            // Remove from local array
            unreviewedRecords.splice(reviewIndex, 1);
            
            // Adjust index if we deleted the last item
            if (reviewIndex >= unreviewedRecords.length && reviewIndex > 0) {
                reviewIndex = unreviewedRecords.length - 1;
            }
            
            updateReviewBadgeCount(unreviewedRecords.length);
            renderReviewImage();
        } else {
            showToast("归档失败", "error");
        }
    } catch (e) {
        showToast("接口请求失败", "error");
    }
}

// Bind Review Handlers on module load / inside DOMContentLoaded initialization
function initReviewHandlers() {
    const skipBtn = document.getElementById("btn-skip-image");
    if (skipBtn) {
        skipBtn.addEventListener("click", () => {
            if (unreviewedRecords.length <= 1) return;
            reviewIndex = (reviewIndex + 1) % unreviewedRecords.length;
            renderReviewImage();
        });
    }
    
    const deleteBtn = document.getElementById("btn-delete-image");
    if (deleteBtn) {
        deleteBtn.addEventListener("click", async () => {
            if (unreviewedRecords.length === 0 || reviewIndex >= unreviewedRecords.length) return;
            
            const record = unreviewedRecords[reviewIndex];
            if (confirm("确定要永久删除此图片和记录吗？")) {
                try {
                    const res = await fetch(`/api/records/${record.id}`, { method: "DELETE" });
                    const result = await res.json();
                    
                    if (result.status === "success") {
                        showToast("记录已删除", "success");
                        unreviewedRecords.splice(reviewIndex, 1);
                        if (reviewIndex >= unreviewedRecords.length && reviewIndex > 0) {
                            reviewIndex = unreviewedRecords.length - 1;
                        }
                        updateReviewBadgeCount(unreviewedRecords.length);
                        renderReviewImage();
                    } else {
                        showToast("删除失败", "error");
                    }
                } catch (e) {
                    showToast("接口请求失败", "error");
                }
            }
        });
    }
    
    // KEYBOARD HOTKEYS FOR QUICK REVIEW
    window.addEventListener("keydown", (e) => {
        const reviewTab = document.getElementById("review-tab");
        if (!reviewTab || !reviewTab.classList.contains("active")) return;
        
        if (document.activeElement.tagName === "INPUT" || document.activeElement.tagName === "TEXTAREA") {
            return;
        }
        
        const key = e.key;
        if (key >= "1" && key <= "9") {
            const idx = parseInt(key) - 1;
            const buttons = document.querySelectorAll("#review-categories-buttons .btn-category-select");
            if (buttons && buttons[idx]) {
                buttons[idx].click();
            }
        }
    });
}
