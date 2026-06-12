/**
 * ConflictCompass — 前端交互逻辑
 */

// ============================================================
// 全局状态
// ============================================================

const STATE = {
    currentPage: 'workbench',
    selectedStage: '',
    selectedScenario: '',
    currentScriptId: null,
    currentScript: null,        // 当前生成的话术
    currentHistoryId: null,     // 当前查看的历史记录 ID
    editingTemplateId: null,    // 当前编辑的模板 ID
};

// 场景数据映射
const SCENARIOS = {
    '入职融入': [
        { name: '试用期目标沟通', risk: '低' },
        { name: '试用期延长通知', risk: '中' },
        { name: '转正评估面谈', risk: '低' },
    ],
    '在岗管理': [
        { name: '绩效考核反馈', risk: '中' },
        { name: '绩效改进计划(PIP)启动', risk: '高' },
        { name: '目标调整沟通', risk: '中' },
    ],
    '纪律与冲突': [
        { name: '违纪警告（口头）', risk: '高' },
        { name: '违纪警告（书面）', risk: '高' },
        { name: '冲突调解', risk: '高' },
        { name: '投诉处理反馈', risk: '中' },
    ],
    '异动与调整': [
        { name: '调岗沟通', risk: '中' },
        { name: '降职降薪通知', risk: '高' },
        { name: '组织架构调整传达', risk: '中' },
    ],
    '离职与善后': [
        { name: '离职挽留面谈', risk: '中' },
        { name: '协商解除劳动合同', risk: '极高' },
        { name: '裁员通知', risk: '极高' },
        { name: '竞业限制告知', risk: '中' },
    ],
};

const RISK_COLORS = { '低': '#28A745', '中': '#FD7E14', '高': '#DC3545', '极高': '#9B2C2C' };

// ============================================================
// 初始化
// ============================================================

document.addEventListener('DOMContentLoaded', () => {
    checkServiceStatus();
    loadHistory();
    loadTemplates();
});

// ============================================================
// 页面切换
// ============================================================

function switchPage(pageName) {
    STATE.currentPage = pageName;

    // 导航高亮
    document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
    document.querySelector(`[data-page="${pageName}"]`)?.classList.add('active');

    // 页面切换
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    const target = document.getElementById(`page-${pageName}`);
    if (target) target.classList.add('active');

    // 切换到对应页面时加载数据
    if (pageName === 'history') loadHistory();
    if (pageName === 'templates') loadTemplates();
}

// ============================================================
// 服务状态检查
// ============================================================

async function checkServiceStatus() {
    const dot = document.querySelector('.status-dot');
    const text = document.querySelector('.status-text');
    try {
        const res = await fetch('/api/ping');
        const data = await res.json();
        if (data.status === 'ok') {
            dot.className = 'status-dot online';
            if (data.api_key_configured) {
                text.textContent = '服务就绪 ✅';
            } else {
                text.textContent = 'API Key 未设置 ⚠️';
                dot.className = 'status-dot error';
            }
        } else {
            dot.className = 'status-dot error';
            text.textContent = '服务异常';
        }
    } catch (e) {
        dot.className = 'status-dot error';
        text.textContent = '服务未连接';
    }
}

// ============================================================
// 生命周期 → 场景选择
// ============================================================

function selectLifecycle(stage) {
    STATE.selectedStage = stage;
    STATE.selectedScenario = '';

    // 更新标签样式
    document.querySelectorAll('.lc-tab').forEach(t => t.classList.remove('selected'));
    document.querySelector(`[data-stage="${stage}"]`)?.classList.add('selected');

    // 渲染场景选择
    const grid = document.getElementById('scenarioGrid');
    const card = document.getElementById('step-scenario');
    const scenarios = SCENARIOS[stage] || [];

    grid.innerHTML = scenarios.map(s => `
        <div class="scenario-card" data-scenario="${s.name}" onclick="selectScenario('${s.name}')">
            <div class="sc-name">${s.name}</div>
            <div class="sc-risk" style="color:${RISK_COLORS[s.risk]}">风险等级：${s.risk}</div>
        </div>
    `).join('');

    card.classList.remove('hidden');

    // 隐藏后续步骤
    document.getElementById('step-details').classList.add('hidden');
    document.getElementById('step-result').classList.add('hidden');
    document.getElementById('step-optimize').classList.add('hidden');
}

