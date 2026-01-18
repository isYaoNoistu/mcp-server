// DOM加载完成后执行
document.addEventListener('DOMContentLoaded', function() {
    // 初始化选项卡
    initTabs();
    
    // 初始化工具列表
    loadTools();
    
    // 初始化配置工具
    initConfigTools();
    
    // 定期刷新数据
    setInterval(function() {
        loadTools();
    }, 5000); // 每5秒刷新一次
});

// 初始化选项卡功能
function initTabs() {
    const navLinks = document.querySelectorAll('.nav-link');
    const tabContents = document.querySelectorAll('.tab-content');
    
    navLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            
            // 获取目标选项卡ID
            const targetTab = this.getAttribute('data-tab');
            
            // 移除所有激活状态
            navLinks.forEach(l => l.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));
            
            // 添加当前激活状态
            this.classList.add('active');
            document.getElementById(targetTab).classList.add('active');
        });
    });
}

// 加载工具列表
function loadTools() {
    // 从后端API获取工具数据
    fetch('/api/tools')
        .then(response => response.json())
        .then(data => {
            const tools = data.tools || [];
            const toolsTable = document.getElementById('tools-table');
            toolsTable.innerHTML = '';
            
            tools.forEach(tool => {
                const toolRow = createToolRow(tool);
                toolsTable.appendChild(toolRow);
            });
        })
        .catch(error => {
            console.error('获取工具列表失败:', error);
            // 显示错误消息
            showToast('获取工具列表失败', 'error');
        });
}

// 创建工具行
function createToolRow(tool) {
    const row = document.createElement('div');
    row.className = 'tool-row';
    
    row.innerHTML = `
        <div class="tool-info">
            <div class="tool-row-name">${tool.name}</div>
            <div class="tool-row-description">${tool.description}</div>
        </div>
        <div class="tool-actions">
            <label class="switch">
                <input type="checkbox" id="toggle-${tool.id}" ${tool.status ? 'checked' : ''} data-tool-id="${tool.id}">
                <span class="slider"></span>
            </label>
        </div>
    `;
    
    // 添加开关事件监听
    const toggle = row.querySelector(`#toggle-${tool.id}`);
    toggle.addEventListener('change', function() {
        const toolId = this.dataset.toolId;
        const enabled = this.checked;
        toggleTool(toolId, enabled);
    });
    
    return row;
}

// 切换工具状态
function toggleTool(toolId, enabled) {
    // 调用后端API切换工具状态
    fetch('/api/tools/toggle', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ toolId, enabled })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast(`工具 ${enabled ? '已启用' : '已禁用'}: ${toolId}`, 'success');
            // 刷新工具列表
            loadTools();
        } else {
            showToast(`操作失败: ${data.message}`, 'error');
        }
    })
    .catch(error => {
        console.error('切换工具状态失败:', error);
        showToast('操作失败: 网络错误', 'error');
    });
}

// 初始化配置工具
function initConfigTools() {
    // 加载配置列表
    loadConfigList();
}

// 工具配置数据
const toolConfigs = {
    prometheus: {
        name: 'Prometheus工具',
        description: 'Prometheus指标查询工具',
        fields: {
            url: 'http://127.0.0.1:9090',
            username: '',
            password: ''
        }
    },
    files_query: {
        name: '文件查询工具',
        description: '读取FILES_ROOT下文件',
        fields: {
            root: 'files',
            max_bytes: '204800'
        }
    },
    mysql: {
        name: 'MySQL查询工具',
        description: 'MySQL数据库查询工具',
        fields: {
            host: '127.0.0.1',
            port: '3306',
            user: 'root',
            password: 'password'
        }
    },
    jenkins: {
        name: 'Jenkins工具',
        description: 'Jenkins信息分析工具',
        fields: {
            url: 'http://127.0.0.1:8080',
            username: '',
            token: '',
            timeout: '30',
            console_max_bytes: '204800'
        }
    },
    remote_host: {
        name: '远程主机配置',
        description: '配置远程主机执行工具的相关参数',
        fields: {
            '允许远程执行(ALLOW_REMOTE_EXEC)': 'false',
            '远程主机IP(REMOTE_HOST_IP)': '',
            'SSH端口(REMOTE_SSH_PORT)': '22',
            'SSH用户名(REMOTE_SSH_USER)': '',
            'SSH密码(REMOTE_SSH_PASSWORD)': '',
            'SSH密钥(REMOTE_SSH_KEY)': '',
            '认证方式(REMOTE_AUTH_METHOD)': 'password'
        }
    }
};

