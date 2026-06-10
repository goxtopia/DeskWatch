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
        const timeline = data.timeline || [];
        const imageCount = timeline.length;
        document.getElementById("stat-total-images").innerText = imageCount;
        
        // Total tracked time (approximate based on interval)
        const interval = config ? config.sample_interval : 10;
        const totalSeconds = imageCount * interval;
        const minutes = Math.floor(totalSeconds / 60);
        const hours = Math.floor(minutes / 60);
        const remMin = minutes % 60;
        
        let timeStr = "";
        if (hours > 0) {
            timeStr = `${hours}h ${remMin}m`;
        } else {
            timeStr = `${remMin}m`;
        }
        document.getElementById("stat-total-time").innerText = timeStr;
        
        // Calculate and display sedentary stats (overtime & valid breaks)
        const sedStats = calculateSedentaryStats(timeline);
        document.getElementById("stat-overtime-time").innerText = `${sedStats.overtimeMinutes}m`;
        document.getElementById("stat-valid-breaks").innerText = `${sedStats.validBreaks}次`;
        
        // Calculate and display drinking stats
        const drinkCount = calculateDrinkingCount(timeline);
        const drinkCountEl = document.getElementById("stat-drinking-count");
        if (drinkCountEl) {
            drinkCountEl.innerText = `${drinkCount}次`;
        }
        
        // Build Doughnut Chart
        renderChart(data.summary);
        
        // Build Time Line Bar
        renderTimelineBar(timeline);
        
    } catch (e) {
        console.error("Error loading dashboard stats:", e);
        showToast("拉取监测统计失败", "error");
    }
    
    // Get reviewed count
    try {
        const res = await fetch("/api/stats/dataset");
        const data = await res.json();
        const reviewedCount = Object.values(data).reduce((a, b) => a + b, 0);
        document.getElementById("stat-reviewed-count").innerText = reviewedCount;
    } catch (e) {
        console.error("Error loading dataset stats:", e);
    }
}

