# A股涨停板池系统

实时监控A股涨停板池，支持资金流向分析、板块联动追踪。

## 功能特性

- 实时涨停池数据（每分钟自动刷新）
- 资金流向监控（超大单、大单净流入）
- Dashboard统计面板
- 多维度筛选（连板数、封板资金、板块）
- 历史数据存储（支持复盘）

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务
python run.py

# 访问
http://localhost:8000
```

## 项目结构

- `data_fetcher.py` - 数据获取接口
- `storage.py` - SQLite存储层
- `scheduler.py` - 定时任务调度
- `web_server.py` - FastAPI服务
- `web_ui/` - 前端页面
- `database/` - 数据库相关文件