// 加载配置列表
function loadConfigList() {
    const configList = document.getElementById('config-list');
    configList.innerHTML = '';
    
    // 从后端获取当前配置
    fetch('/api/config/load')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const currentConfig = data.config;
                
                // 生成配置项
                for (const [toolId, config] of Object.entries(toolConfigs)) {
                    const configItem = document.createElement('div');
                    configItem.className = 'config-item';
                    configItem.innerHTML = `
                        <div class="config-item-info">
                            <div class="config-item-name">${config.name}</div>
                            <div class="config-item-description">${config.description}</div>
                        </div>
                        <div class="config-item-actions">
                            <button class="btn btn-sm btn-primary" onclick="toggleConfigDetails('${toolId}')">
                                <i class="fas fa-cog"></i> 配置
                            </button>
                        </div>
                    `;
                    
                    // 创建配置详情区域
                    const configDetails = document.createElement('div');
                    configDetails.id = `config-details-${toolId}`;
                    configDetails.className = 'config-details';
                    configDetails.innerHTML = generateConfigForm(toolId, config, currentConfig[toolId]);
                    
                    configList.appendChild(configItem);
                    configList.appendChild(configDetails);
                }
            } else {
                // 加载失败时使用默认配置
                for (const [toolId, config] of Object.entries(toolConfigs)) {
                    const configItem = document.createElement('div');
                    configItem.className = 'config-item';
                    configItem.innerHTML = `
                        <div class="config-item-info">
                            <div class="config-item-name">${config.name}</div>
                            <div class="config-item-description">${config.description}</div>
                        </div>
                        <div class="config-item-actions">
                            <button class="btn btn-sm btn-primary" onclick="toggleConfigDetails('${toolId}')">
                                <i class="fas fa-cog"></i> 配置
                            </button>
                        </div>
                    `;
                    
                    // 创建配置详情区域
                    const configDetails = document.createElement('div');
                    configDetails.id = `config-details-${toolId}`;
                    configDetails.className = 'config-details';
                    configDetails.innerHTML = generateConfigForm(toolId, config);
                    
                    configList.appendChild(configItem);
                    configList.appendChild(configDetails);
                }
            }
        })
        .catch(error => {
            console.error('加载配置失败:', error);
            // 网络错误时使用默认配置
            for (const [toolId, config] of Object.entries(toolConfigs)) {
                const configItem = document.createElement('div');
                configItem.className = 'config-item';
                configItem.innerHTML = `
                    <div class="config-item-info">
                        <div class="config-item-name">${config.name}</div>
                        <div class="config-item-description">${config.description}</div>
                    </div>
                    <div class="config-item-actions">
                        <button class="btn btn-sm btn-primary" onclick="toggleConfigDetails('${toolId}')">
                            <i class="fas fa-cog"></i> 配置
                        </button>
                    </div>
                `;
                
                // 创建配置详情区域
                const configDetails = document.createElement('div');
                configDetails.id = `config-details-${toolId}`;
                configDetails.className = 'config-details';
                configDetails.innerHTML = generateConfigForm(toolId, config);
                
                configList.appendChild(configItem);
                configList.appendChild(configDetails);
            }
        });
}

