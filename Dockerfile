FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 复制依赖并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY app.py .

# 暴露 8080 端口供 Zeabur 识别
EXPOSE 8080

# 运行服务
CMD ["python", "app.py"]
