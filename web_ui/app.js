/** A股涨停板池 - 前端逻辑 */
class ZtPoolApp {
    constructor() {
        this.data = [];
        this.predictions = {};  // {code: prediction_result}
        this.sortColumn = 'continuous_days';
        this.sortOrder = 'desc';
        this.filters = { continuous: 1, seal: 0, sector: '', search: '' };

        this.initElements();
        this.bindEvents();
        this.loadData();
    }

    initElements() {
        this.elements = {
            tbody: document.getElementById('zt-tbody'),
            total: document.getElementById('stat-total'),
            explosion: document.getElementById('stat-explosion'),
            rate: document.getElementById('stat-rate'),
            continuous: document.getElementById('stat-continuous'),
            momentum: document.getElementById('stat-momentum'),
            updateTime: document.getElementById('update-time'),
            filterContinuous: document.getElementById('filter-continuous'),
            filterSeal: document.getElementById('filter-seal'),
            filterSector: document.getElementById('filter-sector'),
            searchStock: document.getElementById('search-stock'),
            refreshBtn: document.getElementById('refresh-btn'),
            btnYesterdayDetail: document.getElementById('btn-yesterday-detail'),
            btnFactorDetail: document.getElementById('btn-factor-detail'),
            modal: document.getElementById('yesterday-modal'),
            modalClose: document.getElementById('modal-close'),
            factorModal: document.getElementById('factor-modal'),
            factorModalClose: document.getElementById('factor-modal-close'),
            predictionSection: document.getElementById('prediction-section'),
            predictionList: document.getElementById('prediction-list'),
            factorCategories: document.getElementById('factor-categories'),
            factorStockInfo: document.getElementById('factor-stock-info')
        };
        this.currentStockCode = null;  // 当前查看因子的股票
    }

    bindEvents() {
        // 刷新按钮
        this.elements.refreshBtn.addEventListener('click', () => this.loadData());

        // 筛选器
        this.elements.filterContinuous.addEventListener('change', (e) => {
            this.filters.continuous = parseInt(e.target.value);
            this.renderTable();
        });
        this.elements.filterSeal.addEventListener('change', (e) => {
            this.filters.seal = parseInt(e.target.value);
            this.renderTable();
        });
        this.elements.filterSector.addEventListener('change', (e) => {
            this.filters.sector = e.target.value;
            this.renderTable();
        });
        this.elements.searchStock.addEventListener('input', (e) => {
            this.filters.search = e.target.value.toLowerCase();
            this.renderTable();
        });

        // 排序
        document.querySelectorAll('th[data-sort]').forEach(th => {
            th.addEventListener('click', () => this.handleSort(th.dataset.sort));
        });

        // 昨涨停详情弹窗
        this.elements.btnYesterdayDetail?.addEventListener('click', () => this.showYesterdayDetail());
        this.elements.modalClose?.addEventListener('click', () => this.hideYesterdayDetail());
        this.elements.modal?.addEventListener('click', (e) => {
            if (e.target === this.elements.modal) this.hideYesterdayDetail();
        });

        // 因子详情弹窗
        this.elements.btnFactorDetail?.addEventListener('click', () => this.showFactorDetail());
        this.elements.factorModalClose?.addEventListener('click', () => this.hideFactorDetail());
        this.elements.factorModal?.addEventListener('click', (e) => {
            if (e.target === this.elements.factorModal) this.hideFactorDetail();
        });
    }

    async showYesterdayDetail() {
        const modal = this.elements.modal;
        if (!modal) return;

        modal.style.display = 'block';

        // 显示加载状态
        document.getElementById('list-down').innerHTML = '<div class="loading">加载中...</div>';
        document.getElementById('list-up').innerHTML = '<div class="loading">加载中...</div>';
        document.getElementById('list-flat').innerHTML = '<div class="loading">加载中...</div>';

        try {
            const res = await fetch('/api/zt_pool/yesterday_detail');
            const data = await res.json();

            if (data.code === 0) {
                this.renderYesterdayList('list-down', data.data.down_stocks, 'down');
                this.renderYesterdayList('list-up', data.data.up_stocks, 'up');
                this.renderYesterdayList('list-flat', data.data.flat_stocks, 'flat');

                // 如果没有数据，显示提示
                const total = data.data.down_stocks.length + data.data.up_stocks.length + data.data.flat_stocks.length;
                if (total === 0) {
                    document.getElementById('list-up').innerHTML = '<div class="loading">暂无数据</div>';
                }
            }
        } catch (err) {
            console.error('加载昨涨停详情失败:', err);
        }
    }