// 生成配置表单
function generateConfigForm(toolId, config, currentFields = {}) {
    let formHtml = '<div class="config-details-form">';
    
    for (const [field, defaultValue] of Object.entries(config.fields)) {
        // 使用当前配置值，如果没有则使用默认值
        const value = currentFields[field] || defaultValue;
        
        // 特殊处理远程主机配置的认证方式字段，使用下拉框
        if (toolId === 'remote_host' && field === '认证方式(REMOTE_AUTH_METHOD)') {
            formHtml += `
                <div class="config-field">
                    <label for="config-${toolId}-${field}">${field.replace(/_/g, ' ')}</label>
                    <select id="config-${toolId}-${field}" class="form-control" data-tool="${toolId}" data-field="${field}">
                        <option value="password" ${value === 'password' ? 'selected' : ''}>用户名/密码</option>
                        <option value="key" ${value === 'key' ? 'selected' : ''}>SSH密钥</option>
                    </select>
                </div>
            `;
        } else if (toolId === 'remote_host' && field === 'SSH密码(REMOTE_SSH_PASSWORD)') {
            formHtml += `
                <div class="config-field">
                    <label for="config-${toolId}-${field}">${field.replace(/_/g, ' ')}</label>
                    <input type="password" id="config-${toolId}-${field}" class="form-control" value="${value}" data-tool="${toolId}" data-field="${field}">
                </div>
            `;
        } else if (toolId === 'remote_host' && field === 'SSH密钥(REMOTE_SSH_KEY)') {
            formHtml += `
                <div class="config-field">
                    <label for="config-${toolId}-${field}">${field.replace(/_/g, ' ')}</label>
                    <textarea id="config-${toolId}-${field}" class="form-control" rows="5" data-tool="${toolId}" data-field="${field}">${value}</textarea>
                </div>
            `;
        } else if (toolId === 'remote_host' && field === '允许远程执行(ALLOW_REMOTE_EXEC)') {
            formHtml += `
                <div class="config-field">
                    <label for="config-${toolId}-${field}">${field.replace(/_/g, ' ')}</label>
                    <select id="config-${toolId}-${field}" class="form-control" data-tool="${toolId}" data-field="${field}">
                        <option value="true" ${value === 'true' ? 'selected' : ''}>是</option>
                        <option value="false" ${value === 'false' ? 'selected' : ''}>否</option>
                    </select>
                </div>
            `;
        } else {
            formHtml += `
                <div class="config-field">
                    <label for="config-${toolId}-${field}">${field.replace(/_/g, ' ')}</label>
                    <input type="text" id="config-${toolId}-${field}" class="form-control" value="${value}" data-tool="${toolId}" data-field="${field}">
                </div>
            `;
        }
    }
    
    // 添加远程主机配置的测试按钮
    if (toolId === 'remote_host') {
        formHtml += `
            <div class="config-detail-actions" style="margin-top: 10px;">
                <button class="btn btn-success" onclick="testRemoteHostConnection('${toolId}')" id="test-${toolId}">
                    <i class="fas fa-plug"></i> 测试连接
                </button>
                <span id="test-result-${toolId}" style="margin-left: 10px;"></span>
            </div>
        `;
    }
    
    formHtml += `
        <div class="config-detail-actions">
            <button class="btn btn-primary" onclick="saveToolConfig('${toolId}')">
                <i class="fas fa-save"></i> 保存
            </button>
            <button class="btn btn-secondary" onclick="cancelToolConfig('${toolId}')">
                <i class="fas fa-times"></i> 取消
            </button>
        </div>
    `;
    
    formHtml += '</div>';
    return formHtml;
}

// 切换配置详情显示
function toggleConfigDetails(toolId) {
    const configDetails = document.getElementById(`config-details-${toolId}`);
    configDetails.classList.toggle('active');
}

// 保存工具配置
function saveToolConfig(toolId) {
    const inputs = document.querySelectorAll(`[data-tool="${toolId}"]`);
    const configData = {};
    
    inputs.forEach(input => {
        const field = input.dataset.field;
        const value = input.value;
        configData[field] = value;
    });
    
    // 检查远程主机配置是否需要测试
    if (toolId === 'remote_host') {
        const testButton = document.getElementById(`test-${toolId}`);
        // 检查是否已经测试通过
        if (!testButton.hasAttribute('data-test-passed')) {
            showToast('请先测试远程主机连接，确保连接成功后再保存配置', 'warning');
            return;
        }
    }
    
    // 更新本地配置
    toolConfigs[toolId].fields = configData;
    
    // 调用后端API保存配置
    fetch('/api/config/save', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ [toolId]: configData })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast(`${toolConfigs[toolId].name} 配置保存成功`, 'success');
            // 收起配置详情
            cancelToolConfig(toolId);
        } else {
            showToast(`配置保存失败: ${data.message}`, 'error');
        }
    })
    .catch(error => {
        console.error('保存配置失败:', error);
        showToast('配置保存失败: 网络错误', 'error');
    });
}

// 取消配置
function cancelToolConfig(toolId) {
    const configDetails = document.getElementById(`config-details-${toolId}`);
    configDetails.classList.remove('active');
}

