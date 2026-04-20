/** A股涨停板池 - 前端逻辑 */
class ZtPoolApp {
    constructor() {
        this.data = [];
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
            modal: document.getElementById('yesterday-modal'),
            modalClose: document.getElementById('modal-close')
        };
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
            const [poolRes, statsRes, sectorRes] = await Promise.all([
                fetch('/api/zt_pool/today'),
                fetch('/api/stats/dashboard'),
                fetch('/api/sector/ranking?limit=20')
            ]);

            const poolData = await poolRes.json();
            const statsData = await statsRes.json();
            const sectorData = await sectorRes.json();

            this.data = poolData.data || [];

            this.updateStats(statsData.data);
            this.updateSectorFilter(sectorData.data);
            this.renderTable();
            this.elements.updateTime.textContent = statsData.data?.update_time || '--';
        } catch (err) {
            console.error('加载数据失败:', err);
            this.elements.tbody.innerHTML = '<tr><td colspan="8" class="loading">加载失败</td></tr>';
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
            this.elements.tbody.innerHTML = '<tr><td colspan="8" class="loading">暂无数据</td></tr>';
            return;
        }

        this.elements.tbody.innerHTML = filtered.map(item => `
            <tr>
                <td>${item.stock_code}</td>
                <td class="stock-up">${item.stock_name}</td>
                <td>${item.continuous_days || 1}</td>
                <td>${this.formatAmount(item.seal_amount)}</td>
                <td class="${item.explosion_count > 0 ? 'stock-explosion' : ''}">${item.explosion_count || 0}</td>
                <td class="${item.super_net_inflow >= 0 ? 'positive' : 'negative'}">${this.formatFlow(item.super_net_inflow)}</td>
                <td class="${item.big_net_inflow >= 0 ? 'positive' : 'negative'}">${this.formatFlow(item.big_net_inflow)}</td>
                <td>${item.sector || '-'}</td>
            </tr>
        `).join('');
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
