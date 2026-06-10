// DeskWatch - Frontend JS App Entry

// Application State
var config = null;
var unreviewedRecords = [];
var reviewIndex = 0;
var trainingInterval = null;
var lastLogIndex = 0;
var cameraStatusInterval = null;
var chartInstance = null;
var lastDashboardCaptureTime = null;
var isCurrentlySedentaryAlert = false;
var lastReminderTime = 0;

var historyCurrentPage = 1;
var historyTotalPages = 1;
const historyLimit = 12;

// Theme colors map for categories
const categoryColors = [
    'hsl(262, 80%, 65%)',  // Purple
    'hsl(190, 85%, 50%)',  // Cyan
    'hsl(145, 65%, 48%)',  // Green
    'hsl(35, 90%, 52%)',   // Orange
    'hsl(343, 80%, 60%)',  // Pink
    'hsl(210, 85%, 55%)',  // Blue
    'hsl(48, 95%, 52%)',   // Yellow
    'hsl(10, 85%, 58%)'    // Red
];

// Toast Notification helper
function showToast(message, type = "info") {
    const container = document.getElementById("toast-container");
    if (!container) return;
    
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    
    let icon = "ph-info";
    if (type === "success") icon = "ph-check-circle";
    if (type === "error") icon = "ph-warning-circle";
    
    toast.innerHTML = `
        <i class="ph-bold ${icon}"></i>
        <span class="toast-message">${message}</span>
    `;
    
    container.appendChild(toast);
    
    // Trigger reflow
    toast.offsetHeight;
    toast.classList.add("show");
    
    setTimeout(() => {
        toast.classList.remove("show");
        setTimeout(() => toast.remove(), 400);
    }, 3000);
}
window.showToast = showToast;

// FETCH CONFIG HELPER
async function fetchConfig() {
    try {
        const res = await fetch("/api/config");
        config = await res.json();
        
        // Set current running model in stats
        const activeModelBadge = document.getElementById("stat-active-model");
        if (activeModelBadge) {
            activeModelBadge.innerText = config.active_model.toUpperCase();
        }
    } catch (e) {
        console.error("Error fetching config:", e);
    }
}

// CAMERA AND CAPTURE ACTIONS
async function fetchCameraStatus() {
    try {
        const res = await fetch("/api/camera/status");
        const data = await res.json();
        
        // Handle Sedentary Status and Dispatch Events
        const isRunning = data.is_running;
        if (isRunning && data.sedentary_status) {
            const sed = data.sedentary_status;
            
            // Update inactive time in UI
            const inactiveTimeEl = document.getElementById("stat-inactive-time");
            if (inactiveTimeEl) {
                const min = Math.round(sed.inactive_minutes || 0);
                inactiveTimeEl.innerText = `${min}m`;
            }

            if (sed.is_sedentary) {
                const now = Date.now();
                const snoozeMinutes = (config && config.sedentary_snooze_minutes) || 5;
                const snoozeMs = snoozeMinutes * 60 * 1000;
                if (!isCurrentlySedentaryAlert || (now - lastReminderTime > snoozeMs)) {
                    isCurrentlySedentaryAlert = true;
                    lastReminderTime = now;
                    if (window.HealthEvents) {
                        window.HealthEvents.emit('sedentary', { minutes: sed.sedentary_minutes });
                    }
                }
            } else {
                if (isCurrentlySedentaryAlert) {
                    isCurrentlySedentaryAlert = false;
                    lastReminderTime = 0;
                    if (window.HealthEvents) {
                        window.HealthEvents.emit('clear_sedentary');
                    }
                }
            }
        } else {
            const inactiveTimeEl = document.getElementById("stat-inactive-time");
            if (inactiveTimeEl) {
                inactiveTimeEl.innerText = "0m";
            }
            if (isCurrentlySedentaryAlert) {
                isCurrentlySedentaryAlert = false;
                lastReminderTime = 0;
                if (window.HealthEvents) {
                    window.HealthEvents.emit('clear_sedentary');
                }
            }
        }
        
        const toggleCaptureBtn = document.getElementById("toggle-capture-btn");
        const navStatusDot = document.getElementById("nav-status-dot");
        const navStatusText = document.getElementById("nav-status-text");
        const navStatusDesc = document.getElementById("nav-status-desc");
        
        // Navigation badge & button state
        if (toggleCaptureBtn && navStatusDot && navStatusText) {
            if (isRunning) {
                toggleCaptureBtn.className = "btn btn-danger btn-glow";
                toggleCaptureBtn.innerHTML = `<i class="ph-bold ph-stop"></i><span>停止监控</span>`;
                
                navStatusDot.className = "status-dot active";
                navStatusText.innerText = "监控中";
            } else {
                toggleCaptureBtn.className = "btn btn-primary btn-glow";
                toggleCaptureBtn.innerHTML = `<i class="ph-bold ph-play"></i><span>开启监控</span>`;
                
                navStatusDot.className = "status-dot disconnected";
                navStatusText.innerText = "已停止";
            }
        }
        
        // Status card description
        if (navStatusDesc) {
            if (data.status === "Active") {
                navStatusDesc.innerText = `采集状态正常。最新时间: ${data.last_capture_time.substring(11)}`;
                
                // If there's a new capture, refresh stats and timeline in real-time!
                if (data.last_capture_time && data.last_capture_time !== lastDashboardCaptureTime) {
                    lastDashboardCaptureTime = data.last_capture_time;
                    const activeTabEl = document.querySelector(".menu-item.active");
                    const activeTab = activeTabEl ? activeTabEl.getAttribute("data-tab") : "";
                    if (activeTab === "dashboard-tab") {
                        loadDashboardData();
                    }
                }
                
                // If on dashboard, update live preview
                if (data.last_prediction) {
                    const previewPlaceholder = document.getElementById("preview-placeholder");
                    if (previewPlaceholder) previewPlaceholder.style.display = "none";
                    
                    const imgEl = document.getElementById("preview-image");
                    if (imgEl) {
                        imgEl.src = `/${data.last_prediction.image_path}?t=${new Date().getTime()}`;
                        imgEl.style.display = "block";
                    }
                    
                    const overlayEl = document.getElementById("preview-overlay");
                    if (overlayEl) overlayEl.style.display = "flex";
                    
                    const previewLabel = document.getElementById("preview-label");
                    if (previewLabel) previewLabel.innerText = data.last_prediction.label;
                    
                    const previewConfidence = document.getElementById("preview-confidence");
                    if (previewConfidence) previewConfidence.innerText = `${Math.round(data.last_prediction.confidence * 100)}%`;
                    
                    const previewTimestamp = document.getElementById("preview-timestamp");
                    if (previewTimestamp) previewTimestamp.innerText = data.last_capture_time.substring(11);
                }
            } else if (data.status === "Capturing...") {
                if (navStatusDot && navStatusText) {
                    navStatusDot.className = "status-dot loading";
                    navStatusText.innerText = "画面抓取";
                }
                navStatusDesc.innerText = "摄像头正在截取帧...";
            } else if (data.status === "Classifying...") {
                if (navStatusDot && navStatusText) {
                    navStatusDot.className = "status-dot loading";
                    navStatusText.innerText = "推理分析";
                }
                navStatusDesc.innerText = "模型正在分类画面行为...";
            } else if (data.status === "Error") {
                if (navStatusDot && navStatusText) {
                    navStatusDot.className = "status-dot disconnected";
                    navStatusText.innerText = "监测错误";
                }
                navStatusDesc.innerText = data.last_error || "采集失败";
            } else {
                navStatusDesc.innerText = "等待开启监控。";
            }
        }
        
    } catch (e) {
        console.error("Error getting camera status:", e);
    }
}

