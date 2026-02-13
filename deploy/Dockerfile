FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY src/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY src/ ./src/

# 创建数据目录
RUN mkdir -p /app/my_life

WORKDIR /app/src

# 端口
EXPOSE 9000

# 启动（Lite 模式自动初始化 + 内置调度器自动启动）
CMD ["python", "app.py"]
