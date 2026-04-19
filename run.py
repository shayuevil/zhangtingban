"""启动脚本"""
import sys
import io
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from web_server import create_app
import uvicorn

if __name__ == "__main__":
    print("=" * 60)
    print("A股涨停板池系统 启动中...")
    print("=" * 60)

    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000)