// 测试远程主机连接
function testRemoteHostConnection(toolId) {
    const inputs = document.querySelectorAll(`[data-tool="${toolId}"]`);
    const configData = {};
    
    inputs.forEach(input => {
        const field = input.dataset.field;
        const value = input.value;
        configData[field] = value;
    });
    
    // 更新测试按钮状态
    const testButton = document.getElementById(`test-${toolId}`);
    const testResult = document.getElementById(`test-result-${toolId}`);
    
    testButton.disabled = true;
    testButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 测试中...';
    testResult.innerHTML = '';
    
    // 发送测试请求
    fetch('/api/config/test-remote-connection', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(configData)
    })
    .then(response => response.json())
    .then(data => {
        // 恢复测试按钮状态
        testButton.disabled = false;
        testButton.innerHTML = '<i class="fas fa-plug"></i> 测试连接';
        
        if (data.success) {
            testResult.innerHTML = '<span style="color: green;"><i class="fas fa-check-circle"></i> 连接成功</span>';
            // 在按钮上添加测试通过标记
            testButton.setAttribute('data-test-passed', 'true');
        } else {
            testResult.innerHTML = `<span style="color: red;"><i class="fas fa-times-circle"></i> 连接失败: ${data.message}</span>`;
            // 移除测试通过标记
            testButton.removeAttribute('data-test-passed');
        }
    })
    .catch(error => {
        // 恢复测试按钮状态
        testButton.disabled = false;
        testButton.innerHTML = '<i class="fas fa-plug"></i> 测试连接';
        testResult.innerHTML = `<span style="color: red;"><i class="fas fa-times-circle"></i> 测试失败: ${error.message}</span>`;
        // 移除测试通过标记
        testButton.removeAttribute('data-test-passed');
    });
}

// 显示消息提示
function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    const toastText = toast.querySelector('.toast-text');
    const icon = toast.querySelector('i');
    
    // 设置消息内容
    toastText.textContent = message;
    
    // 设置消息类型
    toast.className = 'toast';
    if (type === 'error') {
        toast.classList.add('error');
        icon.className = 'fas fa-times-circle';
    } else if (type === 'warning') {
        toast.classList.add('warning');
        icon.className = 'fas fa-exclamation-circle';
    } else {
        icon.className = 'fas fa-check-circle';
    }
    
    // 显示消息
    toast.classList.add('show');
    
    // 3秒后自动隐藏
    setTimeout(function() {
        toast.classList.remove('show');
    }, 3000);
}

// 工具函数：发送API请求
async function sendApiRequest(url, method = 'GET', data = null) {
    try {
        const options = {
            method: method,
            headers: {
                'Content-Type': 'application/json'
            }
        };
        
        if (data) {
            options.body = JSON.stringify(data);
        }
        
        const response = await fetch(url, options);
        const result = await response.json();
        
        if (!response.ok) {
            throw new Error(result.message || '请求失败');
        }
        
        return result;
    } catch (error) {
        console.error('API请求失败:', error);
        showToast(`操作失败: ${error.message}`, 'error');
        throw error;
    }
}