function selectScenario(scenario) {
    STATE.selectedScenario = scenario;

    document.querySelectorAll('.scenario-card').forEach(c => c.classList.remove('selected'));
    document.querySelector(`[data-scenario="${scenario}"]`)?.classList.add('selected');

    // 显示详细信息表单
    document.getElementById('step-details').classList.remove('hidden');
    document.getElementById('step-result').classList.add('hidden');
    document.getElementById('step-optimize').classList.add('hidden');

    // 尝试从模板加载默认值
    loadTemplateDefaults(STATE.selectedStage, scenario);
}

async function loadTemplateDefaults(stage, scenario) {
    try {
        const res = await fetch('/api/templates?lifecycle_stage=' + encodeURIComponent(stage));
        const data = await res.json();
        const match = data.items.find(t => t.scenario === scenario);
        if (match) {
            if (match.default_tone) document.getElementById('inputTone').value = match.default_tone;
            if (match.default_notes) document.getElementById('inputExtra').value = match.default_notes;
        }
    } catch (e) {
        // 静默失败，不影响使用
    }
}

// ============================================================
// 话术生成
// ============================================================

async function generateScript() {
    if (!STATE.selectedStage || !STATE.selectedScenario) {
        showToast('请先选择生命周期阶段和场景', 'error');
        return;
    }

    const btn = document.getElementById('btnGenerate');
    btn.disabled = true;
    btn.innerHTML = '<span class="loading"></span> 生成中...';

    const params = {
        lifecycle_stage: STATE.selectedStage,
        scenario: STATE.selectedScenario,
        level: document.getElementById('inputLevel').value,
        emotion: document.getElementById('inputEmotion').value,
        tone: document.getElementById('inputTone').value,
        extra_info: document.getElementById('inputExtra').value,
    };

    try {
        const res = await fetch('/api/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params),
        });
        const data = await res.json();

        if (!data.success) {
            showToast(data.error || '生成失败', 'error');
            return;
        }

        STATE.currentScriptId = data.id;
        STATE.currentScript = data.script;
        renderScriptResult(data);
        document.getElementById('step-result').classList.remove('hidden');
        document.getElementById('step-optimize').classList.add('hidden');

        showToast('话术生成成功！', 'success');
    } catch (e) {
        showToast('网络请求失败：' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '✨ 生成话术';
    }
}

function renderScriptResult(data) {
    const { script, predictions, taboo_hits } = data;

    // 话术内容
    const output = document.getElementById('scriptOutput');
    output.innerHTML = `
        <div class="section-label label-opening">开场</div>
        <div class="section-text">${highlightTabooWords(script.opening, taboo_hits)}</div>
        <div class="section-label label-core">核心</div>
        <div class="section-text">${highlightTabooWords(script.core, taboo_hits)}</div>
        <div class="section-label label-closing">收尾</div>
        <div class="section-text">${highlightTabooWords(script.closing, taboo_hits)}</div>
    `;

    // 反应预判
    const predSection = document.getElementById('predictionsSection');
    const predList = document.getElementById('predictionsList');
    if (predictions && predictions.length > 0) {
        predSection.classList.remove('hidden');
        predList.innerHTML = predictions.map(p => `
            <div class="prediction-item">
                <div class="prediction-q">❓ ${escapeHtml(p.question)}</div>
                <div class="prediction-a">💡 ${escapeHtml(p.response)}</div>
            </div>
        `).join('');
    } else {
        predSection.classList.add('hidden');
    }

    // 禁忌词提醒
    renderTabooAlerts(taboo_hits, 'tabooAlerts');

    // 滚动到结果
    document.getElementById('step-result').scrollIntoView({ behavior: 'smooth' });
}

// ============================================================
// 话术优化
// ============================================================

function showOptimizePanel() {
    document.getElementById('step-optimize').classList.remove('hidden');
    document.getElementById('optimizedOutput').classList.add('hidden');
    document.getElementById('changesSummary').classList.add('hidden');
    document.getElementById('inputOptimizeNotes').value = '';
    document.getElementById('step-optimize').scrollIntoView({ behavior: 'smooth' });
}

