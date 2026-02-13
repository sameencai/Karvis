FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY cloud_function/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY cloud_function/ .

# 创建本地数据目录
RUN mkdir -p /app/data

# 端口
EXPOSE 9000

# 启动（Lite 模式自动初始化 + 内置调度器自动启动）
CMD ["python", "app.py"]
