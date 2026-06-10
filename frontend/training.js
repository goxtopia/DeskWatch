// DeskWatch - Training Tab Module

async function loadTrainingData() {
    if (!config) await fetchConfig();
    
    // Fetch dataset distribution stats
    try {
        const res = await fetch("/api/stats/dataset");
        const datasetStats = await res.json();
        
        const tbody = document.getElementById("dataset-stats-tbody");
        tbody.innerHTML = "";
        
        let totalImages = 0;
        
        if (config && config.categories) {
            config.categories.forEach(cat => {
                const count = datasetStats[cat] || 0;
                totalImages += count;
                
                const row = document.createElement("tr");
                
                let statusBadge = `<span class="badge" style="background-color: hsla(220, 20%, 90%, 0.05); color: var(--text-muted);">暂无样本</span>`;
                if (count > 0 && count < 3) {
                    statusBadge = `<span class="badge" style="background-color: var(--warning-light); color: var(--warning);">样本较少</span>`;
                } else if (count >= 3) {
                    statusBadge = `<span class="badge" style="background-color: var(--success-light); color: var(--success);">就绪</span>`;
                }
                
                row.innerHTML = `
                    <td><strong>${cat}</strong></td>
                    <td>${count} 张</td>
                    <td>${statusBadge}</td>
                `;
                tbody.appendChild(row);
            });
        }
        
        document.getElementById("dataset-total-badge").innerText = `共 ${totalImages} 张已标注图片`;
    } catch (e) {
        console.error("Error loading dataset stats:", e);
        showToast("拉取数据集信息失败", "error");
    }
    
    // Refresh training status check
    checkTrainingStatus();
}

async function checkTrainingStatus() {
    try {
        const res = await fetch("/api/train/status");
        const data = await res.json();
        
        updateTrainingUI(data);
        
        if (data.is_training) {
            // If training, start polling
            if (!trainingInterval) {
                trainingInterval = setInterval(checkTrainingStatus, 1000);
            }
        } else {
            if (trainingInterval) {
                clearInterval(trainingInterval);
                trainingInterval = null;
            }
        }
    } catch (e) {
        console.error("Error checking training status:", e);
    }
}

function updateTrainingUI(status) {
    const badge = document.getElementById("train-status-badge");
    const progressFill = document.getElementById("train-progress-fill");
    const consoleBox = document.getElementById("train-console");
    const startBtn = document.getElementById("btn-start-training");
    
    // Epoch progress percent
    let pct = 0;
    if (status.total_epochs > 0) {
        pct = (status.current_epoch / status.total_epochs) * 100;
    }
    
    progressFill.style.width = `${pct}%`;
    
    document.getElementById("train-metric-epoch").innerText = `${status.current_epoch} / ${status.total_epochs}`;
    document.getElementById("train-metric-loss").innerText = status.train_loss ? status.train_loss.toFixed(4) : "0.0000";
    document.getElementById("train-metric-val-loss").innerText = status.val_loss ? status.val_loss.toFixed(4) : "0.0000";
    document.getElementById("train-metric-acc").innerText = status.val_accuracy ? `${(status.val_accuracy * 100).toFixed(2)}%` : "0.00%";
    
    const trainTypeSelect = document.getElementById("train-type");
    const trainType = trainTypeSelect ? trainTypeSelect.value : "cnn";
    let modelLabel = "ConvNeXt";
    if (trainType === "clip_mlp") modelLabel = "CLIP-MLP";
    else if (trainType === "clip_linear") modelLabel = "CLIP-Linear";
    
    if (status.is_training) {
        badge.innerText = "训练中";
        badge.className = "status-badge active";
        startBtn.disabled = true;
        startBtn.innerHTML = `<i class="ph-bold ph-spinner" style="animation: rotate 1.5s linear infinite;"></i> <span>正在训练 ${modelLabel}...</span>`;
    } else {
        badge.innerText = "空闲";
        badge.className = "status-badge";
        startBtn.disabled = false;
        startBtn.innerHTML = `<i class="ph-bold ph-play-circle"></i> <span>开始微调 ${modelLabel} 模型</span>`;
    }
    
    // Check log output & add to console using the logs array
    if (status.logs && status.logs.length > lastLogIndex) {
        for (let i = lastLogIndex; i < status.logs.length; i++) {
            const logMsg = status.logs[i];
            let lineClass = "system";
            if (logMsg.includes("successfully") || logMsg.includes("completed")) {
                lineClass = "success";
            }
            
            const timestamp = new Date().toLocaleTimeString();
            let displayMsg = logMsg;
            // Avoid prepending timestamp to border lines or metrics table rows
            const isTableLine = logMsg.startsWith("=") || logMsg.startsWith("各类别评估指标") || logMsg.startsWith("类别:");
            if (!isTableLine) {
                displayMsg = `[${timestamp}] ${logMsg}`;
            }
            
            const line = document.createElement("p");
            line.className = `console-line ${lineClass}`;
            line.innerText = displayMsg;
            consoleBox.appendChild(line);
        }
        lastLogIndex = status.logs.length;
        consoleBox.scrollTop = consoleBox.scrollHeight;
    }
    
    if (status.error) {
        const lastLine = consoleBox.lastElementChild;
        const timestamp = new Date().toLocaleTimeString();
        const errText = `[${timestamp}] 训练发生错误: ${status.error}`;
        if (!lastLine || !lastLine.innerText.includes(status.error)) {
            const line = document.createElement("p");
            line.className = "console-line error";
            line.innerText = errText;
            consoleBox.appendChild(line);
            consoleBox.scrollTop = consoleBox.scrollHeight;
        }
        showToast(`训练失败: ${status.error}`, "error");
    }
}

function initTrainingHandlers() {
    const trainTypeSelect = document.getElementById("train-type");
    if (trainTypeSelect) {
        trainTypeSelect.addEventListener("change", () => {
            const startBtn = document.getElementById("btn-start-training");
            let label = "ConvNeXt";
            if (trainTypeSelect.value === "clip_mlp") label = "CLIP-MLP";
            else if (trainTypeSelect.value === "clip_linear") label = "CLIP-Linear";
            startBtn.innerHTML = `<i class="ph-bold ph-play-circle"></i> <span>开始微调 ${label} 模型</span>`;
        });
    }

    const btnStartTraining = document.getElementById("btn-start-training");
    if (btnStartTraining) {
        btnStartTraining.addEventListener("click", async () => {
            const epochs = parseInt(document.getElementById("train-epochs").value);
            const batchSize = parseInt(document.getElementById("train-batch").value);
            const lr = parseFloat(document.getElementById("train-lr").value);
            const trainType = document.getElementById("train-type").value;
            
            const consoleBox = document.getElementById("train-console");
            lastLogIndex = 0;
            consoleBox.innerHTML = `<p class="console-line system">[系统] 正在向服务器请求启动微调...</p>`;
            
            try {
                const res = await fetch("/api/train", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ epochs, batch_size: batchSize, lr, train_type: trainType })
                });
                const data = await res.json();
                
                if (res.ok) {
                    showToast("训练已启动", "success");
                    checkTrainingStatus();
                } else {
                    showToast(data.detail || "启动训练失败", "error");
                    consoleBox.innerHTML += `<p class="console-line error">[错误] 启动失败: ${data.detail || "未知错误"}</p>`;
                }
            } catch (e) {
                showToast("网络请求失败", "error");
            }
        });
    }
}
