// DeskWatch - Settings Tab Module

async function loadSettingsData() {
    await fetchConfig();
    
    if (!config) return;
    
    document.getElementById("setting-rtsp-url").value = config.rtsp_url;
    document.getElementById("setting-interval").value = config.sample_interval;
    
    // Active model radio selection
    const radios = document.getElementsByName("setting-active-model");
    radios.forEach(radio => {
        if (radio.value === config.active_model) {
            radio.checked = true;
        }
        // Add change listener to show/hide sub-sections
        radio.addEventListener("change", toggleSettingsSubsections);
    });
    
    document.getElementById("setting-clip-model").value = config.clip_model_name;
    document.getElementById("setting-vlm-url").value = config.vlm_api_url;
    document.getElementById("setting-vlm-key").value = config.vlm_api_key;
    document.getElementById("setting-vlm-model").value = config.vlm_model;
    document.getElementById("setting-vlm-prompt").value = config.vlm_prompt;
    
    document.getElementById("setting-sedentary-enabled").checked = config.sedentary_reminder_enabled !== false;
    document.getElementById("setting-sedentary-threshold").value = config.sedentary_threshold_minutes || 3;
    document.getElementById("setting-sedentary-min-break").value = config.min_break_detections || 5;
    document.getElementById("setting-sedentary-snooze").value = config.sedentary_snooze_minutes || 5;
    
    // Telegram Bot parameters loading
    document.getElementById("setting-telegram-enabled").checked = config.telegram_bot_enabled === true;
    document.getElementById("setting-telegram-token").value = config.telegram_bot_token || "";
    document.getElementById("setting-telegram-chatid").value = config.telegram_chat_id || "";
    document.getElementById("setting-telegram-report-enabled").checked = config.telegram_report_enabled === true;
    document.getElementById("setting-telegram-report-time").value = config.telegram_report_time || "21:00";
    
    // Drinking parameters loading
    document.getElementById("setting-drinking-merge-gap").value = config.drinking_merge_gap !== undefined ? config.drinking_merge_gap : 5;
    
    // SWA config
    document.getElementById("setting-swa-strategy").value = config.swa_strategy || "softmax_drop_worst";
    document.getElementById("setting-swa-temperature").value = config.swa_temperature !== undefined ? config.swa_temperature : 10.0;
    
    toggleSettingsSubsections();
    renderSettingsCategories();
}

function toggleSettingsSubsections() {
    const checkedRadio = document.querySelector('input[name="setting-active-model"]:checked');
    if (!checkedRadio) return;
    const activeModel = checkedRadio.value;
    const clipPane = document.getElementById("clip-settings-pane");
    const vlmPane = document.getElementById("vlm-settings-pane");
    
    clipPane.style.display = activeModel === "clip" ? "block" : "none";
    vlmPane.style.display = activeModel === "vlm" ? "block" : "none";
}

function renderSettingsCategories() {
    const container = document.getElementById("settings-categories-list");
    if (!container) return;
    container.innerHTML = "";
    
    if (!config || !config.categories) return;
    
    config.categories.forEach(cat => {
        const tag = document.createElement("div");
        tag.className = "tag-item";
        tag.innerHTML = `
            <span>${cat}</span>
            <button type="button" class="btn-delete-tag"><i class="ph ph-x"></i></button>
        `;
        
        tag.querySelector(".btn-delete-tag").addEventListener("click", () => {
            if (config.categories.length <= 2) {
                showToast("至少需保留 2 个类别进行监测", "warning");
                return;
            }
            config.categories = config.categories.filter(c => c !== cat);
            renderSettingsCategories();
        });
        
        container.appendChild(tag);
    });
    
    renderSettingsBreakCategories();
    renderSettingsDrinkingCategories();
}

function renderSettingsBreakCategories() {
    const container = document.getElementById("setting-break-categories-list");
    if (!container) return;
    container.innerHTML = "";
    
    if (!config || !config.categories) return;
    
    const breakCats = config.break_categories || ["Away", "Standing", "Napping"];
    const breakCatsLower = breakCats.map(c => c.toLowerCase());
    
    config.categories.forEach(cat => {
        const wrapper = document.createElement("label");
        wrapper.style.display = "flex";
        wrapper.style.alignItems = "center";
        wrapper.style.gap = "8px";
        wrapper.style.cursor = "pointer";
        wrapper.style.fontSize = "0.85rem";
        
        const isChecked = breakCatsLower.includes(cat.toLowerCase());
        
        wrapper.innerHTML = `
            <input type="checkbox" value="${cat}" ${isChecked ? "checked" : ""} style="width: 16px; height: 16px;">
            <span>${cat}</span>
        `;
        container.appendChild(wrapper);
    });
}

function renderSettingsDrinkingCategories() {
    const container = document.getElementById("setting-drinking-categories-list");
    if (!container) return;
    container.innerHTML = "";
    
    if (!config || !config.categories) return;
    
    const drinkCats = config.drinking_categories || ["Drinking Water"];
    const drinkCatsLower = drinkCats.map(c => c.toLowerCase());
    
    config.categories.forEach(cat => {
        const wrapper = document.createElement("label");
        wrapper.style.display = "flex";
        wrapper.style.alignItems = "center";
        wrapper.style.gap = "8px";
        wrapper.style.cursor = "pointer";
        wrapper.style.fontSize = "0.85rem";
        
        const isChecked = drinkCatsLower.includes(cat.toLowerCase());
        
        wrapper.innerHTML = `
            <input type="checkbox" value="${cat}" ${isChecked ? "checked" : ""} style="width: 16px; height: 16px;">
            <span>${cat}</span>
        `;
        container.appendChild(wrapper);
    });
}