document.addEventListener("DOMContentLoaded", () => {
    // UI Elements
    const tabs = document.querySelectorAll(".menu-item[data-tab]");
    const tabContents = document.querySelectorAll(".tab-content");
    const pageTitle = document.getElementById("page-title");
    const pageSubtitle = document.getElementById("page-subtitle");
    const toggleCaptureBtn = document.getElementById("toggle-capture-btn");
    
    // TAB ROUTING
    tabs.forEach(tab => {
        tab.addEventListener("click", () => {
            tabs.forEach(t => t.classList.remove("active"));
            tabContents.forEach(c => c.classList.remove("active"));
            
            tab.classList.add("active");
            const targetTab = tab.getAttribute("data-tab");
            document.getElementById(targetTab).classList.add("active");
            
            // Update Headers
            if (targetTab === "dashboard-tab") {
                pageTitle.innerText = "监控大屏";
                pageSubtitle.innerText = "实时监测桌面活动与分类统计";
                loadDashboardData();
            } else if (targetTab === "review-tab") {
                pageTitle.innerText = "人工核对与审查";
                pageSubtitle.innerText = "人工校正预测结果并将其归档至训练集";
                loadReviewData();
            } else if (targetTab === "history-tab") {
                pageTitle.innerText = "历史相册";
                pageSubtitle.innerText = "相册式回顾所有已采集的历史样本，可进行二次校对或删除";
                loadHistoryData(1);
            } else if (targetTab === "training-tab") {
                pageTitle.innerText = "模型训练中心";
                pageSubtitle.innerText = "使用标注的更正数据微调本地 ConvNeXt 分类模型";
                loadTrainingData();
            } else if (targetTab === "settings-tab") {
                pageTitle.innerText = "系统配置";
                pageSubtitle.innerText = "配置摄像头源、采样频率与分类器选项";
                loadSettingsData();
            }
        });
    });
    
    if (toggleCaptureBtn) {
        toggleCaptureBtn.addEventListener("click", async () => {
            try {
                const res = await fetch("/api/camera/status");
                const data = await res.json();
                const endpoint = data.is_running ? "/api/camera/stop" : "/api/camera/start";
                
                const toggleRes = await fetch(endpoint, { method: "POST" });
                const result = await toggleRes.json();
                
                showToast(result.message, result.status === "success" ? "success" : "error");
                fetchCameraStatus();
                
                // Reload dashboard if starting
                if (endpoint === "/api/camera/start") {
                    setTimeout(loadDashboardData, 1000);
                }
            } catch (e) {
                showToast("控制摄像头失败", "error");
            }
        });
    }
    
    // Initialize handlers from different modules
    if (typeof initReviewHandlers === "function") initReviewHandlers();
    if (typeof initHistoryHandlers === "function") initHistoryHandlers();
    if (typeof initTrainingHandlers === "function") initTrainingHandlers();
    if (typeof initSettingsHandlers === "function") initSettingsHandlers();
    
    // Main Initialization
    async function init() {
        await fetchConfig();
        loadDashboardData();
        fetchCameraStatus();
        
        // Polling loop for camera status
        cameraStatusInterval = setInterval(fetchCameraStatus, 3000);
        
        // Initial review badge check
        try {
            const res = await fetch("/api/records/unreviewed");
            const records = await res.json();
            updateReviewBadgeCount(records.length);
        } catch(e) {}
        
        // Notification permission request and testing
        const btnReqNotification = document.getElementById("btn-request-notification");
        if (btnReqNotification) {
            btnReqNotification.addEventListener("click", async () => {
                await window.requestNotificationPermission();
                window.sendTestNotification();
            });
        }
        if (window.updateNotificationPermissionStatus) {
            window.updateNotificationPermissionStatus();
        }
    }
    
    init();
});