function hideOptimizePanel() {
    document.getElementById('step-optimize').classList.add('hidden');
}

async function optimizeScript() {
    if (!STATE.currentScript) {
        showToast('请先生成话术', 'error');
        return;
    }

    const btn = document.getElementById('btnOptimize');
    btn.disabled = true;
    btn.innerHTML = '<span class="loading"></span> 优化中...';

    const params = {
        original_script: STATE.currentScript,
        direction: document.getElementById('inputOptimizeDirection').value,
        extra_notes: document.getElementById('inputOptimizeNotes').value,
        script_id: STATE.currentScriptId,
    };

    try {
        const res = await fetch('/api/optimize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params),
        });
        const data = await res.json();

        if (!data.success) {
            showToast(data.error || '优化失败', 'error');
            return;
        }

        // 显示优化结果
        const opt = data.optimized_script;
        const outDiv = document.getElementById('optimizedOutput');
        outDiv.innerHTML = `
            <h4 style="margin-bottom:12px;color:var(--orange)">🔧 优化后话术</h4>
            <div class="section-label label-opening">开场</div>
            <div class="section-text">${escapeHtml(opt.opening)}</div>
            <div class="section-label label-core">核心</div>
            <div class="section-text">${escapeHtml(opt.core)}</div>
            <div class="section-label label-closing">收尾</div>
            <div class="section-text">${escapeHtml(opt.closing)}</div>
        `;
        outDiv.classList.remove('hidden');

        // 修改说明
        if (data.changes_summary) {
            const changesDiv = document.getElementById('changesSummary');
            changesDiv.innerHTML = `<strong>📝 修改说明：</strong><br>${escapeHtml(data.changes_summary).replace(/\n/g, '<br>')}`;
            changesDiv.classList.remove('hidden');
        }

        // 更新当前话术为优化版
        STATE.currentScript = opt;

        // 禁忌词
        renderTabooAlerts(data.taboo_hits, 'tabooAlerts');

        showToast('话术优化成功！', 'success');
    } catch (e) {
        showToast('网络请求失败：' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '🔧 开始优化';
    }
}

// ============================================================
// 合规检查
// ============================================================

async function runCheck() {
    const text = document.getElementById('checkInput').value.trim();
    if (!text) {
        showToast('请粘贴待检查的话术', 'error');
        return;
    }

    const btn = document.getElementById('btnCheck');
    btn.disabled = true;
    btn.innerHTML = '<span class="loading"></span> 检查中...';

    try {
        const res = await fetch('/api/check', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: text }),
        });
        const data = await res.json();

        if (!data.success) {
            showToast(data.error || '检查失败', 'error');
            return;
        }

        renderCheckResults(data);
        document.getElementById('checkResultCard').classList.remove('hidden');
        document.getElementById('checkResultCard').scrollIntoView({ behavior: 'smooth' });
        showToast('合规检查完成！', 'success');
    } catch (e) {
        showToast('网络请求失败：' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '🔍 开始检查';
    }
}

function renderCheckResults(data) {
    const { summary, results, taboo_words } = data;

    // 汇总
    document.getElementById('checkSummary').innerHTML = `
        <div class="check-stat pass">
            <span class="stat-num">${summary.pass}</span>
            <span class="stat-label">✅ 通过</span>
        </div>
        <div class="check-stat warning">
            <span class="stat-num">${summary.warning}</span>
            <span class="stat-label">⚠️ 提醒</span>
        </div>
        <div class="check-stat violation">
            <span class="stat-num">${summary.violation}</span>
            <span class="stat-label">🚫 违规</span>
        </div>
    `;

    // 逐项结果
    const resultsDiv = document.getElementById('checkResults');
    resultsDiv.innerHTML = results.map(r => {
        const statusLabels = { pass: '✅ 通过', warning: '⚠️ 提醒', violation: '🚫 违规' };
        const lawsHtml = (r.legal_references || []).map(l =>
            `<div class="check-law">📜 ${escapeHtml(l.law)}：${escapeHtml(l.content)}</div>`
        ).join('');
        const suggestionHtml = r.suggestion ? `<div class="check-suggestion">💡 ${escapeHtml(r.suggestion)}</div>` : '';

        return `
            <div class="check-result-item ${r.status}">
                <div class="check-category">${statusLabels[r.status]} ${escapeHtml(r.category)}</div>
                ${r.detail ? `<div class="check-detail">${escapeHtml(r.detail)}</div>` : ''}
                ${lawsHtml}
                ${suggestionHtml}
            </div>
        `;
    }).join('');

    // 禁忌词
    renderTabooAlerts(taboo_words, 'checkTabooAlerts');
}