function calculateSedentaryStats(timeline) {
    if (!timeline || timeline.length === 0) {
        return { validBreaks: 0, overtimeMinutes: 0 };
    }
    
    const interval = config ? config.sample_interval : 10;
    const minBreakCount = config ? config.min_break_detections : 5;
    const thresholdMinutes = config ? config.sedentary_threshold_minutes : 3;
    const breakCats = config ? (config.break_categories || ["Away", "Standing", "Napping"]) : ["Away", "Standing", "Napping"];
    const breakCatsLower = breakCats.map(c => c.toLowerCase());
    
    const isBreak = (label) => {
        if (!label) return false;
        return breakCatsLower.includes(label.toLowerCase());
    };
    
    // Convert YYYY-MM-DD HH:MM:SS to seconds from midnight
    function timeToSeconds(timeStr) {
        try {
            const parts = timeStr.split(" ");
            if (parts.length < 2) return 0;
            const timeParts = parts[1].split(":");
            return parseInt(timeParts[0], 10) * 3600 + parseInt(timeParts[1], 10) * 60 + parseInt(timeParts[2], 10);
        } catch (e) {
            return 0;
        }
    }
    
    // 1. Group timeline into sessions based on sample gaps (> 5 * interval)
    const maxGap = Math.max(300, 5 * interval);
    const sessions = [];
    let currentSession = [timeline[0]];
    
    for (let i = 1; i < timeline.length; i++) {
        const prevSec = timeToSeconds(timeline[i-1].timestamp);
        const currSec = timeToSeconds(timeline[i].timestamp);
        if (currSec - prevSec > maxGap) {
            sessions.push(currentSession);
            currentSession = [];
        }
        currentSession.push(timeline[i]);
    }
    sessions.push(currentSession);
    
    let totalValidBreaks = 0;
    let totalOvertimeSeconds = 0;
    
    // 2. Process each session
    sessions.forEach(session => {
        if (session.length === 0) return;
        
        // Find break segments in this session
        const breakSegments = [];
        let inBreak = false;
        let startIdx = -1;
        
        for (let i = 0; i < session.length; i++) {
            const isBrk = isBreak(session[i].label);
            if (isBrk) {
                if (!inBreak) {
                    inBreak = true;
                    startIdx = i;
                }
            } else {
                if (inBreak) {
                    breakSegments.push({ start: startIdx, end: i - 1 });
                    inBreak = false;
                }
            }
        }
        if (inBreak) {
            breakSegments.push({ start: startIdx, end: session.length - 1 });
        }
        
        // Filter valid break segments (consecutive detections >= minBreakCount)
        const validBreakSegments = [];
        breakSegments.forEach(seg => {
            const length = seg.end - seg.start + 1;
            if (length >= minBreakCount) {
                validBreakSegments.push(seg);
                totalValidBreaks++;
            }
        });
        
        // 3. Calculate sitting segments (separated by valid breaks)
        const sittingSegments = [];
        let prevEnd = -1;
        
        validBreakSegments.forEach(vBreak => {
            sittingSegments.push({ start: prevEnd + 1, end: vBreak.start - 1 });
            prevEnd = vBreak.end;
        });
        sittingSegments.push({ start: prevEnd + 1, end: session.length - 1 });
        
        // For each sitting segment, calculate duration and see if it exceeds threshold
        sittingSegments.forEach(seg => {
            if (seg.start > seg.end) return;
            
            const startSec = timeToSeconds(session[seg.start].timestamp);
            const endSec = timeToSeconds(session[seg.end].timestamp) + interval;
            const durationSec = endSec - startSec;
            
            const thresholdSec = thresholdMinutes * 60;
            if (durationSec > thresholdSec) {
                totalOvertimeSeconds += (durationSec - thresholdSec);
            }
        });
    });
    
    return {
        validBreaks: totalValidBreaks,
        overtimeMinutes: Math.round(totalOvertimeSeconds / 60)
    };
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

function calculateDrinkingCount(timeline) {
    if (!timeline || timeline.length === 0) return 0;
    
    const drinkCats = config && config.drinking_categories ? config.drinking_categories : ["Drinking Water"];
    const drinkCatsLower = drinkCats.map(c => c.toLowerCase());
    const mergeGap = config && config.drinking_merge_gap !== undefined ? config.drinking_merge_gap : 5;
    const interval = config ? config.sample_interval : 10;
    const maxGap = Math.max(300, 5 * interval);
    
    const isDrink = (label) => {
        if (!label) return false;
        return drinkCatsLower.includes(label.toLowerCase());
    };
    
    // Find all drink indices
    const drinkIndices = [];
    for (let i = 0; i < timeline.length; i++) {
        if (isDrink(timeline[i].label)) {
            drinkIndices.push(i);
        }
    }
    
    if (drinkIndices.length === 0) return 0;
    
    function timeToSeconds(timeStr) {
        try {
            const parts = timeStr.split(" ");
            if (parts.length < 2) return 0;
            const timeParts = parts[1].split(":");
            return parseInt(timeParts[0], 10) * 3600 + parseInt(timeParts[1], 10) * 60 + parseInt(timeParts[2], 10);
        } catch (e) {
            return 0;
        }
    }
    
    let occurrences = 1;
    for (let i = 1; i < drinkIndices.length; i++) {
        const prevIdx = drinkIndices[i-1];
        const currIdx = drinkIndices[i];
        
        // 1. Check index gap
        const indexGap = currIdx - prevIdx - 1;
        if (indexGap > mergeGap) {
            occurrences++;
            continue;
        }
        
        // 2. Check time gaps between consecutive records in the gap
        let sessionSplit = false;
        for (let j = prevIdx; j < currIdx; j++) {
            const prevSec = timeToSeconds(timeline[j].timestamp);
            const currSec = timeToSeconds(timeline[j+1].timestamp);
            if (currSec - prevSec > maxGap) {
                sessionSplit = true;
                break;
            }
        }
        
        if (sessionSplit) {
            occurrences++;
        }
    }
    
    return occurrences;
}