function initSettingsHandlers() {
    // ADD CATEGORY
    const btnAddCategory = document.getElementById("btn-add-category");
    if (btnAddCategory) {
        btnAddCategory.addEventListener("click", () => {
            const input = document.getElementById("new-category-input");
            const value = input.value.trim();
            
            if (!value) return;
            
            if (!config) config = { categories: [] };
            if (config.categories.includes(value)) {
                showToast("该类别已存在", "warning");
                return;
            }
            
            config.categories.push(value);
            input.value = "";
            renderSettingsCategories();
        });
    }
    
    // SAVE CONFIG
    const btnSaveSettings = document.getElementById("btn-save-settings");
    if (btnSaveSettings) {
        btnSaveSettings.addEventListener("click", async () => {
            const rtsp_url = document.getElementById("setting-rtsp-url").value.trim();
            const sample_interval = parseInt(document.getElementById("setting-interval").value);
            
            const checkedRadio = document.querySelector('input[name="setting-active-model"]:checked');
            if (!checkedRadio) {
                showToast("请选择一个活动模型", "error");
                return;
            }
            const active_model = checkedRadio.value;
            
            const clip_model_name = document.getElementById("setting-clip-model").value.trim();
            const vlm_api_url = document.getElementById("setting-vlm-url").value.trim();
            const vlm_api_key = document.getElementById("setting-vlm-key").value.trim();
            const vlm_model = document.getElementById("setting-vlm-model").value.trim();
            const vlm_prompt = document.getElementById("setting-vlm-prompt").value;
            
            if (!rtsp_url) {
                showToast("摄像头源不能为空", "error");
                return;
            }
            if (isNaN(sample_interval) || sample_interval < 2) {
                showToast("采样频率必须大于等于 2 秒", "error");
                return;
            }
            
            const sedentary_reminder_enabled = document.getElementById("setting-sedentary-enabled").checked;
            const sedentary_threshold_minutes = parseInt(document.getElementById("setting-sedentary-threshold").value);
            const min_break_detections = parseInt(document.getElementById("setting-sedentary-min-break").value);
            const sedentary_snooze_minutes = parseInt(document.getElementById("setting-sedentary-snooze").value);
            
            // Telegram Bot parameters saving
            const telegram_bot_enabled = document.getElementById("setting-telegram-enabled").checked;
            const telegram_bot_token = document.getElementById("setting-telegram-token").value.trim();
            const telegram_chat_id = document.getElementById("setting-telegram-chatid").value.trim();
            const telegram_report_enabled = document.getElementById("setting-telegram-report-enabled").checked;
            const telegram_report_time = document.getElementById("setting-telegram-report-time").value.trim();
            
            // Drinking config parameters saving
            const drinking_merge_gap = parseInt(document.getElementById("setting-drinking-merge-gap").value);
            
            const swa_strategy = document.getElementById("setting-swa-strategy").value;
            let swa_temperature = parseFloat(document.getElementById("setting-swa-temperature").value);
            if (isNaN(swa_temperature)) swa_temperature = 10.0;
            
            const break_categories = [];
            document.querySelectorAll("#setting-break-categories-list input:checked").forEach(cb => {
                break_categories.push(cb.value);
            });
            
            const drinking_categories = [];
            document.querySelectorAll("#setting-drinking-categories-list input:checked").forEach(cb => {
                drinking_categories.push(cb.value);
            });
            
            if (isNaN(sedentary_threshold_minutes) || sedentary_threshold_minutes < 1) {
                showToast("久坐提醒时间阈值必须大于等于 1 分钟", "error");
                return;
            }
            if (isNaN(min_break_detections) || min_break_detections < 1) {
                showToast("有效休息判定检测次数必须大于等于 1 次", "error");
                return;
            }
            if (isNaN(sedentary_snooze_minutes) || sedentary_snooze_minutes < 1) {
                showToast("重复提醒间隔时间必须大于等于 1 分钟", "error");
                return;
            }
            
            const updatedConfig = {
                rtsp_url,
                sample_interval,
                categories: config.categories,
                active_model,
                vlm_api_url,
                vlm_api_key,
                vlm_model,
                vlm_prompt,
                clip_model_name,
                sedentary_reminder_enabled,
                sedentary_threshold_minutes,
                min_break_detections,
                break_categories,
                sedentary_snooze_minutes,
                telegram_bot_enabled,
                telegram_bot_token,
                telegram_chat_id,
                telegram_report_enabled,
                telegram_report_time,
                drinking_categories,
                drinking_merge_gap,
                swa_strategy,
                swa_temperature
            };
            
            if (isNaN(drinking_merge_gap) || drinking_merge_gap < 0) {
                showToast("相邻饮水事件合并间隔必须大于等于 0", "error");
                return;
            }
            
            try {
                const res = await fetch("/api/config", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(updatedConfig)
                });
                const data = await res.json();
                
                if (res.ok) {
                    showToast("配置保存并应用成功", "success");
                    config = data.config;
                    
                    // Update global UI representation
                    document.getElementById("stat-active-model").innerText = config.active_model.toUpperCase();
                    
                    // Refresh status
                    fetchCameraStatus();
                } else {
                    let errMsg = "保存失败";
                    if (data.detail) {
                        if (Array.isArray(data.detail)) {
                            errMsg = data.detail.map(e => `${e.loc.join('.')}: ${e.msg}`).join('\n');
                        } else {
                            errMsg = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
                        }
                    }
                    showToast(errMsg, "error");
                }
            } catch (e) {
                showToast("接口请求错误", "error");
            }
        });
    }
}