// ============================================================
// 历史记录
// ============================================================

let searchTimer = null;
function debounceSearch() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(loadHistory, 400);
}

async function loadHistory() {
    const stage = document.getElementById('historyStageFilter')?.value || '';
    const keyword = document.getElementById('historyKeyword')?.value || '';
    const container = document.getElementById('historyList');

    try {
        let url = '/api/history?limit=50';
        if (stage) url += '&lifecycle_stage=' + encodeURIComponent(stage);
        if (keyword) url += '&keyword=' + encodeURIComponent(keyword);

        const res = await fetch(url);
        const data = await res.json();

        if (!data.success) {
            container.innerHTML = `<div class="empty-state"><p>加载失败</p></div>`;
            return;
        }

        if (data.items.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">📭</div>
                    <p>暂无历史记录</p>
                    <span>生成的话术会自动保存在这里</span>
                </div>`;
            return;
        }

        container.innerHTML = data.items.map(item => `
            <div class="history-item" onclick="viewHistoryDetail(${item.id})">
                <span class="hi-stage">${escapeHtml(item.lifecycle_stage)}</span>
                <div class="hi-info">
                    <div class="hi-scenario">${escapeHtml(item.scenario)}</div>
                    <div class="hi-preview">${escapeHtml(item.preview)}</div>
                </div>
                <span class="hi-meta">${formatDate(item.created_at)}</span>
                <button class="hi-delete" onclick="event.stopPropagation();deleteHistory(${item.id})" title="删除">🗑</button>
            </div>
        `).join('');
    } catch (e) {
        container.innerHTML = `<div class="empty-state"><p>加载失败：${e.message}</p></div>`;
    }
}

async function viewHistoryDetail(id) {
    try {
        const res = await fetch(`/api/history/${id}`);
        const data = await res.json();
        if (!data.success) return;

        STATE.currentHistoryId = id;

        document.getElementById('modalTitle').textContent =
            `${data.lifecycle_stage} — ${data.scenario}`;

        const s = data.script || {};
        document.getElementById('modalBody').innerHTML = `
            <div class="script-output">
                <div class="section-label label-opening">开场</div>
                <div class="section-text">${escapeHtml(s.opening || '')}</div>
                <div class="section-label label-core">核心</div>
                <div class="section-text">${escapeHtml(s.core || '')}</div>
                <div class="section-label label-closing">收尾</div>
                <div class="section-text">${escapeHtml(s.closing || '')}</div>
            </div>
            ${data.predictions && data.predictions.length > 0 ? `
                <div class="predictions-section" style="margin-top:16px">
                    <h4>💬 对方反应预判</h4>
                    ${data.predictions.map(p => `
                        <div class="prediction-item">
                            <div class="prediction-q">❓ ${escapeHtml(p.question)}</div>
                            <div class="prediction-a">💡 ${escapeHtml(p.response)}</div>
                        </div>
                    `).join('')}
                </div>
            ` : ''}
            <div style="margin-top:8px;font-size:12px;color:var(--gray-400)">
                职级：${escapeHtml(data.level || '未填写')} |
                情绪：${escapeHtml(data.emotion || '未填写')} |
                语气：${escapeHtml(data.tone || '未填写')} |
                时间：${formatDate(data.created_at)}
            </div>
        `;

        document.getElementById('historyModal').classList.remove('hidden');
    } catch (e) {
        showToast('加载详情失败', 'error');
    }
}

function closeHistoryModal() {
    document.getElementById('historyModal').classList.add('hidden');
    STATE.currentHistoryId = null;
}

async function reuseFromHistory() {
    if (!STATE.currentHistoryId) return;

    try {
        const res = await fetch(`/api/history/${STATE.currentHistoryId}`);
        const data = await res.json();
        if (!data.success) return;

        // 加载到工作台
        STATE.selectedStage = data.lifecycle_stage;
        STATE.selectedScenario = data.scenario;
        STATE.currentScript = data.script;
        STATE.currentScriptId = data.id;

        // 切换到工作台
        switchPage('workbench');

        // 回填参数
        if (data.level) document.getElementById('inputLevel').value = data.level;
        if (data.emotion) document.getElementById('inputEmotion').value = data.emotion;
        if (data.tone) document.getElementById('inputTone').value = data.tone;
        if (data.extra_info) document.getElementById('inputExtra').value = data.extra_info;

        // 渲染结果
        renderScriptResult({
            script: data.script,
            predictions: data.predictions || [],
            taboo_hits: [],
        });
        document.getElementById('step-scenario').classList.remove('hidden');
        document.getElementById('step-details').classList.remove('hidden');
        document.getElementById('step-result').classList.remove('hidden');

        closeHistoryModal();
        showToast('已加载到工作台，可继续编辑优化', 'success');
    } catch (e) {
        showToast('加载失败', 'error');
    }
}

async function deleteHistory(id) {
    if (!confirm('确定删除这条记录吗？')) return;
    try {
        await fetch(`/api/history/${id}`, { method: 'DELETE' });
        showToast('已删除', 'success');
        loadHistory();
    } catch (e) {
        showToast('删除失败', 'error');
    }
}

// ============================================================
// 模板管理
// ============================================================

async function loadTemplates() {
    const container = document.getElementById('templateList');
    try {
        const res = await fetch('/api/templates');
        const data = await res.json();

        if (!data.items || data.items.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">📂</div>
                    <p>暂无模板</p>
                    <span>点击上方按钮创建第一个模板</span>
                </div>`;
            return;
        }

        container.innerHTML = data.items.map(t => `
            <div class="template-card">
                <div class="tc-icon">📋</div>
                <div class="tc-info">
                    <div class="tc-name">
                        ${escapeHtml(t.name)}
                        <span class="tc-stage">${escapeHtml(t.lifecycle_stage)}</span>
                        ${t.is_preset ? '<span class="tc-badge preset">预置</span>' : ''}
                    </div>
                    <div class="tc-desc">
                        场景：${escapeHtml(t.scenario)} | 默认语气：${escapeHtml(t.default_tone)}
                        ${t.default_notes ? ' | ' + escapeHtml(t.default_notes) : ''}
                    </div>
                </div>
                <div class="tc-actions">
                    ${!t.is_preset ? `
                        <button class="btn btn-sm" onclick="editTemplate(${t.id})">✏️</button>
                        <button class="btn btn-sm btn-danger" onclick="deleteTemplate(${t.id})">🗑</button>
                    ` : '<span class="tc-badge preset">系统内置</span>'}
                </div>
            </div>
        `).join('');
    } catch (e) {
        container.innerHTML = `<div class="empty-state"><p>加载失败</p></div>`;
    }
}

