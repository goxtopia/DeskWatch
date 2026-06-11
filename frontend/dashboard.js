// DeskWatch - Dashboard Tab Module

// DYNAMIC COLOR MAPPER
function getCategoryColor(categoryName, index) {
    if (!config || !config.categories) return categoryColors[index % categoryColors.length];
    const catIdx = config.categories.indexOf(categoryName);
    if (catIdx !== -1) {
        return categoryColors[catIdx % categoryColors.length];
    }
    return categoryColors[index % categoryColors.length];
}

async function loadDashboardData() {
    if (!config) await fetchConfig();
    
    // Update stats summary count
    try {
        const res = await fetch("/api/stats/daily");
        const data = await res.json();
        
        // Total tracked image count
        const imageCount = data.total_images !== undefined ? data.total_images : (data.timeline ? data.timeline.length : 0);
        document.getElementById("stat-total-images").innerText = imageCount;
        
        // Total tracked time (approximate based on interval)
        document.getElementById("stat-total-time").innerText = data.total_time_str || "0m";
        
        // Computer and phone time stats
        const computerTimeEl = document.getElementById("stat-computer-time");
        if (computerTimeEl) {
            computerTimeEl.innerText = data.computer_time_str || "0m";
        }
        const phoneTimeEl = document.getElementById("stat-phone-time");
        if (phoneTimeEl) {
            phoneTimeEl.innerText = data.phone_time_str || "0m";
        }
        
        // Calculate and display sedentary stats (overtime & valid breaks)
        document.getElementById("stat-overtime-time").innerText = `${data.overtime_minutes || 0}m`;
        document.getElementById("stat-valid-breaks").innerText = `${data.valid_breaks || 0}次`;
        
        // Calculate and display drinking stats
        const drinkCountEl = document.getElementById("stat-drinking-count");
        if (drinkCountEl) {
            drinkCountEl.innerText = `${data.drinking_count || 0}次`;
        }
        
        // Total reviewed count
        document.getElementById("stat-reviewed-count").innerText = data.reviewed_count || 0;
        
        // Build Doughnut Chart
        renderChart(data.summary);
        
        // Build Time Line Bar
        renderTimelineBar(data.timeline || []);
        
    } catch (e) {
        console.error("Error loading dashboard stats:", e);
        showToast("拉取监测统计失败", "error");
    }
}

function renderChart(summaryData) {
    const ctx = document.getElementById('timeDistributionChart').getContext('2d');
    
    // Prepare Labels, values and colors
    const labels = Object.keys(summaryData || {});
    if (labels.length === 0) {
        labels.push("无数据");
    }
    
    const interval = config ? config.sample_interval : 10;
    const dataValues = labels.map(label => {
        if (label === "无数据") return 1;
        const count = summaryData[label];
        return parseFloat(((count * interval) / 60).toFixed(1));
    });
    
    const colors = labels.map((label, idx) => {
        if (label === "无数据") return 'hsla(220, 20%, 90%, 0.05)';
        return getCategoryColor(label, idx);
    });
    
    if (chartInstance) {
        chartInstance.destroy();
    }
    
    chartInstance = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: dataValues,
                backgroundColor: colors,
                borderColor: 'rgba(0, 0, 0, 0.4)',
                borderWidth: 2,
                hoverOffset: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: 'hsl(210, 12%, 72%)',
                        font: {
                            family: 'Outfit',
                            size: 12
                        },
                        padding: 16
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            if (context.label === "无数据") return "今天尚无采集记录";
                            return ` ${context.label}: ${context.raw} 分钟`;
                        }
                    }
                }
            },
            cutout: '65%'
        }
    });
}

function renderTimelineBar(timeline) {
    const barContainer = document.getElementById("timeline-bar");
    const legendContainer = document.getElementById("timeline-legend");
    barContainer.innerHTML = "";
    legendContainer.innerHTML = "";
    
    if (timeline.length === 0) {
        barContainer.innerHTML = `<div class="timeline-segment" style="width: 100%; background-color: hsla(220, 20%, 90%, 0.05); position: absolute; left: 0; top: 0; height: 100%;" data-tooltip="今天无监测记录"></div>`;
        legendContainer.innerHTML = `<div class="legend-item"><span class="legend-dot" style="background-color: hsla(220, 20%, 90%, 0.2);"></span><span>无监测数据</span></div>`;
        return;
    }
    
    function timeToSeconds(timeStr) {
        try {
            const parts = timeStr.split(" ");
            if (parts.length < 2) return 0;
            const timeParts = parts[1].split(":");
            if (timeParts.length < 3) return 0;
            const h = parseInt(timeParts[0], 10);
            const m = parseInt(timeParts[1], 10);
            const s = parseInt(timeParts[2], 10);
            return h * 3600 + m * 60 + s;
        } catch (e) {
            console.error("Error parsing time to seconds:", e);
            return 0;
        }
    }
    
    const segments = [];
    const interval = config ? config.sample_interval : 10;
    const maxGap = interval * 3;
    
    let currentSeg = {
        label: timeline[0].label,
        startTime: timeline[0].timestamp,
        endTime: timeline[0].timestamp,
        startSec: timeToSeconds(timeline[0].timestamp),
        endSec: timeToSeconds(timeline[0].timestamp) + interval
    };
    
    for (let i = 1; i < timeline.length; i++) {
        const item = timeline[i];
        const itemSec = timeToSeconds(item.timestamp);
        const gap = itemSec - currentSeg.endSec;
        
        if (item.label === currentSeg.label && gap <= maxGap) {
            currentSeg.endTime = item.timestamp;
            currentSeg.endSec = itemSec + interval;
        } else {
            segments.push(currentSeg);
            currentSeg = {
                label: item.label,
                startTime: item.timestamp,
                endTime: item.timestamp,
                startSec: itemSec,
                endSec: itemSec + interval
            };
        }
    }
    segments.push(currentSeg);
    
    const totalSecondsInDay = 86400;
    
    segments.forEach((seg, idx) => {
        const leftPct = (seg.startSec / totalSecondsInDay) * 100;
        const widthPct = ((seg.endSec - seg.startSec) / totalSecondsInDay) * 100;
        
        const color = getCategoryColor(seg.label, idx);
        const segmentDiv = document.createElement("div");
        segmentDiv.className = "timeline-segment";
        segmentDiv.style.position = "absolute";
        segmentDiv.style.left = `${leftPct.toFixed(3)}%`;
        segmentDiv.style.width = `${widthPct.toFixed(3)}%`;
        segmentDiv.style.height = "100%";
        segmentDiv.style.backgroundColor = color;
        
        const durationSec = seg.endSec - seg.startSec;
        const durationMin = Math.round(durationSec / 60);
        const durationStr = durationMin > 0 ? `${durationMin}分钟` : `${durationSec}秒`;
        
        const tooltipText = `${seg.label}: ${seg.startTime.substring(11)} ~ ${seg.endTime.substring(11)} (${durationStr})`;
        segmentDiv.setAttribute("data-tooltip", tooltipText);
        
        barContainer.appendChild(segmentDiv);
    });
    
    const uniqueLabels = [...new Set(timeline.map(item => item.label))];
    uniqueLabels.forEach((label, idx) => {
        const color = getCategoryColor(label, idx);
        const legendDiv = document.createElement("div");
        legendDiv.className = "legend-item";
        legendDiv.innerHTML = `
            <span class="legend-dot" style="background-color: ${color}"></span>
            <span>${label}</span>
        `;
        legendContainer.appendChild(legendDiv);
    });
}