// 工具函数：获取当前时间
function getCurrentTime() {
    const now = new Date();
    return now.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

// 工具函数：格式化数字
function formatNumber(num) {
    if (num >= 1000) {
        return (num / 1000).toFixed(1) + 'K';
    }
    return num.toString();
}

// 添加页面加载动画
window.addEventListener('load', function() {
    const loader = document.querySelector('.loader');
    if (loader) {
        loader.style.display = 'none';
    }
});

// 监听窗口大小变化
window.addEventListener('resize', function() {
    // 响应式调整逻辑
    console.log('窗口大小变化');
});

// 键盘快捷键支持
document.addEventListener('keydown', function(e) {
    // Ctrl/Cmd + T 切换到工具管理
    if ((e.ctrlKey || e.metaKey) && e.key === 't') {
        e.preventDefault();
        document.querySelector('[data-tab="tool-management"]').click();
    }
    
    // Ctrl/Cmd + C 切换到配置工具
    if ((e.ctrlKey || e.metaKey) && e.key === 'c') {
        e.preventDefault();
        document.querySelector('[data-tab="config-tools"]').click();
    }
    
    // Ctrl/Cmd + P 切换到平台使用
    if ((e.ctrlKey || e.metaKey) && e.key === 'p') {
        e.preventDefault();
        document.querySelector('[data-tab="platform-usage"]').click();
    }
    
    // ESC 关闭所有提示
    if (e.key === 'Escape') {
        const toast = document.getElementById('toast');
        toast.classList.remove('show');
    }
});

// 添加错误处理
window.addEventListener('error', function(e) {
    console.error('页面错误:', e.error);
    showToast(`页面发生错误: ${e.error.message}`, 'error');
});

// 添加网络状态监听
window.addEventListener('online', function() {
    showToast('网络已连接', 'success');
});

window.addEventListener('offline', function() {
    showToast('网络连接已断开', 'error');
});

// 个人信息相关函数

// 修改密码
function changePassword() {
    showToast('修改密码功能开发中', 'info');
}

// 退出登录
function logout() {
    if (confirm('确定要退出登录吗？')) {
        showToast('退出登录功能开发中', 'info');
    }
}

// 添加滚动到顶部按钮
function addScrollTopButton() {
    const scrollBtn = document.createElement('button');
    scrollBtn.className = 'scroll-top';
    scrollBtn.innerHTML = '<i class="fas fa-arrow-up"></i>';
    scrollBtn.style.cssText = `
        position: fixed;
        bottom: 20px;
        right: 20px;
        background-color: #6c757d;
        color: white;
        border: none;
        border-radius: 50%;
        width: 50px;
        height: 50px;
        font-size: 1.2rem;
        cursor: pointer;
        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.2);
        transition: all 0.3s ease;
        opacity: 0;
        visibility: hidden;
        z-index: 1000;
    `;
    
    document.body.appendChild(scrollBtn);
    
    // 监听滚动事件
    window.addEventListener('scroll', function() {
        if (window.pageYOffset > 300) {
            scrollBtn.style.opacity = '1';
            scrollBtn.style.visibility = 'visible';
        } else {
            scrollBtn.style.opacity = '0';
            scrollBtn.style.visibility = 'hidden';
        }
    });
    
    // 点击事件
    scrollBtn.addEventListener('click', function() {
        window.scrollTo({
            top: 0,
            behavior: 'smooth'
        });
    });
}

// 初始化滚动到顶部按钮
addScrollTopButton();

// 调用记录相关功能

// 在DOM加载完成后初始化调用记录模块
document.addEventListener('DOMContentLoaded', function() {
    // 初始化调用记录
    initCallRecords();
});

// 初始化调用记录
function initCallRecords() {
    // 加载调用记录
    loadCallRecords();
    
    // 定期刷新调用记录
    setInterval(function() {
        loadCallRecords();
    }, 10000); // 每10秒刷新一次
}

// 加载调用记录
function loadCallRecords() {
    // 从后端API获取调用记录数据
    fetch('/api/call-records')
        .then(response => response.json())
        .then(data => {
            const records = data.records || [];
            const recordsBody = document.getElementById('call-records-body');
            recordsBody.innerHTML = '';
            
            if (records.length === 0) {
                recordsBody.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 20px; color: #666;">暂无调用记录</td></tr>';
                return;
            }
            
            // 按照时间倒序排序
            records.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
            
            records.forEach(record => {
                const recordRow = createRecordRow(record);
                recordsBody.appendChild(recordRow);
            });
        })
        .catch(error => {
            console.error('获取调用记录失败:', error);
            const recordsBody = document.getElementById('call-records-body');
            recordsBody.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 20px; color: #dc3545;">获取调用记录失败</td></tr>';
        });
}

// 创建调用记录行
function createRecordRow(record) {
    const row = document.createElement('tr');
    row.className = 'record-row';
    
    // 格式化时间
    const timestamp = new Date(record.timestamp);
    const formattedTime = timestamp.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
    
    // 确定状态类
    let statusClass = 'status-info';
    if (record.status === 'success') {
        statusClass = 'status-success';
    } else if (record.status === 'error') {
        statusClass = 'status-error';
    }
    
    // 格式化处理时间（毫秒）
    const processTime = Math.round(parseFloat(record.process_time) * 1000);
    
    // 创建表格单元格
    const timeCell = document.createElement('td');
    timeCell.textContent = formattedTime;
    
    const toolCell = document.createElement('td');
    toolCell.textContent = record.tool_name;
    
    const ipCell = document.createElement('td');
    ipCell.textContent = record.client_ip;
    
    const statusCell = document.createElement('td');
    const statusSpan = document.createElement('span');
    statusSpan.className = statusClass;
    statusSpan.textContent = record.status;
    statusCell.appendChild(statusSpan);
    
    const timeCell2 = document.createElement('td');
    timeCell2.textContent = `${processTime}ms`;
    
    // 将单元格添加到行中
    row.appendChild(timeCell);
    row.appendChild(toolCell);
    row.appendChild(ipCell);
    row.appendChild(statusCell);
    row.appendChild(timeCell2);
    
    return row;
}



// 为调用记录添加键盘快捷键
document.addEventListener('keydown', function(e) {
    // Ctrl/Cmd + R 切换到调用记录
    if ((e.ctrlKey || e.metaKey) && e.key === 'r') {
        e.preventDefault();
        document.querySelector('[data-tab="call-records"]').click();
    }
});