    hideYesterdayDetail() {
        this.elements.modal.style.display = 'none';
    }

    renderYesterdayList(listId, stocks, type) {
        const container = document.getElementById(listId);
        if (!stocks || stocks.length === 0) {
            container.innerHTML = '<span style="color:#999;font-size:13px;">暂无</span>';
            return;
        }

        container.innerHTML = stocks.map(s => {
            const changeStr = (s.today_change >= 0 ? '+' : '') + s.today_change + '%';
            return `<div class="stock-chip ${type}">
                <span class="name">${s.name}(${s.code})</span>
                <span class="change">${changeStr}</span>
            </div>`;
        }).join('');
    }

    async loadData() {
        try {
            const [poolRes, statsRes, sectorRes, predictRes] = await Promise.all([
                fetch('/api/zt_pool/today'),
                fetch('/api/stats/dashboard'),
                fetch('/api/sector/ranking?limit=20'),
                fetch('/api/predict/tomorrow')
            ]);

            const poolData = await poolRes.json();
            const statsData = await statsRes.json();
            const sectorData = await sectorRes.json();
            const predictData = await predictRes.json();

            this.data = poolData.data || [];

            // 构建预测结果字典
            this.predictions = {};
            (predictData.data || []).forEach(p => {
                this.predictions[p.stock_code] = p;
            });

            this.updateStats(statsData.data);
            this.updateSectorFilter(sectorData.data);
            this.renderPrediction(predictData.data || []);
            this.renderTable();
            this.elements.updateTime.textContent = statsData.data?.update_time || '--';
        } catch (err) {
            console.error('加载数据失败:', err);
            this.elements.tbody.innerHTML = '<tr><td colspan="9" class="loading">加载失败</td></tr>';
        }
    }

    updateStats(stats) {
        if (!stats) return;
        this.elements.total.textContent = stats.total_zt || 0;
        this.elements.explosion.textContent = stats.explosion_count || 0;
        this.elements.rate.textContent = (stats.explosion_rate || 0) + '%';
        this.elements.continuous.textContent = stats.continuous_count || 0;

        // 昨涨停今日表现
        const yp = stats.yesterday_performance || {};
        const momentum = this.elements.momentum;
        if (momentum) {
            momentum.textContent = yp.momentum_score || '--';
            momentum.className = 'stat-value momentum ' + this.getMomentumClass(yp.momentum_score);
        }

        // 显示昨涨停详情
        const yesterdayStats = document.getElementById('yesterday-stats');
        if (yesterdayStats && yp.yesterday_zt_count > 0) {
            yesterdayStats.style.display = 'flex';
            document.getElementById('stat-yesterday-count').textContent = yp.yesterday_zt_count;
            document.getElementById('stat-yesterday-up').textContent = yp.today_up_count;
            document.getElementById('stat-yesterday-down').textContent = yp.today_down_count;
            const avgEl = document.getElementById('stat-yesterday-avg');
            avgEl.textContent = (yp.today_change_avg >= 0 ? '+' : '') + yp.today_change_avg + '%';
            avgEl.className = 'stat-num ' + (yp.today_change_avg >= 0 ? 'up' : 'down');
        }
    }

    getMomentumClass(score) {
        const map = {
            '极好': 'excellent',
            '较好': 'good',
            '中性': 'neutral',
            '较差': 'bad',
            '极差': 'terrible'
        };
        return map[score] || 'neutral';
    }

