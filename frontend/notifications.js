// DeskWatch - Frontend Health Events and Notification Module
(function () {
    // Simple Event Emitter
    class EventEmitter {
        constructor() {
            this.events = {};
        }
        
        on(event, listener) {
            if (!this.events[event]) {
                this.events[event] = [];
            }
            this.events[event].push(listener);
        }
        
        off(event, listener) {
            if (!this.events[event]) return;
            this.events[event] = this.events[event].filter(l => l !== listener);
        }
        
        emit(event, data) {
            if (!this.events[event]) return;
            this.events[event].forEach(listener => {
                try {
                    listener(data);
                } catch (e) {
                    console.error(`Error in event listener for ${event}:`, e);
                }
            });
        }
    }

    const HealthEvents = new EventEmitter();
    
    // Store scheduled timeout IDs for sedentary warnings
    let alertTimeouts = [];
    
    // Handle sedentary alert event
    HealthEvents.on('sedentary', (data) => {
        // Clear any existing timeouts first
        clearPendingAlerts();
        
        const sedentaryMinutes = data.minutes || 0;
        
        // Define notification schedule: 3 alerts spaced 15s apart (at 0s, 15s, 30s)
        const triggerWarning = (index) => {
            const title = "久坐提醒 - DeskWatch";
            const body = `您已连续工作约 ${Math.round(sedentaryMinutes)} 分钟！为了您的健康，请站起来活动活动。 [提醒 ${index}/3]`;
            
            // 1. Browser Native Notification
            if (Notification.permission === "granted") {
                try {
                    new Notification(title, {
                        body: body,
                        icon: "/favicon.ico"
                    });
                } catch (err) {
                    console.error("Failed to send native notification:", err);
                }
            }
            
            // 2. In-app Toast message
            if (window.showToast) {
                window.showToast(body, "warning");
            }
        };
        
        // Schedule the 3 warnings
        triggerWarning(1); // Immediate (0s)
        
        const timeout1 = setTimeout(() => triggerWarning(2), 15000); // 15s
        const timeout2 = setTimeout(() => triggerWarning(3), 30000); // 30s
        
        alertTimeouts.push(timeout1, timeout2);
    });
    
    // Handle clear event
    HealthEvents.on('clear_sedentary', () => {
        clearPendingAlerts();
    });
    
    function clearPendingAlerts() {
        alertTimeouts.forEach(t => clearTimeout(t));
        alertTimeouts = [];
    }
    
    // Helper function to check/request permission and send a test notification
    async function requestNotificationPermission() {
        if (!("Notification" in window)) {
            if (window.showToast) window.showToast("此浏览器不支持系统级通知", "error");
            return "unsupported";
        }
        
        const permission = await Notification.requestPermission();
        updateNotificationPermissionStatus();
        return permission;
    }
    
    function updateNotificationPermissionStatus() {
        const badge = document.getElementById("notification-permission-status");
        if (!badge) return;
        
        if (!("Notification" in window)) {
            badge.innerText = "不支持";
            badge.style.backgroundColor = "var(--danger-light)";
            badge.style.color = "var(--danger)";
            return;
        }
        
        const status = Notification.permission;
        if (status === "granted") {
            badge.innerText = "已授权";
            badge.style.backgroundColor = "var(--success-light)";
            badge.style.color = "var(--success)";
        } else if (status === "denied") {
            badge.innerText = "被拒绝";
            badge.style.backgroundColor = "var(--danger-light)";
            badge.style.color = "var(--danger)";
        } else {
            badge.innerText = "未授权";
            badge.style.backgroundColor = "var(--warning-light)";
            badge.style.color = "var(--warning)";
        }
    }
    
    function sendTestNotification() {
        if (!("Notification" in window)) return;
        
        if (Notification.permission === "granted") {
            new Notification("测试通知 - DeskWatch", {
                body: "恭喜！DeskWatch 浏览器通知测试成功。",
                icon: "/favicon.ico"
            });
            if (window.showToast) window.showToast("测试通知发送成功", "success");
        } else {
            if (window.showToast) window.showToast("请先授予通知权限", "warning");
        }
    }
    
    // Expose APIs globally
    window.HealthEvents = HealthEvents;
    window.requestNotificationPermission = requestNotificationPermission;
    window.updateNotificationPermissionStatus = updateNotificationPermissionStatus;
    window.sendTestNotification = sendTestNotification;
})();