function showTemplateForm(id = null) {
    STATE.editingTemplateId = id;
    const modal = document.getElementById('templateModal');
    const title = document.getElementById('templateModalTitle');

    if (id) {
        title.textContent = '编辑模板';
        // 异步加载模板数据
        fetch(`/api/templates`)
            .then(r => r.json())
            .then(data => {
                const t = data.items.find(item => item.id === id);
                if (t) {
                    document.getElementById('tplName').value = t.name;
                    document.getElementById('tplStage').value = t.lifecycle_stage;
                    document.getElementById('tplScenario').value = t.scenario;
                    document.getElementById('tplTone').value = t.default_tone;
                    document.getElementById('tplNotes').value = t.default_notes;
                }
            });
    } else {
        title.textContent = '新建模板';
        document.getElementById('tplName').value = '';
        document.getElementById('tplStage').value = '';
        document.getElementById('tplScenario').value = '';
        document.getElementById('tplTone').value = '正式严肃';
        document.getElementById('tplNotes').value = '';
    }

    modal.classList.remove('hidden');
}

function closeTemplateModal() {
    document.getElementById('templateModal').classList.add('hidden');
    STATE.editingTemplateId = null;
}

async function saveTemplate() {
    const params = {
        name: document.getElementById('tplName').value.trim(),
        lifecycle_stage: document.getElementById('tplStage').value,
        scenario: document.getElementById('tplScenario').value.trim(),
        default_tone: document.getElementById('tplTone').value,
        default_notes: document.getElementById('tplNotes').value.trim(),
    };

    if (!params.name || !params.lifecycle_stage || !params.scenario) {
        showToast('请填写模板名称、生命周期和场景描述', 'error');
        return;
    }

    try {
        let res;
        if (STATE.editingTemplateId) {
            res = await fetch(`/api/templates/${STATE.editingTemplateId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(params),
            });
        } else {
            res = await fetch('/api/templates', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(params),
            });
        }
        const data = await res.json();
        if (data.success) {
            showToast(STATE.editingTemplateId ? '模板更新成功' : '模板创建成功', 'success');
            closeTemplateModal();
            loadTemplates();
        } else {
            showToast(data.error || '操作失败', 'error');
        }
    } catch (e) {
        showToast('操作失败：' + e.message, 'error');
    }
}

async function editTemplate(id) {
    showTemplateForm(id);
}

async function deleteTemplate(id) {
    if (!confirm('确定删除这个模板吗？')) return;
    try {
        const res = await fetch(`/api/templates/${id}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.success) {
            showToast('已删除', 'success');
            loadTemplates();
        } else {
            showToast(data.error || '删除失败', 'error');
        }
    } catch (e) {
        showToast('删除失败', 'error');
    }
}

// ============================================================
// 工具函数
// ============================================================

function copyScript() {
    if (!STATE.currentScript) {
        showToast('没有可复制的话术', 'error');
        return;
    }
    const s = STATE.currentScript;
    const text = `【开场】${s.opening}\n\n【核心】${s.core}\n\n【收尾】${s.closing}`;

    navigator.clipboard.writeText(text).then(() => {
        showToast('已复制到剪贴板 📋', 'success');
    }).catch(() => {
        // Fallback for older browsers
        const ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        showToast('已复制到剪贴板 📋', 'success');
    });
}

function highlightTabooWords(text, tabooHits) {
    if (!tabooHits || tabooHits.length === 0) return escapeHtml(text);

    let result = escapeHtml(text);
    tabooHits.forEach(hit => {
        const escapedWord = escapeHtml(hit.word);
        const levelClass = hit.level === 'confrontational' ? 'confrontational' : '';
        const suggestions = (hit.suggestions || []).join(' / ');
        result = result.replace(
            new RegExp(escapedWord, 'g'),
            `<span class="taboo-highlight ${levelClass}" title="建议替换：${escapeHtml(suggestions)}">
                ${escapedWord}<span class="taboo-tooltip">💡 ${escapeHtml(suggestions)}</span>
            </span>`
        );
    });
    return result;
}

function renderTabooAlerts(tabooHits, containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    if (!tabooHits || tabooHits.length === 0) {
        container.innerHTML = '';
        return;
    }

    container.innerHTML = tabooHits.map(hit => {
        const levelClass = hit.level === 'confrontational' ? 'confrontational' : 'escalation';
        const suggestions = (hit.suggestions || []).join('、');
        return `
            <div class="taboo-alert ${levelClass}">
                <span>⚠️</span>
                <div>
                    <span class="alert-word">"${escapeHtml(hit.word)}"</span>
                    <span>${hit.level === 'escalation' ? '（升级性词汇）' : '（对抗性词汇）'}</span>
                    <span class="alert-suggestions">→ 建议替换：${escapeHtml(suggestions)}</span>
                    <div style="font-size:11px;color:var(--gray-400);margin-top:2px">${escapeHtml(hit.context || '')}</div>
                </div>
            </div>
        `;
    }).join('');
}

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function formatDate(dateStr) {
    if (!dateStr) return '';
    try {
        const d = new Date(dateStr);
        return d.toLocaleDateString('zh-CN') + ' ' + d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    } catch (e) {
        return dateStr;
    }
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 0.3s';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}