    renderPrediction(predictions) {
        const container = this.elements.predictionList;
        const section = this.elements.predictionSection;

        if (!predictions || predictions.length === 0) {
            section.style.display = 'none';
            return;
        }

        // 保存预测列表用于因子详情
        this.predictionsList = predictions;
        section.style.display = 'block';

        container.innerHTML = predictions.slice(0, 10).map((p, idx) => {
            const pred = p.prediction || {};
            const score = pred.score || 0;
            const rec = pred.recommendation || '--';
            const upProb = (pred.up_probability || 0) * 100;

            let scoreClass = 'low';
            if (score >= 70) scoreClass = 'high';
            else if (score >= 50) scoreClass = 'medium';

            let recClass = 'watch';
            if (rec === '强烈推荐') recClass = 'strong';
            else if (rec === '推荐') recClass = 'good';
            else if (rec === '谨慎') recClass = 'caution';

            const isTop3 = idx < 3;

            return `<div class="prediction-card ${isTop3 ? 'top-3' : ''}"
                onclick="window.app.showStockFactorDetail(window.app.predictionsList[${idx}])"
                title="${this.formatAmount(p.seal_amount)} | 主力净流入${this.formatFlow(p.main_net_inflow)}">
                <div class="prediction-stock">
                    <span class="name ${p.continuous_days > 1 ? 'stock-up' : ''}">${p.stock_name}</span>
                    <span class="code">${p.stock_code}</span>
                </div>
                <div class="prediction-score">
                    <span class="score-value ${scoreClass}">${score}</span>
                    <span class="prob-value">涨 ${upProb.toFixed(0)}%</span>
                </div>
                <span class="recommendation ${recClass}">${rec}</span>
            </div>`;
        }).join('');
    }

    getRecBadge(rec) {
        let recClass = 'watch';
        if (rec === '强烈推荐') recClass = 'strong';
        else if (rec === '推荐') recClass = 'good';
        else if (rec === '谨慎') recClass = 'caution';
        return `<span class="rec-badge ${recClass}">${rec}</span>`;
    }

    // 因子详情相关
    async showFactorDetail() {
        const modal = this.elements.factorModal;
        if (!modal) return;

        modal.style.display = 'block';
        this.elements.factorCategories.innerHTML = '<div class="loading">加载中...</div>';

        // 获取因子定义
        try {
            const res = await fetch('/api/predict/factors');
            const data = await res.json();
            if (data.code === 0) {
                this.factorDefinitions = data.data;
            }
        } catch (err) {
            console.error('加载因子定义失败:', err);
        }

        // 显示第一只股票的因子详情
        const predictions = this.predictionsList || [];
        if (predictions.length > 0) {
            this.showStockFactorDetail(predictions[0]);
        }
    }

    showStockFactorDetail(prediction) {
        if (!prediction || !prediction.factors) {
            this.elements.factorCategories.innerHTML = '<div class="loading">暂无因子数据</div>';
            return;
        }

        const pred = prediction.prediction || {};
        this.elements.factorStockInfo.innerHTML = `
            <h3>${prediction.stock_name} (${prediction.stock_code})</h3>
            <div class="score-summary">
                综合评分: <strong style="font-size:24px;color:var(--primary)">${pred.score || 0}</strong> |
                上涨概率: <strong>${((pred.up_probability || 0) * 100).toFixed(0)}%</strong> |
                推荐: <span class="recommendation ${this.getRecClass(pred.recommendation)}">${pred.recommendation || '--'}</span>
            </div>
        `;

        // 按类别分组显示因子
        const categories = this.groupFactorsByCategory(prediction.factors);
        this.elements.factorCategories.innerHTML = Object.entries(categories).map(([cat, items]) => `
            <div class="factor-category">
                <h4>${this.getCategoryName(cat)}</h4>
                ${items.map(item => `
                    <div class="factor-item">
                        <span class="name">${item.display_name}</span>
                        <span class="value ${this.getScoreClass(item.score)}">${item.score.toFixed(0)}</span>
                    </div>
                `).join('')}
            </div>
        `).join('');
    }

    groupFactorsByCategory(factors) {
        const grouped = {};
        (this.factorDefinitions || []).forEach(def => {
            const cat = def.category;
            if (!grouped[cat]) grouped[cat] = [];
            grouped[cat].push({
                name: def.name,
                display_name: def.display_name,
                score: factors[def.name] || 50,
                weight: def.weight
            });
        });
        return grouped;
    }

    getCategoryName(cat) {
        const names = {
            'seal_quality': '涨停质量因子',
            'capital_behavior': '资金行为因子',
            'market_env': '市场环境因子',
            'technical': '技术形态因子',
            'historical': '历史规律因子',
            'order_book': '盘口数据因子',
            'northbound': '北向资金因子'
        };
        return names[cat] || cat;
    }

    getScoreClass(score) {
        if (score >= 70) return 'high';
        if (score >= 40) return 'medium';
        return 'low';
    }

    getRecClass(rec) {
        if (rec === '强烈推荐') return 'strong';
        if (rec === '推荐') return 'good';
        if (rec === '谨慎') return 'caution';
        return 'watch';
    }

    hideFactorDetail() {
        this.elements.factorModal.style.display = 'none';
    }

    updateSectorFilter(sectors) {
        const select = this.elements.filterSector;
        const currentValue = select.value;
        select.innerHTML = '<option value="">全部</option>';
        (sectors || []).forEach(s => {
            const opt = document.createElement('option');
            opt.value = s.sector_name;
            opt.textContent = s.sector_name;
            select.appendChild(opt);
        });
        select.value = currentValue;
    }

    handleSort(column) {
        if (this.sortColumn === column) {
            this.sortOrder = this.sortOrder === 'asc' ? 'desc' : 'asc';
        } else {
            this.sortColumn = column;
            this.sortOrder = 'desc';
        }
        this.renderTable();
    }

    getFilteredData() {
        return this.data.filter(item => {
            if (item.continuous_days < this.filters.continuous) return false;
            if ((item.seal_amount || 0) < this.filters.seal) return false;
            if (this.filters.sector && item.sector !== this.filters.sector) return false;
            if (this.filters.search) {
                const match = item.stock_code.toLowerCase().includes(this.filters.search) ||
                              item.stock_name.toLowerCase().includes(this.filters.search);
                if (!match) return false;
            }
            return true;
        }).sort((a, b) => {
            const aVal = a[this.sortColumn] || 0;
            const bVal = b[this.sortColumn] || 0;
            return this.sortOrder === 'asc' ? aVal - bVal : bVal - aVal;
        });
    }

    renderTable() {
        const filtered = this.getFilteredData();
        if (filtered.length === 0) {
            this.elements.tbody.innerHTML = '<tr><td colspan="9" class="loading">暂无数据</td></tr>';
            return;
        }

        this.elements.tbody.innerHTML = filtered.map(item => {
            const pred = this.predictions[item.stock_code];
            const rec = pred?.prediction?.recommendation || '--';
            return `
            <tr>
                <td>${item.stock_code}</td>
                <td class="stock-up">${item.stock_name}</td>
                <td>${item.continuous_days || 1}</td>
                <td>${this.formatAmount(item.seal_amount)}</td>
                <td class="${item.explosion_count > 0 ? 'stock-explosion' : ''}">${item.explosion_count || 0}</td>
                <td class="${item.super_net_inflow >= 0 ? 'positive' : 'negative'}">${this.formatFlow(item.super_net_inflow)}</td>
                <td class="${item.big_net_inflow >= 0 ? 'positive' : 'negative'}">${this.formatFlow(item.big_net_inflow)}</td>
                <td>${item.sector || '-'}</td>
                <td class="td-prediction">${this.getRecBadge(rec)}</td>
            </tr>
        `}).join('');
    }

    formatAmount(val) {
        if (!val) return '-';
        if (val >= 10000) return (val / 10000).toFixed(1) + '亿';
        return val.toFixed(0) + '万';
    }

    formatFlow(val) {
        if (!val && val !== 0) return '-';
        const abs = Math.abs(val);
        if (abs >= 10000) return (val >= 0 ? '+' : '-') + (abs / 10000).toFixed(2) + '亿';
        return (val >= 0 ? '+' : '-') + abs.toFixed(0) + '万';
    }
}

// 启动
document.addEventListener('DOMContentLoaded', () => {
    window.app = new ZtPoolApp();

    // 自动刷新 - 每分钟
    setInterval(() => window.app.loadData(), 60000);
});
